"""Criação de simulado personalizado pelo aluno."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

import config
import db
import motor
from comum import login_required, usuario_atual

bp = Blueprint("sim_cfg", __name__)


@bp.route("/simulados/novo", methods=["GET", "POST"])
@login_required
def novo():
    usuario = usuario_atual()
    conn = db.get_db()
    if request.method == "POST":
        materias = [int(x) for x in request.form.getlist("materias")]
        modulos = [int(x) for x in request.form.getlist("modulos")]
        dificuldade = request.form.get("dificuldade") or "todas"
        n = max(5, min(int(request.form.get("n_questoes") or 20), 60))
        tempo = int(request.form.get("tempo_min") or 0) or None
        corte = float(request.form.get("nota_corte") or config.NOTA_CORTE_PADRAO)
        embaralhar = 1 if request.form.get("embaralhar") else 0
        gabarito = request.form.get("mostrar_gabarito") or "fim"
        if not materias and not modulos:
            flash("Escolha pelo menos uma matéria ou um módulo.", "erro")
            return redirect(url_for("sim_cfg.novo"))
        sid = db.run(conn, """INSERT INTO simulados (nome, tipo, descricao, criado_por, n_questoes,
                        tempo_min, nota_corte, embaralhar, mostrar_gabarito, dificuldade, publico)
                        VALUES (?, 'personalizado', ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                     [(request.form.get("nome") or "Simulado personalizado").strip(),
                      "Simulado criado por " + usuario["nome"], usuario["id"], n, tempo or 0, corte,
                      embaralhar, gabarito, dificuldade])
        for mid in materias:
            db.run(conn, "INSERT OR IGNORE INTO simulado_materias (simulado_id, materia_id) VALUES (?,?)",
                   [sid, mid])
        if modulos:
            for pid in motor.ids_disponiveis(conn, modulo_ids=modulos, dificuldade=dificuldade):
                db.run(conn, """INSERT OR IGNORE INTO simulado_questoes (simulado_id, pergunta_id)
                                VALUES (?,?)""", [sid, pid])
        tid = motor.criar_tentativa(conn, usuario["id"], modo="simulado", simulado_id=sid, n_questoes=n,
                                    tempo_min=tempo, nota_corte=corte, dificuldade=dificuldade,
                                    embaralhar=bool(embaralhar), mostrar_gabarito=gabarito,
                                    materia_ids=materias or None, modulo_ids=modulos or None)
        return redirect(url_for("simulado_exec.executar", tid=tid))

    materias = db.q(conn, """SELECT mt.*, (SELECT COUNT(*) FROM perguntas p JOIN modulos m
                          ON m.id = p.modulo_id WHERE m.materia_id = mt.id AND p.ativo = 1) AS n_perguntas
                          FROM materias mt WHERE mt.ativo = 1 ORDER BY mt.ordem""")
    modulos = db.q(conn, """SELECT mo.id, mo.nome, mt.nome AS materia_nome,
                            (SELECT COUNT(*) FROM perguntas p WHERE p.modulo_id = mo.id AND p.ativo = 1) AS n
                            FROM modulos mo JOIN materias mt ON mt.id = mo.materia_id
                            WHERE mo.ativo = 1 ORDER BY mt.ordem, mo.ordem""")
    return render_template("simulado_novo.html", materias=materias, modulos=modulos)
