"""Simulados: lista, início (matéria/geral/oficial) e histórico."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, url_for

import db
import motor
from comum import login_required, usuario_atual

bp = Blueprint("simulados", __name__)

ORDEM = "CASE s.tipo WHEN 'materia' THEN 1 WHEN 'geral' THEN 2 WHEN 'oficial' THEN 3 ELSE 4 END"


def _simulado(conn, simulado_id, usuario_id):
    s = db.q1(conn, "SELECT * FROM simulados WHERE id = ? AND ativo = 1", [simulado_id])
    if not s:
        abort(404, description="Simulado não encontrado.")
    feitas = db.q1(conn, """SELECT COUNT(*) AS n FROM tentativas WHERE usuario_id = ? AND simulado_id = ?
                            AND status <> 'em_andamento'""", [usuario_id, simulado_id])["n"]
    if s["max_tentativas"] and feitas >= s["max_tentativas"]:
        return None, feitas
    return s, feitas


def _iniciar(conn, usuario_id, s, pergunta_ids=None):
    if pergunta_ids is None:
        pergunta_ids = [r["pergunta_id"] for r in db.q(
            conn, "SELECT pergunta_id FROM simulado_questoes WHERE simulado_id = ? ORDER BY ordem",
            [s["id"]])]
    materias = [r["materia_id"] for r in db.q(
        conn, "SELECT materia_id FROM simulado_materias WHERE simulado_id = ?", [s["id"]])]
    modo = "oficial" if s["tipo"] == "oficial" else ("reforco" if s["tipo"] == "reforco" else "simulado")
    return motor.criar_tentativa(
        conn, usuario_id, modo=modo, simulado_id=s["id"], pergunta_ids=pergunta_ids or None,
        n_questoes=s["n_questoes"], tempo_min=s["tempo_min"] or None, nota_corte=s["nota_corte"],
        dificuldade=s["dificuldade"], embaralhar=bool(s["embaralhar"]),
        mostrar_gabarito=s["mostrar_gabarito"], materia_ids=materias or None)


@bp.route("/simulados")
@login_required
def lista():
    usuario = usuario_atual()
    conn = db.get_db()
    uid = usuario["id"]
    disponiveis = db.q(conn, f"""
        SELECT s.*, mt.nome AS materia_nome, mt.cor AS materia_cor,
               (SELECT COUNT(*) FROM simulado_questoes sq WHERE sq.simulado_id = s.id) AS n_fixas,
               (SELECT COUNT(*) FROM tentativas t WHERE t.usuario_id = ? AND t.simulado_id = s.id
                 AND t.status <> 'em_andamento') AS feitas,
               (SELECT ROUND(MAX(t.nota), 1) FROM tentativas t WHERE t.usuario_id = ?
                 AND t.simulado_id = s.id AND t.status = 'entregue') AS melhor
        FROM simulados s
        LEFT JOIN materias mt ON mt.id = (SELECT sm.materia_id FROM simulado_materias sm
                                          WHERE sm.simulado_id = s.id LIMIT 1)
        WHERE s.ativo = 1 ORDER BY {ORDEM}, s.id
    """, [uid, uid])
    em_andamento = db.q(conn, """
        SELECT t.*, s.nome AS simulado_nome,
               (SELECT COUNT(*) FROM respostas r WHERE r.tentativa_id = t.id
                 AND r.alternativa_id IS NOT NULL) AS respondidas
        FROM tentativas t LEFT JOIN simulados s ON s.id = t.simulado_id
        WHERE t.usuario_id = ? AND t.status = 'em_andamento' ORDER BY t.id DESC
    """, [uid])
    historico = db.q(conn, """
        SELECT t.*, s.nome AS simulado_nome FROM tentativas t
        LEFT JOIN simulados s ON s.id = t.simulado_id
        WHERE t.usuario_id = ? AND t.simulado_id IS NOT NULL AND t.status IN ('entregue', 'expirada')
        ORDER BY t.id DESC LIMIT 20
    """, [uid])
    return render_template("simulados.html", disponiveis=disponiveis, em_andamento=em_andamento,
                           historico=historico)


@bp.route("/simulados/iniciar/<int:simulado_id>", methods=["POST"])
@login_required
def iniciar(simulado_id):
    usuario = usuario_atual()
    conn = db.get_db()
    s, feitas = _simulado(conn, simulado_id, usuario["id"])
    if s is None:
        flash("Limite de tentativas deste simulado foi atingido.", "aviso")
        return redirect(url_for("simulados.lista"))
    return redirect(url_for("simulado_exec.executar", tid=_iniciar(conn, usuario["id"], s)))


@bp.route("/simulados/reforco", methods=["POST"])
@login_required
def reforco():
    usuario = usuario_atual()
    conn = db.get_db()
    ids = motor.ids_pontos_fracos(conn, usuario["id"])
    if not ids:
        flash("Ainda não há dados suficientes para montar um simulado de reforço.", "aviso")
        return redirect(url_for("simulados.lista"))
    sid = db.run(conn, """INSERT INTO simulados (nome, tipo, descricao, criado_por, n_questoes, tempo_min,
                    nota_corte, embaralhar, mostrar_gabarito, publico)
                    VALUES (?, 'reforco', 'Gerado a partir do seu histórico de erros', ?, ?, 25, ?, 1,
                    'fim', 0)""",
                 ["Reforço de pontos fracos", usuario["id"], len(ids), 6.0])
    tid = motor.criar_tentativa(conn, usuario["id"], modo="reforco", simulado_id=sid, pergunta_ids=ids,
                                tempo_min=25)
    return redirect(url_for("simulado_exec.executar", tid=tid))
