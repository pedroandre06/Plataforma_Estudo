"""CRUD de questões no painel administrativo."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import config
import db
from comum import admin_required

bp = Blueprint("admin_q", __name__)


def _modulos(conn):
    return db.q(conn, """SELECT mo.*, mt.nome AS materia_nome FROM modulos mo
                         JOIN materias mt ON mt.id = mo.materia_id ORDER BY mt.ordem, mo.ordem""")


@bp.route("/admin/perguntas")
@admin_required
def perguntas():
    conn = db.get_db()
    filtros = {"materia": request.args.get("materia", type=int),
               "modulo": request.args.get("modulo", type=int),
               "dificuldade": request.args.get("dificuldade") or "",
               "q": (request.args.get("q") or "").strip()}
    sql = ["""SELECT p.*, mo.nome AS modulo_nome, mo.slug AS modulo_slug, mt.nome AS materia_nome,
                     mt.cor AS materia_cor,
                     (SELECT COUNT(*) FROM alternativas a WHERE a.pergunta_id = p.id) AS n_alternativas
              FROM perguntas p JOIN modulos mo ON mo.id = p.modulo_id
              JOIN materias mt ON mt.id = mo.materia_id WHERE 1 = 1"""]
    params: list = []
    if filtros["materia"]:
        sql.append("AND mt.id = ?")
        params.append(filtros["materia"])
    if filtros["modulo"]:
        sql.append("AND mo.id = ?")
        params.append(filtros["modulo"])
    if filtros["dificuldade"]:
        sql.append("AND p.dificuldade = ?")
        params.append(filtros["dificuldade"])
    if filtros["q"]:
        # lower() dos dois lados: no SQLite o LIKE ja ignora caixa (ASCII), no Postgres nao.
        sql.append("AND (lower(p.enunciado) LIKE lower(?) OR lower(p.topico) LIKE lower(?))")
        params += [f"%{filtros['q'].lower()}%"] * 2
    sql.append("ORDER BY mt.ordem, mo.ordem, p.id LIMIT 300")
    return render_template("admin_perguntas.html", filtros=filtros,
                           perguntas=db.q(conn, " ".join(sql), params),
                           materias=db.q(conn, "SELECT * FROM materias ORDER BY ordem"),
                           modulos=_modulos(conn))


@bp.route("/admin/pergunta/nova", methods=["GET", "POST"])
@admin_required
def pergunta_nova():
    return _formulario(None)


@bp.route("/admin/pergunta/<int:pid>/editar", methods=["GET", "POST"])
@admin_required
def pergunta_editar(pid):
    p = db.q1(db.get_db(), "SELECT * FROM perguntas WHERE id = ?", [pid])
    if not p:
        abort(404, description="Questão não encontrada.")
    return _formulario(p)


def _formulario(pergunta):
    conn = db.get_db()
    if request.method == "POST":
        modulo_id = request.form.get("modulo_id", type=int)
        enunciado = (request.form.get("enunciado") or "").strip()
        textos = [(i, t.strip()) for i, t in enumerate(request.form.getlist("alternativa")) if t.strip()]
        correta = request.form.get("correta", type=int)
        if not modulo_id or not enunciado or len(textos) < 2 or correta is None \
                or not any(i == correta for i, _ in textos):
            flash("Preencha módulo, enunciado, ao menos 2 alternativas e marque a correta.", "erro")
            return redirect(request.url)
        campos = [modulo_id, enunciado, request.form.get("tipo") or "multipla",
                  request.form.get("dificuldade") or "medio",
                  (request.form.get("topico") or "").strip() or None,
                  (request.form.get("explicacao") or "").strip() or None,
                  (request.form.get("referencia") or "").strip() or None]
        if pergunta:
            pid = pergunta["id"]
            db.run(conn, """UPDATE perguntas SET modulo_id = ?, enunciado = ?, tipo = ?, dificuldade = ?,
                            topico = ?, explicacao = ?, referencia = ? WHERE id = ?""", campos + [pid])
            db.run(conn, "DELETE FROM alternativas WHERE pergunta_id = ?", [pid])
        else:
            pid = db.run(conn, """INSERT INTO perguntas (modulo_id, enunciado, tipo, dificuldade, topico,
                            explicacao, referencia) VALUES (?,?,?,?,?,?,?)""", campos)
        for ordem, (indice, texto) in enumerate(textos):
            db.run(conn, "INSERT INTO alternativas (pergunta_id, texto, correta, ordem) VALUES (?,?,?,?)",
                   [pid, texto, 1 if indice == correta else 0, ordem])
        flash("Questão salva com sucesso.", "ok")
        return redirect(url_for("admin_q.perguntas"))
    return render_template("admin_pergunta_form.html", pergunta=pergunta, modulos=_modulos(conn),
                           alternativas=db.q(conn, "SELECT * FROM alternativas WHERE pergunta_id = ?"
                                                   " ORDER BY ordem", [pergunta["id"]])
                           if pergunta else [])


@bp.route("/admin/pergunta/<int:pid>/excluir", methods=["POST"])
@admin_required
def pergunta_excluir(pid):
    conn = db.get_db()
    if request.form.get("definitivo"):
        db.run(conn, "DELETE FROM perguntas WHERE id = ?", [pid])
        flash("Questão excluída definitivamente.", "ok")
    else:
        db.run(conn, "UPDATE perguntas SET ativo = 0 WHERE id = ?", [pid])
        flash("Questão desativada (é possível reativar depois).", "ok")
    return redirect(url_for("admin_q.perguntas"))


@bp.route("/admin/pergunta/<int:pid>/ativar", methods=["POST"])
@admin_required
def pergunta_ativar(pid):
    db.run(db.get_db(), "UPDATE perguntas SET ativo = 1 WHERE id = ?", [pid])
    flash("Questão reativada.", "ok")
    return redirect(url_for("admin_q.perguntas"))
