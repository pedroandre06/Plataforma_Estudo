"""Sorteio de questões e criação de tentativas (quiz, simulado, prova)."""
from __future__ import annotations

import json
import random

from flask import abort

import config
import db
from comum import agora, em_minutos

MODOS_TREINO = ("treino", "prova", "revisao")


def ids_disponiveis(conn, modulo_ids=None, materia_ids=None, dificuldade="todas", excluir=None):
    sql = ["SELECT p.id FROM perguntas p JOIN modulos m ON m.id = p.modulo_id",
           "WHERE p.ativo = 1 AND m.ativo = 1"]
    params: list = []
    if modulo_ids:
        sql.append(f"AND p.modulo_id IN ({','.join('?' * len(modulo_ids))})")
        params += list(modulo_ids)
    if materia_ids:
        sql.append(f"AND m.materia_id IN ({','.join('?' * len(materia_ids))})")
        params += list(materia_ids)
    if dificuldade != "todas":
        sql.append("AND p.dificuldade = ?")
        params.append(dificuldade)
    if excluir:
        sql.append(f"AND p.id NOT IN ({','.join('?' * len(excluir))})")
        params += list(excluir)
    return [r["id"] for r in db.q(conn, " ".join(sql), params)]


def sortear(ids: list[int], quantidade: int) -> list[int]:
    if quantidade <= 0 or quantidade >= len(ids):
        return random.sample(ids, len(ids))
    return random.sample(ids, quantidade)


def ids_de_revisao(conn, usuario_id: int, modulo_ids=None) -> list[int]:
    """Questões erradas (ou em branco) pelo usuário em tentativas já entregues."""
    sql = ["SELECT r.pergunta_id FROM respostas r",
           "JOIN tentativas t ON t.id = r.tentativa_id",
           "JOIN perguntas p ON p.id = r.pergunta_id",
           "WHERE t.usuario_id = ? AND t.status = 'entregue' AND p.ativo = 1",
           "AND (r.correta = 0 OR r.alternativa_id IS NULL)"]
    params: list = [usuario_id]
    if modulo_ids:
        sql.append(f"AND p.modulo_id IN ({','.join('?' * len(modulo_ids))})")
        params += list(modulo_ids)
    return sorted({r["pergunta_id"] for r in db.q(conn, " ".join(sql), params)})


def ids_pontos_fracos(conn, usuario_id: int, limite: int = 40) -> list[int]:
    """Questões com menor taxa de acerto histórico (prioriza o que o usuário erra).

    Portabilidade SQLite/PostgreSQL: o HAVING e o ORDER BY repetem os agregados por
    extensao (nenhum dos dois motores garante alias de agregado no HAVING) e a divisao
    usa "* 1.0" em vez de CAST(... AS REAL), tipo que so existe no SQLite.
    """
    erros = "SUM(CASE WHEN r.correta = 1 THEN 1 ELSE 0 END)"
    linhas = db.q(conn, f"""
        SELECT r.pergunta_id,
               {erros} AS acertos,
               COUNT(*) AS total
        FROM respostas r
        JOIN tentativas t ON t.id = r.tentativa_id
        WHERE t.usuario_id = ? AND t.status = 'entregue' AND r.alternativa_id IS NOT NULL
        GROUP BY r.pergunta_id
        HAVING {erros} < COUNT(*)
        ORDER BY ({erros} * 1.0 / COUNT(*)) ASC, COUNT(*) DESC
    """, [usuario_id])
    escolhidas = [r["pergunta_id"] for r in linhas[:limite]]
    if len(escolhidas) < 8:
        usadas = {r["pergunta_id"] for r in linhas}
        novas = ids_disponiveis(conn, excluir=sorted(usadas))
        escolhidas += random.sample(novas, min(8 - len(escolhidas), len(novas)))
    return escolhidas


def criar_tentativa(conn, usuario_id: int, *, modo: str, modulo_id=None, simulado_id=None,
                    pergunta_ids=None, n_questoes: int = 10, tempo_min=None, nota_corte=None,
                    dificuldade="todas", embaralhar=True, mostrar_gabarito="fim",
                    modulo_ids=None, materia_ids=None) -> int:
    if pergunta_ids is not None:
        selecionadas = list(pergunta_ids)
    else:
        disponiveis = ids_disponiveis(conn, modulo_ids, materia_ids, dificuldade)
        if not disponiveis:
            abort(400, description="Não há questões disponíveis para esta seleção.")
        selecionadas = sortear(disponiveis, n_questoes)
    if embaralhar:
        random.shuffle(selecionadas)

    mapa: dict[str, list[int]] = {}
    for pid in selecionadas:
        alts = [r["id"] for r in db.q(
            conn, "SELECT id FROM alternativas WHERE pergunta_id = ? ORDER BY ordem, id", [pid])]
        if embaralhar:
            random.shuffle(alts)
        mapa[str(pid)] = alts

    regras = {"n_questoes": len(selecionadas), "tempo_min": tempo_min,
              "nota_corte": nota_corte if nota_corte is not None else config.NOTA_CORTE_PADRAO,
              "mostrar_gabarito": mostrar_gabarito, "dificuldade": dificuldade,
              "embaralhar": embaralhar}
    tid = db.run(conn, """INSERT INTO tentativas (usuario_id, modulo_id, simulado_id, modo, inicio_em,
                          limite_em, total, nota_corte, config_json, questoes_json)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 [usuario_id, modulo_id, simulado_id, modo, agora(),
                  em_minutos(tempo_min) if tempo_min else None, len(selecionadas),
                  regras["nota_corte"], json.dumps(regras, ensure_ascii=False), json.dumps(mapa)])
    for i, pid in enumerate(selecionadas):
        db.run(conn, "INSERT OR IGNORE INTO respostas (tentativa_id, pergunta_id, ordem) VALUES (?, ?, ?)",
               [tid, pid, i])
    return tid
