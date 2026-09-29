"""Quiz de módulo: treino (feedback imediato), prova e revisão."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

import correcao
import db
import motor
import sessao_tentativa as sessao
from comum import login_required, segundos_ate, usuario_atual

bp = Blueprint("quiz", __name__)


def _modulo(conn, slug):
    mo = db.q1(conn, """SELECT mo.*, mt.nome AS materia_nome, mt.cor AS materia_cor
                        FROM modulos mo JOIN materias mt ON mt.id = mo.materia_id WHERE mo.slug = ?""",
               [slug])
    if not mo or not mo["ativo"]:
        abort(404, description="Módulo não encontrado.")
    return mo


@bp.route("/modulo/<slug>/quiz/iniciar", methods=["POST"])
@login_required
def iniciar(slug):
    usuario = usuario_atual()
    conn = db.get_db()
    mo = _modulo(conn, slug)
    modo = request.form.get("modo") or "treino"
    if modo not in motor.MODOS_TREINO:
        abort(400, description="Modo de quiz inválido.")
    n = max(5, min(int(request.form.get("n") or 10), 40))
    if modo == "revisao":
        ids = motor.ids_de_revisao(conn, usuario["id"], [mo["id"]])
        if not ids:
            flash("Você ainda não tem questões erradas neste módulo. Faça um treino primeiro!", "aviso")
            return redirect(url_for("aula.modulo", slug=slug, aba="praticar"))
        tid = motor.criar_tentativa(conn, usuario["id"], modo="revisao", modulo_id=mo["id"],
                                    pergunta_ids=ids, mostrar_gabarito="imediato")
    elif modo == "prova":
        tid = motor.criar_tentativa(conn, usuario["id"], modo="prova", modulo_id=mo["id"], n_questoes=n,
                                    tempo_min=int(request.form.get("tempo") or 0) or None,
                                    modulo_ids=[mo["id"]])
    else:
        tid = motor.criar_tentativa(conn, usuario["id"], modo="treino", modulo_id=mo["id"], n_questoes=n,
                                    mostrar_gabarito="imediato", modulo_ids=[mo["id"]])
    return redirect(url_for("quiz.executar", tid=tid))


@bp.route("/tentativa/<int:tid>")
@login_required
def executar(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    if t["status"] != "em_andamento":
        return redirect(url_for("resultado.resultado", tid=tid))
    lista = sessao.questoes(conn, t, mapa)
    if not lista:
        abort(400, description="Esta tentativa não possui questões.")

    if t["modo"] == "treino":
        feedback = request.args.get("feedback", type=int)
        alvo = feedback
        if alvo is None:
            pendente = next((q for q in lista if q["escolhida"] is None), None)
            alvo = pendente["pergunta"]["id"] if pendente else None
        indice = next((i for i, q in enumerate(lista) if q["pergunta"]["id"] == alvo), None)
        if indice is None:
            return redirect(url_for("resultado.confirmar", tid=tid))
        atual = lista[indice]
        if feedback is not None and atual["escolhida"] is not None:
            certa = next((a for a in atual["alternativas"] if a["correta"]), None)
            atual["correta"] = 1 if (certa and certa["id"] == atual["escolhida"]) else 0
        return render_template("quiz_treino.html", tentativa=t, questao=atual, indice=indice,
                               total=len(lista), feedback=feedback,
                               respondidas=sum(1 for q in lista if q["escolhida"] is not None))

    return render_template("quiz_prova.html", tentativa=t, questoes=lista, regras=regras,
                           restante=segundos_ate(t["limite_em"]) if t["limite_em"] else None,
                           resumo=sessao.resumo_respostas(conn, tid))


@bp.route("/tentativa/<int:tid>/responder", methods=["POST"])
@login_required
def responder(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"], exigir_andamento=True)
    pergunta_id = request.form.get("pergunta_id", type=int)
    if pergunta_id:
        sessao.salvar_resposta(conn, t, pergunta_id, request.form.get("alternativa_id", type=int))
    if t["modo"] == "treino":
        return redirect(url_for("quiz.executar", tid=tid, feedback=pergunta_id))
    flash("Resposta registrada.", "ok")
    return redirect(url_for("quiz.executar", tid=tid))


@bp.route("/tentativa/<int:tid>/entregar", methods=["POST"])
@login_required
def entregar(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t, mapa, regras = sessao.carregar(conn, tid, usuario["id"])
    if t["status"] == "em_andamento":
        for chave, valor in request.form.items():
            if chave.startswith("p_") and valor.isdigit():
                sessao.salvar_resposta(conn, t, int(chave[2:]), int(valor))
        correcao.corrigir(conn, t)
    return redirect(url_for("resultado.resultado", tid=tid))
