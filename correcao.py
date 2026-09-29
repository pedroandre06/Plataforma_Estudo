"""Correção de tentativas, análise de desempenho e atualização de progresso."""
from __future__ import annotations

import json
from collections import defaultdict

import config
import db
from comum import agora, segundos_desde


def corrigir(conn, tentativa, tempo_seg=None) -> dict:
    linhas = db.q(conn, """SELECT r.id, r.pergunta_id, r.alternativa_id
                           FROM respostas r WHERE r.tentativa_id = ?""", [tentativa["id"]])
    acertos = erros = brancos = 0
    for r in linhas:
        if r["alternativa_id"] is None:
            brancos += 1
            db.run(conn, "UPDATE respostas SET correta = NULL WHERE id = ?", [r["id"]])
            continue
        certa = db.q1(conn, "SELECT id FROM alternativas WHERE pergunta_id = ? AND correta = 1",
                      [r["pergunta_id"]])
        ok = bool(certa and certa["id"] == r["alternativa_id"])
        acertos += 1 if ok else 0
        erros += 0 if ok else 1
        db.run(conn, "UPDATE respostas SET correta = ? WHERE id = ?", [1 if ok else 0, r["id"]])

    total = len(linhas)
    nota = round(10 * acertos / total, 1) if total else 0.0
    regras = json.loads(tentativa["config_json"] or "{}")
    corte = float(tentativa["nota_corte"] or regras.get("nota_corte") or config.NOTA_CORTE_PADRAO)
    tempo = segundos_desde(tentativa["inicio_em"]) if tempo_seg is None else int(tempo_seg)
    db.run(conn, """UPDATE tentativas SET status = 'entregue', fim_em = ?, tempo_seg = ?, acertos = ?,
                    erros = ?, brancos = ?, nota = ?, aprovado = ? WHERE id = ?""",
           [agora(), tempo, acertos, erros, brancos, nota, 1 if nota >= corte else 0, tentativa["id"]])
    if tentativa["modulo_id"]:
        atualizar_progresso(conn, tentativa["usuario_id"], tentativa["modulo_id"], tentativa["id"])
    return {"acertos": acertos, "erros": erros, "brancos": brancos, "total": total, "nota": nota,
            "corte": corte, "aprovado": nota >= corte, "tempo_seg": tempo}


def analise(conn, tentativa_id: int) -> dict:
    linhas = db.q(conn, """
        SELECT r.correta, p.dificuldade, p.topico,
               m.nome AS modulo_nome, m.slug AS modulo_slug,
               mt.nome AS materia_nome, mt.cor AS materia_cor
        FROM respostas r
        JOIN perguntas p ON p.id = r.pergunta_id
        JOIN modulos m ON m.id = p.modulo_id
        JOIN materias mt ON mt.id = m.materia_id
        WHERE r.tentativa_id = ?
    """, [tentativa_id])
    baldes = {"materia": defaultdict(lambda: [0, 0]), "modulo": defaultdict(lambda: [0, 0]),
              "dificuldade": defaultdict(lambda: [0, 0]), "topico": defaultdict(lambda: [0, 0])}
    cores: dict[str, str] = {}
    slugs: dict[str, str] = {}
    for r in linhas:
        certo = 1 if r["correta"] == 1 else 0
        for chave, valor in (("materia", r["materia_nome"]), ("modulo", r["modulo_nome"]),
                             ("dificuldade", r["dificuldade"]), ("topico", r["topico"] or "Geral")):
            baldes[chave][valor][0] += certo
            baldes[chave][valor][1] += 1
        cores[r["materia_nome"]] = r["materia_cor"]
        slugs[r["modulo_nome"]] = r["modulo_slug"]
    saida: dict[str, list[dict]] = {}
    for chave, valores in baldes.items():
        itens = [{"nome": nome, "acertos": v[0], "total": v[1],
                  "pct": round(100 * v[0] / v[1]) if v[1] else 0} for nome, v in valores.items()]
        itens.sort(key=lambda i: (-i["pct"], i["nome"]))
        saida[chave] = itens
    return {"grupos": saida, "cores": cores, "slugs": slugs}


def atualizar_progresso(conn, usuario_id: int, modulo_id: int, tentativa_id: int,
                        limiar_conclusao: float = 7.0) -> None:
    total = db.q1(conn, "SELECT COUNT(*) AS n FROM respostas WHERE tentativa_id = ?", [tentativa_id])["n"]
    acertos = db.q1(conn, "SELECT COUNT(*) AS n FROM respostas WHERE tentativa_id = ? AND correta = 1",
                    [tentativa_id])["n"]
    nota = round(10 * acertos / total, 1) if total else 0.0
    atual = db.q1(conn, "SELECT * FROM progresso WHERE usuario_id = ? AND modulo_id = ?",
                  [usuario_id, modulo_id])
    concluido = nota >= limiar_conclusao
    if atual is None:
        db.run(conn, """INSERT INTO progresso (usuario_id, modulo_id, status, melhor_nota, tentativas,
                        acertos, respostas, ultimo_acesso, concluido_em)
                        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)""",
               [usuario_id, modulo_id, "concluido" if concluido else "em_andamento", nota, acertos, total,
                agora(), agora() if concluido else None])
        return
    status = "concluido" if (concluido or atual["status"] == "concluido") else "em_andamento"
    db.run(conn, """UPDATE progresso SET status = ?, melhor_nota = ?, tentativas = tentativas + 1,
                    acertos = acertos + ?, respostas = respostas + ?, ultimo_acesso = ? WHERE id = ?""",
           [status, max(atual["melhor_nota"] or 0, nota), acertos, total, agora(), atual["id"]])
    if status == "concluido" and not atual["concluido_em"]:
        db.run(conn, "UPDATE progresso SET concluido_em = ? WHERE id = ?", [agora(), atual["id"]])


def tocar_modulo(conn, usuario_id: int, modulo_id: int, status: str = "em_andamento") -> None:
    atual = db.q1(conn, "SELECT * FROM progresso WHERE usuario_id = ? AND modulo_id = ?",
                  [usuario_id, modulo_id])
    if atual is None:
        db.run(conn, """INSERT INTO progresso (usuario_id, modulo_id, status, ultimo_acesso)
                        VALUES (?, ?, ?, ?)""", [usuario_id, modulo_id, status, agora()])
    else:
        novo = atual["status"]
        if status == "concluido" or atual["status"] == "em_andamento":
            novo = status
        db.run(conn, "UPDATE progresso SET ultimo_acesso = ?, status = ? WHERE id = ?",
               [agora(), novo, atual["id"]])
