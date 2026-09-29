"""Perfil, histórico de tentativas, flashcards e ligação com os materiais."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
from comum import login_required, usuario_atual

bp = Blueprint("extra", __name__)


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    usuario = usuario_atual()
    conn = db.get_db()
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        email = (request.form.get("email") or "").strip() or None
        atual = request.form.get("atual") or ""
        nova = request.form.get("nova") or ""
        confirma = request.form.get("confirma") or ""
        if nome:
            db.run(conn, "UPDATE usuarios SET nome = ?, email = ? WHERE id = ?",
                   [nome, email, usuario["id"]])
            flash("Dados atualizados.", "ok")
        if nova or atual:
            if not check_password_hash(usuario["senha_hash"], atual):
                flash("Senha atual incorreta.", "erro")
            elif len(nova) < config.MIN_SENHA:
                flash(f"A nova senha deve ter ao menos {config.MIN_SENHA} caracteres.", "erro")
            elif nova != confirma:
                flash("A confirmação não confere com a nova senha.", "erro")
            else:
                db.run(conn, "UPDATE usuarios SET senha_hash = ? WHERE id = ?",
                       [generate_password_hash(nova), usuario["id"]])
                flash("Senha alterada com sucesso.", "ok")
        return redirect(url_for("extra.perfil"))
    estatisticas = db.q1(conn, """
        SELECT (SELECT COUNT(*) FROM tentativas WHERE usuario_id = ?) AS tentativas,
               (SELECT COUNT(*) FROM progresso WHERE usuario_id = ? AND status = 'concluido') AS concluidos,
               (SELECT COUNT(*) FROM respostas r JOIN tentativas t ON t.id = r.tentativa_id
                 WHERE t.usuario_id = ? AND r.correta = 1) AS acertos
    """, [usuario["id"]] * 3)
    return render_template("perfil.html", stats=estatisticas)


@bp.route("/historico")
@login_required
def historico():
    usuario = usuario_atual()
    conn = db.get_db()
    filtro = request.args.get("modo") or "todos"
    sql = ["""SELECT t.*, s.nome AS simulado_nome, m.nome AS modulo_nome,
                     mt.nome AS materia_nome, mt.cor AS materia_cor
              FROM tentativas t
              LEFT JOIN simulados s ON s.id = t.simulado_id
              LEFT JOIN modulos m ON m.id = t.modulo_id
              LEFT JOIN materias mt ON mt.id = m.materia_id
              WHERE t.usuario_id = ?"""]
    params: list = [usuario["id"]]
    if filtro != "todos":
        sql.append("AND t.modo = ?")
        params.append(filtro)
    sql.append("ORDER BY t.id DESC LIMIT 200")
    lista = db.q(conn, " ".join(sql), params)
    evolucao = [dict(r) for r in db.q(conn, """
        SELECT id, nota, modo FROM tentativas
        WHERE usuario_id = ? AND status = 'entregue' AND nota IS NOT NULL ORDER BY id ASC LIMIT 60
    """, [usuario["id"]])]
    resumo = db.q1(conn, """
        SELECT COUNT(*) AS n, ROUND(AVG(nota), 1) AS media, MAX(nota) AS melhor,
               SUM(CASE WHEN aprovado = 1 THEN 1 ELSE 0 END) AS aprovadas
        FROM tentativas WHERE usuario_id = ? AND status = 'entregue'
    """, [usuario["id"]])
    return render_template("historico.html", tentativas=lista, evolucao=evolucao, resumo=resumo,
                           filtro=filtro)


@bp.route("/modulo/<slug>/flashcards")
@login_required
def flashcards(slug):
    conn = db.get_db()
    mo = db.q1(conn, """SELECT mo.*, mt.nome AS materia_nome, mt.cor AS materia_cor
                        FROM modulos mo JOIN materias mt ON mt.id = mo.materia_id WHERE mo.slug = ?""",
               [slug])
    if not mo:
        abort(404, description="Módulo não encontrado.")
    return render_template("flashcards.html", modulo=mo,
                           flashcards=db.q(conn, "SELECT * FROM flashcards WHERE modulo_id = ?"
                                                 " ORDER BY ordem, id", [mo["id"]]))


@bp.route("/busca")
@login_required
def busca():
    termo = (request.args.get("q") or "").strip()
    conn = db.get_db()
    resultados = []
    if termo:
        like = f"%{termo}%"
        resultados = db.q(conn, """
            SELECT p.id, p.enunciado, p.topico, p.dificuldade, mo.nome AS modulo_nome,
                   mo.slug AS modulo_slug, mt.nome AS materia_nome, mt.cor AS materia_cor
            FROM perguntas p
            JOIN modulos mo ON mo.id = p.modulo_id
            JOIN materias mt ON mt.id = mo.materia_id
            WHERE p.ativo = 1 AND (p.enunciado LIKE ? OR p.topico LIKE ?)
            ORDER BY mo.ordem LIMIT 60
        """, [like, like])
    return render_template("busca.html", termo=termo, resultados=resultados)
