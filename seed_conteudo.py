"""Importação do conteúdo (matérias, módulos, questões e flashcards) a partir de data/content.

Flashcards: gerados automaticamente a partir das questões de cada módulo
(frente = enunciado, verso = resposta correta + explicação). Idempotente:
cartões com a mesma frente não são duplicados.
"""
from __future__ import annotations

import json

import config
import db
from rotas_admin_io import inserir_pergunta


def mapa_de_pdfs() -> dict[str, str]:
    """Nome do arquivo PDF -> caminho absoluto (usa o manifest da extração)."""
    manifest = config.MATERIAIS_DIR / "manifest.json"
    if not manifest.exists():
        return {}
    dados = json.loads(manifest.read_text(encoding="utf-8"))
    return {item["pdf_nome"]: item["pdf"] for item in dados}


def upsert_materia(conn, dados) -> int:
    existente = db.q1(conn, "SELECT id FROM materias WHERE slug = ?", [dados["slug"]])
    if existente:
        db.run(conn, """UPDATE materias SET nome = ?, descricao = ?, cor = ?, ordem = ?, ativo = 1
                        WHERE id = ?""",
               [dados["nome"], dados.get("descricao"), dados.get("cor", "#4f9cf9"),
                dados.get("ordem", 0), existente["id"]])
        return existente["id"]
    return db.run(conn, """INSERT INTO materias (slug, nome, descricao, cor, ordem) VALUES (?,?,?,?,?)""",
                  [dados["slug"], dados["nome"], dados.get("descricao"),
                   dados.get("cor", "#4f9cf9"), dados.get("ordem", 0)])


def upsert_modulo(conn, materia_id, meta, pdfs) -> int:
    existente = db.q1(conn, "SELECT id FROM modulos WHERE materia_id = ? AND slug = ?",
                      [materia_id, meta["slug"]])
    resumo = meta.get("resumo")
    texto = "\n".join(resumo) if isinstance(resumo, list) else resumo
    nome_pdf = meta.get("pdf_origem")
    campos = [meta["nome"], meta.get("descricao"), texto,
              pdfs.get(nome_pdf) if nome_pdf else None, meta.get("texto_path"), meta.get("ordem", 0)]
    if existente:
        db.run(conn, """UPDATE modulos SET nome = ?, descricao = ?, resumo = ?, pdf_origem = ?,
                        texto_path = ?, ordem = ?, ativo = 1 WHERE id = ?""", campos + [existente["id"]])
        return existente["id"]
    return db.run(conn, """INSERT INTO modulos (materia_id, slug, nome, descricao, resumo, pdf_origem,
                    texto_path, ordem) VALUES (?,?,?,?,?,?,?,?)""",
                  [materia_id, meta["slug"]] + campos)


def limpar(conn) -> None:
    """Apaga apenas o conteúdo (mantém usuários)."""
    for tabela in ("respostas", "tentativas", "progresso", "anotacoes", "flashcards",
                   "simulado_questoes", "simulado_materias", "simulados", "alternativas",
                   "perguntas", "modulos", "materias"):
        db.run(conn, f"DELETE FROM {tabela}")
    print("[seed] conteúdo anterior removido")


def pergunta_existe(conn, modulo_id: int, enunciado: str) -> bool:
    """True quando o módulo já tem uma questão com esse enunciado (evita duplicar no seed)."""
    return db.q1(conn, "SELECT 1 FROM perguntas WHERE modulo_id = ? AND enunciado = ?",
                 [modulo_id, enunciado]) is not None


def importar_conteudo(conn) -> int:
    pdfs = mapa_de_pdfs()
    materias = json.loads((config.CONTENT_DIR / "materias.json").read_text(encoding="utf-8"))
    ids = {m["slug"]: upsert_materia(conn, m) for m in materias}
    total = 0
    for slug, materia_id in ids.items():
        pasta = config.CONTENT_DIR / slug
        if not pasta.exists():
            continue
        metadados: dict[str, dict] = {}
        lotes: list[tuple[str, dict]] = []
        for arquivo in sorted(pasta.glob("*.json")):
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            modulo_slug = dados["modulo_slug"]
            if "modulo" in dados:
                metadados[modulo_slug] = {"slug": modulo_slug, **dados["modulo"]}
            for p in dados.get("perguntas", []):
                lotes.append((modulo_slug, p))
        ids_modulo = {}
        for modulo_slug, meta in metadados.items():
            ids_modulo[modulo_slug] = upsert_modulo(conn, materia_id, meta, pdfs)
            print(f"[seed] módulo: {meta['nome']}")
        inseridas = 0
        puladas = 0
        for modulo_slug, p in lotes:
            modulo_id = ids_modulo.get(modulo_slug)
            if not modulo_id:
                continue
            enunciado = (p.get("e") or p.get("enunciado") or "").strip()
            if pergunta_existe(conn, modulo_id, enunciado):
                puladas += 1
                continue
            if inserir_pergunta(conn, modulo_id, p):
                inseridas += 1
        print(f"[seed] {slug}: {inseridas} questões novas"
              + (f" ({puladas} já existiam)" if puladas else ""))
        total += inseridas
        gerar_flashcards_modulo(conn, materia_id, ids_modulo)
    return total


def gerar_flashcards_modulo(conn, materia_id: int, ids_modulo: dict[str, int]) -> int:
    """Gera 1 flashcard por questão (frente=enunciado, verso=resposta+explicação).

    Idempotente: pula frentes que já existem no módulo. Retorna nº de novos cartões.
    """
    total = 0
    for modulo_slug, modulo_id in ids_modulo.items():
        perguntas = db.q(conn, """SELECT p.id, p.enunciado, p.explicacao
                                  FROM perguntas p WHERE p.modulo_id = ? AND p.ativo = 1
                                  ORDER BY p.id""", [modulo_id])
        if not perguntas:
            continue
        existentes = {r["frente"] for r in db.q(
            conn, "SELECT frente FROM flashcards WHERE modulo_id = ?", [modulo_id])}
        ordem = db.q1(conn, "SELECT COALESCE(MAX(ordem), -1) AS m FROM flashcards WHERE modulo_id = ?",
                      [modulo_id])["m"] + 1
        for pg in perguntas:
            frente = (pg["enunciado"] or "").strip()
            if not frente or frente in existentes:
                continue
            alts = db.q(conn, """SELECT texto FROM alternativas WHERE pergunta_id = ?
                                 ORDER BY correta DESC, ordem""", [pg["id"]])
            resposta = (alts[0]["texto"] if alts else "").strip()
            verso = resposta
            if pg["explicacao"]:
                verso = f"{resposta}\n\n{pg['explicacao']}" if resposta else pg["explicacao"]
            db.run(conn, "INSERT INTO flashcards (modulo_id, frente, verso, ordem) VALUES (?,?,?,?)",
                   [modulo_id, frente, verso, ordem])
            ordem += 1
            existentes.add(frente)
            total += 1
    if total:
        print(f"[seed] flashcards gerados: {total}")
    return total
