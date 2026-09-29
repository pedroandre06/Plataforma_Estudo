"""Resultado de tentativas (quiz e simulado) e ações pós-correção."""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

import correcao
import db
import motor
import sessao_tentativa as sessao
from comum import login_required, usuario_atual

bp = Blueprint("resultado", __name__)


@bp.route("/tentativa/<int:tid>/confirmar")
@login_required
def confirmar(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    return render_template("quiz_confirmar.html", tentativa=t, questoes=sessao.questoes(conn, t, mapa),
                           regras=regras, resumo=sessao.resumo_respostas(conn, tid))


@bp.route("/tentativa/<int:tid>/resultado")
@login_required
def resultado(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    if t["status"] == "em_andamento":
        return redirect(url_for("quiz.executar", tid=tid))
    lista = sessao.questoes(conn, t, mapa)
    erradas = [q["pergunta"]["id"] for q in lista if q["correta"] == 0 or q["escolhida"] is None]
    modulos = sorted({(q["pergunta"]["modulo_slug"], q["pergunta"]["modulo_nome"]) for q in lista})
    return render_template("resultado.html", tentativa=t, questoes=lista, modulos=modulos, erradas=erradas,
                           analise=correcao.analise(conn, tid), regras=regras,
                           mostrar=regras.get("mostrar_gabarito", "fim") != "nunca")


@bp.route("/tentativa/<int:tid>/refazer-erradas", methods=["POST"])
@login_required
def refazer_erradas(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    faltantes = [r["pergunta_id"] for r in db.q(conn, """
        SELECT pergunta_id FROM respostas WHERE tentativa_id = ? AND (correta = 0 OR alternativa_id IS NULL)
    """, [tid])]
    if not faltantes:
        flash("Você não errou nenhuma questão nesta tentativa. Parabéns!", "ok")
        return redirect(url_for("resultado.resultado", tid=tid))
    novo = motor.criar_tentativa(conn, usuario["id"], modo="revisao", modulo_id=t["modulo_id"],
                                 pergunta_ids=faltantes, mostrar_gabarito="imediato")
    return redirect(url_for("quiz.executar", tid=novo))


@bp.route("/tentativa/<int:tid>/abandonar", methods=["POST"])
@login_required
def abandonar(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    sessao.carregar(conn, tid, usuario["id"])
    db.run(conn, "DELETE FROM tentativas WHERE id = ?", [tid])
    flash("Tentativa descartada.", "aviso")
    slug = request.form.get("slug")
    return redirect(url_for("aula.modulo", slug=slug, aba="praticar") if slug
                    else url_for("geral.dashboard"))
