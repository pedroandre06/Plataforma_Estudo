"""Dashboard e listagem de matérias."""
from __future__ import annotations

from flask import Blueprint, abort, render_template

import db
from comum import login_required, usuario_atual

bp = Blueprint("geral", __name__)


@bp.route("/")
@login_required
def dashboard():
    usuario = usuario_atual()
    conn = db.get_db()
    uid = usuario["id"]
    materias = db.q(conn, """
        SELECT mt.*,
               (SELECT COUNT(*) FROM modulos m WHERE m.materia_id = mt.id AND m.ativo = 1) AS n_modulos,
               (SELECT COUNT(*) FROM perguntas p JOIN modulos m ON m.id = p.modulo_id
                 WHERE m.materia_id = mt.id AND p.ativo = 1) AS n_perguntas,
               (SELECT COUNT(*) FROM progresso pr JOIN modulos m ON m.id = pr.modulo_id
                 WHERE m.materia_id = mt.id AND pr.usuario_id = ? AND pr.status = 'concluido') AS concluidos,
               (SELECT ROUND(AVG(pr.melhor_nota), 1) FROM progresso pr JOIN modulos m ON m.id = pr.modulo_id
                 WHERE m.materia_id = mt.id AND pr.usuario_id = ? AND pr.melhor_nota IS NOT NULL) AS media
        FROM materias mt WHERE mt.ativo = 1 ORDER BY mt.ordem
    """, [uid, uid])
    stats = db.q1(conn, """
        SELECT COUNT(*) AS tentativas, ROUND(AVG(nota), 1) AS media, MAX(nota) AS melhor,
               COALESCE(SUM(acertos), 0) AS acertos, COALESCE(SUM(total), 0) AS respondidas
        FROM tentativas WHERE usuario_id = ? AND status = 'entregue'
    """, [uid])
    recentes = db.q(conn, """
        SELECT t.*, s.nome AS simulado_nome, m.nome AS modulo_nome,
               mt.nome AS materia_nome, mt.cor AS materia_cor
        FROM tentativas t
        LEFT JOIN simulados s ON s.id = t.simulado_id
        LEFT JOIN modulos m ON m.id = t.modulo_id
        LEFT JOIN materias mt ON mt.id = m.materia_id
        WHERE t.usuario_id = ? AND t.status = 'entregue' ORDER BY t.id DESC LIMIT 6
    """, [uid])
    em_andamento = db.q(conn, """
        SELECT t.*, s.nome AS simulado_nome, m.nome AS modulo_nome,
               (SELECT COUNT(*) FROM respostas r WHERE r.tentativa_id = t.id
                 AND r.alternativa_id IS NOT NULL) AS respondidas
        FROM tentativas t
        LEFT JOIN simulados s ON s.id = t.simulado_id
        LEFT JOIN modulos m ON m.id = t.modulo_id
        WHERE t.usuario_id = ? AND t.status = 'em_andamento' ORDER BY t.id DESC LIMIT 4
    """, [uid])
    dias = {r["dia"] for r in db.q(conn, """
        SELECT DISTINCT substr(inicio_em, 1, 10) AS dia FROM tentativas WHERE usuario_id = ?
        ORDER BY dia DESC LIMIT 30
    """, [uid])}
    return render_template("dashboard.html", materias=materias, stats=stats, recentes=recentes,
                           em_andamento=em_andamento, sequencia=len(dias))


@bp.route("/materia/<slug>")
@login_required
def materia(slug):
    usuario = usuario_atual()
    conn = db.get_db()
    m = db.q1(conn, "SELECT * FROM materias WHERE slug = ?", [slug])
    if not m:
        abort(404, description="Matéria não encontrada.")
    modulos = db.q(conn, """
        SELECT mo.*, pr.status AS status, pr.melhor_nota AS melhor_nota, pr.tentativas AS tentativas,
               (SELECT COUNT(*) FROM perguntas p WHERE p.modulo_id = mo.id AND p.ativo = 1) AS n_perguntas,
               (SELECT COUNT(*) FROM flashcards f WHERE f.modulo_id = mo.id) AS n_flashcards
        FROM modulos mo
        LEFT JOIN progresso pr ON pr.modulo_id = mo.id AND pr.usuario_id = ?
        WHERE mo.materia_id = ? AND mo.ativo = 1 ORDER BY mo.ordem
    """, [usuario["id"], m["id"]])
    simulados = db.q(conn, """
        SELECT s.*, (SELECT COUNT(*) FROM simulado_questoes sq WHERE sq.simulado_id = s.id) AS n_fixas
        FROM simulados s
        WHERE s.ativo = 1 AND (s.tipo <> 'materia' OR EXISTS (
              SELECT 1 FROM simulado_materias sm WHERE sm.simulado_id = s.id AND sm.materia_id = ?))
        ORDER BY s.tipo, s.id
    """, [m["id"]])
    return render_template("materia.html", materia=m, modulos=modulos,
                           total_perguntas=sum(x["n_perguntas"] for x in modulos),
                           concluidos=sum(1 for x in modulos if x["status"] == "concluido"),
                           simulados=simulados)
