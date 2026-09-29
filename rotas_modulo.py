"""Página do módulo (resumo, material original, prática), anotações e PDF."""
from __future__ import annotations

import os

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for

import correcao
import db
from comum import agora, login_required, usuario_atual

bp = Blueprint("aula", __name__)


@bp.route("/modulo/<slug>")
@login_required
def modulo(slug):
    usuario = usuario_atual()
    conn = db.get_db()
    mo = db.q1(conn, """
        SELECT mo.*, mt.nome AS materia_nome, mt.slug AS materia_slug, mt.cor AS materia_cor
        FROM modulos mo JOIN materias mt ON mt.id = mo.materia_id WHERE mo.slug = ?
    """, [slug])
    if not mo or not mo["ativo"]:
        abort(404, description="Módulo não encontrado.")
    correcao.tocar_modulo(conn, usuario["id"], mo["id"])
    # Topicos mais errados do modulo. O agregado vem de um JOIN (e nao de subconsulta
    # correlacionada dentro de um GROUP BY), forma aceita pelos dois motores.
    topicos = db.q(conn, """
        SELECT p.topico, COUNT(DISTINCT p.id) AS n, COUNT(et.id) AS erros
        FROM perguntas p
        LEFT JOIN respostas er ON er.pergunta_id = p.id AND er.correta = 0
        LEFT JOIN tentativas et ON et.id = er.tentativa_id AND et.usuario_id = ?
        WHERE p.modulo_id = ? AND p.ativo = 1 AND p.topico IS NOT NULL
        GROUP BY p.topico ORDER BY erros DESC, p.topico LIMIT 30
    """, [usuario["id"], mo["id"]])
    return render_template(
        "modulo.html", modulo=mo, topicos=topicos,
        progresso=db.q1(conn, "SELECT * FROM progresso WHERE usuario_id = ? AND modulo_id = ?",
                        [usuario["id"], mo["id"]]),
        n_perguntas=db.q1(conn, "SELECT COUNT(*) AS n FROM perguntas WHERE modulo_id = ? AND ativo = 1",
                          [mo["id"]])["n"],
        n_flashcards=db.q1(conn, "SELECT COUNT(*) AS n FROM flashcards WHERE modulo_id = ?",
                           [mo["id"]])["n"],
        anotacao=db.q1(conn, "SELECT * FROM anotacoes WHERE usuario_id = ? AND modulo_id = ?",
                       [usuario["id"], mo["id"]]),
        tentativas=db.q(conn, """SELECT * FROM tentativas WHERE usuario_id = ? AND modulo_id = ?
                                 AND status = 'entregue' ORDER BY id DESC LIMIT 5""",
                        [usuario["id"], mo["id"]]),
        tem_pdf=bool(mo["pdf_origem"] and os.path.exists(mo["pdf_origem"])),
        aba=request.args.get("aba", "resumo"))


@bp.route("/modulo/<slug>/anotacao", methods=["POST"])
@login_required
def salvar_anotacao(slug):
    usuario = usuario_atual()
    conn = db.get_db()
    mo = db.q1(conn, "SELECT id FROM modulos WHERE slug = ?", [slug])
    if not mo:
        abort(404, description="Módulo não encontrado.")
    texto = (request.form.get("texto") or "").strip()
    existente = db.q1(conn, "SELECT id FROM anotacoes WHERE usuario_id = ? AND modulo_id = ?",
                      [usuario["id"], mo["id"]])
    if existente:
        db.run(conn, "UPDATE anotacoes SET texto = ?, atualizado_em = ? WHERE id = ?",
               [texto, agora(), existente["id"]])
    else:
        db.run(conn, "INSERT INTO anotacoes (usuario_id, modulo_id, texto) VALUES (?,?,?)",
               [usuario["id"], mo["id"], texto])
    flash("Anotação salva.", "ok")
    return redirect(url_for("aula.modulo", slug=slug, aba="resumo"))


@bp.route("/material/<int:modulo_id>")
@login_required
def material(modulo_id):
    conn = db.get_db()
    mo = db.q1(conn, "SELECT * FROM modulos WHERE id = ?", [modulo_id])
    if not mo or not mo["pdf_origem"] or not os.path.exists(mo["pdf_origem"]):
        abort(404, description="Material original (PDF) não encontrado no disco.")
    return send_file(mo["pdf_origem"], mimetype="application/pdf", as_attachment=False,
                     download_name=f"{mo['nome']}.pdf")
