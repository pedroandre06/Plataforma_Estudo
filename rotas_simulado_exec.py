"""Execução do simulado/prova: navegação, auto-save e correção."""
from __future__ import annotations

from flask import (Blueprint, flash, jsonify, redirect, render_template, request, url_for)

import correcao
import db
import sessao_tentativa as sessao
from comum import login_required, segundos_ate, usuario_atual

bp = Blueprint("simulado_exec", __name__)


@bp.route("/simulado/<int:tid>")
@login_required
def executar(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    if t["status"] != "em_andamento":
        return redirect(url_for("simulado_exec.resultado", tid=tid))
    return render_template("simulado_exec.html", tentativa=t, questoes=sessao.questoes(conn, t, mapa),
                           regras=regras, restante=segundos_ate(t["limite_em"]) if t["limite_em"] else None,
                           resumo=sessao.resumo_respostas(conn, tid),
                           simulado=db.q1(conn, "SELECT * FROM simulados WHERE id = ?",
                                          [t["simulado_id"]]) if t["simulado_id"] else None)


@bp.route("/api/simulado/<int:tid>/resposta", methods=["POST"])
@login_required
def api_resposta(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"], exigir_andamento=True)
    data = request.get_json(silent=True) or {}
    # suporta os dois formatos: {"pergunta_id":..,"alternativa_id":..,"marcar":..}
    # e {"respostas": {pergunta_id: alternativa_id}, "marcadas": [..]}
    if "pergunta_id" in data and data.get("pergunta_id"):
        alt = data.get("alternativa_id")
        try:
            alt = int(alt) if alt not in (None, "") else None
        except (TypeError, ValueError):
            alt = None
        marcar = data.get("marcar")
        if marcar is not None:
            try:
                marcar = bool(int(marcar))
            except (TypeError, ValueError):
                marcar = bool(marcar)
        sessao.salvar_resposta(conn, t, int(data["pergunta_id"]), alt, marcar)
    for pid, alt in (data.get("respostas") or {}).items():
        try:
            alt = int(alt) if alt not in (None, "") else None
        except (TypeError, ValueError):
            continue
        try:
            sessao.salvar_resposta(conn, t, int(pid), alt, None)
        except Exception:
            continue
    for pid in data.get("marcadas") or []:
        try:
            sessao.salvar_resposta(conn, t, int(pid), None, True)
        except Exception:
            continue
    return jsonify({"ok": True, "resumo": sessao.resumo_respostas(conn, tid),
                    "restante": segundos_ate(t["limite_em"]) if t["limite_em"] else None})


@bp.route("/simulado/<int:tid>/entregar", methods=["POST"])
@login_required
def entregar(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    if t["status"] == "em_andamento":
        for chave, valor in request.form.items():
            if chave.startswith("p_") and valor.isdigit():
                sessao.salvar_resposta(conn, t, int(chave[2:]), int(valor))
        expirado = bool(t["limite_em"] and segundos_ate(t["limite_em"]) == 0)
        r = correcao.corrigir(conn, t)
        if expirado:
            db.run(conn, "UPDATE tentativas SET status = 'expirada' WHERE id = ?", [tid])
            flash("Tempo esgotado: o simulado foi entregue automaticamente.", "aviso")
        else:
            flash(f"Entregue: {r['acertos']}/{r['total']} acertos (nota {r['nota']:.1f}).", "ok")
    return redirect(url_for("simulado_exec.resultado", tid=tid))


@bp.route("/simulado/<int:tid>/resultado")
@login_required
def resultado(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    if t["status"] == "em_andamento":
        return redirect(url_for("simulado_exec.executar", tid=tid))
    lista = sessao.questoes(conn, t, mapa)
    anteriores = db.q(conn, """SELECT nota, fim_em, modo FROM tentativas WHERE usuario_id = ?
                               AND simulado_id = ? AND status <> 'em_andamento' AND id <> ?
                               ORDER BY id DESC LIMIT 5""",
                      [usuario["id"], t["simulado_id"], tid]) if t["simulado_id"] else []
    erradas = [q["pergunta"]["id"] for q in lista if q["correta"] == 0 or q["escolhida"] is None]
    return render_template("simulado_resultado.html", tentativa=t, questoes=lista, regras=regras,
                           analise=correcao.analise(conn, tid), erradas=erradas,
                           anteriores=anteriores, mostrar=regras.get("mostrar_gabarito", "fim") != "nunca",
                           simulado=db.q1(conn, "SELECT * FROM simulados WHERE id = ?",
                                          [t["simulado_id"]]) if t["simulado_id"] else None)
