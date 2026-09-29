"""Painel administrativo e gestão de usuários."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

import db
from comum import admin_required

bp = Blueprint("admin", __name__)


@bp.route("/admin")
@admin_required
def painel():
    conn = db.get_db()
    stats = db.q1(conn, """
        SELECT (SELECT COUNT(*) FROM usuarios) AS usuarios,
               (SELECT COUNT(*) FROM usuarios WHERE ativo = 1) AS ativos,
               (SELECT COUNT(*) FROM perguntas WHERE ativo = 1) AS perguntas,
               (SELECT COUNT(*) FROM modulos) AS modulos,
               (SELECT COUNT(*) FROM tentativas WHERE status = 'entregue') AS tentativas,
               (SELECT COUNT(*) FROM simulados) AS simulados
    """)
    por_materia = db.q(conn, """
        SELECT mt.nome, mt.cor,
               (SELECT COUNT(*) FROM modulos m WHERE m.materia_id = mt.id) AS modulos,
               (SELECT COUNT(*) FROM perguntas p JOIN modulos m ON m.id = p.modulo_id
                 WHERE m.materia_id = mt.id) AS perguntas,
               (SELECT ROUND(AVG(t.nota), 1) FROM tentativas t JOIN modulos m ON m.id = t.modulo_id
                 WHERE m.materia_id = mt.id AND t.status = 'entregue') AS media
        FROM materias mt ORDER BY mt.ordem
    """)
    usuarios = db.q(conn, """
        SELECT u.*, (SELECT COUNT(*) FROM tentativas t WHERE t.usuario_id = u.id) AS tentativas,
               (SELECT ROUND(AVG(t.nota), 1) FROM tentativas t WHERE t.usuario_id = u.id
                 AND t.status = 'entregue') AS media
        FROM usuarios u ORDER BY u.id
    """)
    return render_template("admin.html", stats=stats, por_materia=por_materia, usuarios=usuarios)


@bp.route("/admin/usuario/<int:uid>", methods=["POST"])
@admin_required
def usuario_acao(uid):
    conn = db.get_db()
    alvo = db.q1(conn, "SELECT * FROM usuarios WHERE id = ?", [uid])
    if not alvo:
        abort(404, description="Usuário não encontrado.")
    acao = request.form.get("acao")
    if acao == "alternar_ativo":
        db.run(conn, "UPDATE usuarios SET ativo = ? WHERE id = ?", [0 if alvo["ativo"] else 1, uid])
        flash(f"Usuário {alvo['usuario']} {'desativado' if alvo['ativo'] else 'ativado'}.", "ok")
    elif acao == "tornar_admin":
        db.run(conn, "UPDATE usuarios SET papel = 'admin' WHERE id = ?", [uid])
        flash(f"{alvo['usuario']} agora é administrador.", "ok")
    elif acao == "tornar_aluno":
        db.run(conn, "UPDATE usuarios SET papel = 'aluno' WHERE id = ?", [uid])
        flash(f"{alvo['usuario']} agora é aluno.", "ok")
    elif acao == "resetar_senha":
        nova = (request.form.get("nova_senha") or "1234").strip()
        db.run(conn, """UPDATE usuarios SET senha_hash = ?, tentativas_falhas = 0, bloqueado_ate = NULL
                        WHERE id = ?""", [generate_password_hash(nova), uid])
        flash(f"Senha de {alvo['usuario']} redefinida.", "ok")
    return redirect(url_for("admin.painel"))
