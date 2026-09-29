"""Acesso à tentativa em andamento: carregar, listar questões e salvar respostas."""
from __future__ import annotations

import json

from flask import abort

import db


def carregar(conn, tentativa_id: int, usuario_id=None, exigir_andamento=False):
    t = db.q1(conn, "SELECT * FROM tentativas WHERE id = ?", [tentativa_id])
    if t is None:
        abort(404, description="Tentativa não encontrada.")
    if usuario_id is not None and t["usuario_id"] != usuario_id:
        abort(403, description="Esta tentativa pertence a outro usuário.")
    if exigir_andamento and t["status"] != "em_andamento":
        abort(400, description="Esta tentativa já foi finalizada.")
    return t, json.loads(t["questoes_json"] or "{}"), json.loads(t["config_json"] or "{}")


def questoes(conn, tentativa, mapa) -> list[dict]:
    """Questões na ordem sorteada, com as alternativas na ordem exibida ao aluno."""
    respostas = {r["pergunta_id"]: r for r in db.q(
        conn, "SELECT * FROM respostas WHERE tentativa_id = ? ORDER BY ordem", [tentativa["id"]])}
    chaves = sorted(mapa.keys(), key=lambda k: respostas[int(k)]["ordem"] if int(k) in respostas else 999)
    saida = []
    for chave in chaves:
        pid = int(chave)
        p = db.q1(conn, """SELECT p.*, m.nome AS modulo_nome, m.slug AS modulo_slug,
                                  mt.nome AS materia_nome, mt.cor AS materia_cor
                           FROM perguntas p
                           JOIN modulos m ON m.id = p.modulo_id
                           JOIN materias mt ON mt.id = m.materia_id
                           WHERE p.id = ?""", [pid])
        if not p:
            continue
        ordem_alts = mapa.get(chave) or []
        if ordem_alts:
            marca = ",".join("?" * len(ordem_alts))
            alts = db.q(conn, f"SELECT * FROM alternativas WHERE id IN ({marca})", ordem_alts)
            alts.sort(key=lambda a: ordem_alts.index(a["id"]))
        else:
            alts = db.q(conn, "SELECT * FROM alternativas WHERE pergunta_id = ? ORDER BY ordem", [pid])
        r = respostas.get(pid)
        saida.append({"pergunta": p, "alternativas": alts, "ordem": r["ordem"] if r else 0,
                      "resposta_id": r["id"] if r else None,
                      "escolhida": r["alternativa_id"] if r else None,
                      "correta": r["correta"] if r else None,
                      "marcada": bool(r["marcada_revisao"]) if r else False})
    return saida


def resposta_do_aluno(conn, tentativa_id: int, pergunta_id: int):
    return db.q1(conn, "SELECT * FROM respostas WHERE tentativa_id = ? AND pergunta_id = ?",
                 [tentativa_id, pergunta_id])


def salvar_resposta(conn, tentativa, pergunta_id: int, alternativa_id=None, marcar=None) -> None:
    if tentativa["status"] != "em_andamento":
        return
    r = resposta_do_aluno(conn, tentativa["id"], pergunta_id)
    if r is None:
        abort(404, description="Questão não faz parte desta tentativa.")
    if marcar is not None:
        db.run(conn, "UPDATE respostas SET marcada_revisao = ? WHERE id = ?", [1 if marcar else 0, r["id"]])
    if alternativa_id is not None:
        if not db.q1(conn, "SELECT 1 FROM alternativas WHERE id = ? AND pergunta_id = ?",
                     [alternativa_id, pergunta_id]):
            abort(400, description="Alternativa inválida.")
        db.run(conn, "UPDATE respostas SET alternativa_id = ? WHERE id = ?", [alternativa_id, r["id"]])


def resumo_respostas(conn, tentativa_id: int) -> dict:
    linhas = db.q(conn, "SELECT alternativa_id, marcada_revisao FROM respostas WHERE tentativa_id = ?"
                        " ORDER BY ordem, id", [tentativa_id])
    return {"respondidas": sum(1 for r in linhas if r["alternativa_id"] is not None),
            "total": len(linhas),
            "marcadas": [i for i, r in enumerate(linhas) if r["marcada_revisao"]]}


def pendentes(conn, tentativa) -> list[dict]:
    """Tentativas em andamento do usuário (para retomar de onde parou)."""
    return db.q(conn, """
        SELECT t.*, s.nome AS simulado_nome, m.nome AS modulo_nome,
               (SELECT COUNT(*) FROM respostas r WHERE r.tentativa_id = t.id AND r.alternativa_id IS NOT NULL) AS respondidas
        FROM tentativas t
        LEFT JOIN simulados s ON s.id = t.simulado_id
        LEFT JOIN modulos m ON m.id = t.modulo_id
        WHERE t.usuario_id = ? AND t.status = 'em_andamento'
        ORDER BY t.id DESC
    """, [tentativa["usuario_id"]])
