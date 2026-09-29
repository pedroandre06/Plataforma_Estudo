"""Montagem de provas oficiais (questões fixas escolhidas pelo administrador)."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

import db
from comum import admin_required, usuario_atual

bp = Blueprint("admin_prova", __name__)


@bp.route("/admin/prova/nova", methods=["GET", "POST"])
@admin_required
def prova_nova():
    usuario = usuario_atual()
    conn = db.get_db()
    if request.method == "POST":
        nome = (request.form.get("nome") or "Prova oficial").strip()
        ids = [int(x) for x in request.form.getlist("pergunta_id")]
        if not ids:
            flash("Selecione ao menos uma questão para a prova.", "erro")
            return redirect(url_for("admin_prova.prova_nova"))
        sid = db.run(conn, """INSERT INTO simulados (nome, tipo, descricao, criado_por, n_questoes,
                        tempo_min, nota_corte, max_tentativas, embaralhar, mostrar_gabarito, publico)
                        VALUES (?, 'oficial', ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                     [nome, request.form.get("descricao") or "Prova oficial criada pelo administrador",
                      usuario["id"], len(ids), int(request.form.get("tempo_min") or 60),
                      float(request.form.get("nota_corte") or 6.0),
                      int(request.form.get("max_tentativas") or 1),
                      1 if request.form.get("embaralhar") else 0,
                      request.form.get("mostrar_gabarito") or "fim"])
        for ordem, pid in enumerate(ids):
            db.run(conn, """INSERT OR IGNORE INTO simulado_questoes (simulado_id, pergunta_id, ordem)
                            VALUES (?,?,?)""", [sid, pid, ordem])
        marcadores = ",".join("?" * len(ids))
        for linha in db.q(conn, f"""SELECT DISTINCT m.materia_id FROM perguntas p
                                    JOIN modulos m ON m.id = p.modulo_id
                                    WHERE p.id IN ({marcadores})""", ids):
            db.run(conn, "INSERT OR IGNORE INTO simulado_materias (simulado_id, materia_id) VALUES (?,?)",
                   [sid, linha["materia_id"]])
        flash(f"Prova oficial '{nome}' criada com {len(ids)} questões.", "ok")
        return redirect(url_for("simulados.lista"))

    filtros = {"materia": request.args.get("materia", type=int),
               "q": (request.args.get("q") or "").strip()}
    sql = ["""SELECT p.*, mo.nome AS modulo_nome, mt.nome AS materia_nome, mt.cor AS materia_cor
              FROM perguntas p JOIN modulos mo ON mo.id = p.modulo_id
              JOIN materias mt ON mt.id = mo.materia_id WHERE p.ativo = 1"""]
    params: list = []
    if filtros["materia"]:
        sql.append("AND mt.id = ?")
        params.append(filtros["materia"])
    if filtros["q"]:
        # lower() dos dois lados para a busca ignorar caixa tambem no PostgreSQL.
        sql.append("AND lower(p.enunciado) LIKE lower(?)")
        params.append(f"%{filtros['q'].lower()}%")
    sql.append("ORDER BY mt.ordem, mo.ordem, p.id LIMIT 400")
    provas = db.q(conn, """SELECT s.*, (SELECT COUNT(*) FROM simulado_questoes sq
                          WHERE sq.simulado_id = s.id) AS n_fixas
                          FROM simulados s WHERE s.tipo = 'oficial' ORDER BY s.id DESC""")
    return render_template("admin_prova.html", perguntas=db.q(conn, " ".join(sql), params),
                           filtros=filtros, provas=provas,
                           materias=db.q(conn, "SELECT * FROM materias ORDER BY ordem"))


@bp.route("/admin/prova/<int:sid>/excluir", methods=["POST"])
@admin_required
def prova_excluir(sid):
    db.run(db.get_db(), "DELETE FROM simulados WHERE id = ? AND tipo = 'oficial'", [sid])
    flash("Prova oficial removida.", "ok")
    return redirect(url_for("admin_prova.prova_nova"))
