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


def _uid_aluno(conn):
    """Id do usuário padrão (modo sem senha): aceita tentativas antigas migradas."""
    from comum import USUARIO_LIVRE

    linha = db.q1(conn, "SELECT id FROM usuarios WHERE lower(usuario) = lower(?)",
                  [USUARIO_LIVRE])
    return linha["id"] if linha else None


def _salvar_tolerante(conn, tentativa, pergunta_id: int, alternativa_id=None) -> None:
    """Salva a resposta sem 404: ignora pergunta fora da tentativa (dado antigo).

    O treino nunca deve cair numa página de erro por causa de uma questão que
    saiu do banco ou de um form dessincronizado — só segue para a próxima.
    """
    try:
        sessao.salvar_resposta(conn, tentativa, pergunta_id, alternativa_id)
    except Exception:
        return


def _recuperar_ou_recriar(conn, usuario, tid_perdido: int):
    """Devolve um tid válido quando o original sumiu (banco efêmero por instância).

    Estratégia, nesta ordem:
    1. última tentativa em andamento do usuário (retoma de onde parou);
    2. novo treino no mesmo módulo da tentativa perdida — descoberto pelo
       rascunho local do navegador (query ?modulo=<slug> enviada pelo JS);
    3. None (o chamador volta ao painel com aviso).
    """
    from flask import request as req

    em_andamento = db.q1(conn, """SELECT id FROM tentativas WHERE usuario_id = ?
                                  AND status = 'em_andamento' ORDER BY id DESC LIMIT 1""",
                         [usuario["id"]])
    if em_andamento:
        return em_andamento["id"]
    slug = (req.args.get("modulo") or req.form.get("modulo") or "").strip()
    if slug:
        mo = db.q1(conn, "SELECT * FROM modulos WHERE slug = ? AND ativo = 1", [slug])
        if mo:
            return motor.criar_tentativa(conn, usuario["id"], modo="treino",
                                         modulo_id=mo["id"], n_questoes=10,
                                         mostrar_gabarito="imediato",
                                         modulo_ids=[mo["id"]])
    return None


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
    t = db.q1(conn, "SELECT * FROM tentativas WHERE id = ?", [tid])
    if t is None:
        # Banco efêmero (instância nova sem a tentativa): recria um treino
        # equivalente a partir das respostas já renderizadas é impossível, então
        # retoma a última tentativa em andamento ou cria uma nova no módulo.
        tid = _recuperar_ou_recriar(conn, usuario, tid)
        if tid is None:
            flash("Esta tentativa não existe mais neste servidor (banco temporário). "
                  "Inicie um novo treino.", "aviso")
            return redirect(url_for("geral.dashboard"))
        flash("A tentativa original não estava mais neste servidor; "
              "retomei/ iniciei outra para você continuar.", "aviso")
        return redirect(url_for("quiz.executar", tid=tid))
    if t["usuario_id"] != usuario["id"] and t["usuario_id"] != _uid_aluno(conn):
        abort(403, description="Esta tentativa pertence a outro usuário.")
    t, mapa, regras = t, __import__("json").loads(t["questoes_json"] or "{}"), \
        __import__("json").loads(t["config_json"] or "{}")
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
    t = db.q1(conn, "SELECT * FROM tentativas WHERE id = ?", [tid])
    if t is None:
        # Instância nova sem a tentativa: tenta retomar/recriar em vez de erro.
        novo = _recuperar_ou_recriar(conn, usuario, tid)
        if novo is None:
            flash("Esta tentativa não existe mais neste servidor (banco temporário). "
                  "Inicie um novo treino.", "aviso")
            return redirect(url_for("geral.dashboard"))
        pergunta_id = request.form.get("pergunta_id", type=int)
        t2 = db.q1(conn, "SELECT * FROM tentativas WHERE id = ?", [novo])
        if pergunta_id:
            _salvar_tolerante(conn, t2, pergunta_id,
                              request.form.get("alternativa_id", type=int))
        flash("A tentativa original não estava mais neste servidor; "
              "continue nesta nova.", "aviso")
        return redirect(url_for("quiz.executar", tid=novo, feedback=pergunta_id))
    if t["usuario_id"] != usuario["id"] and t["usuario_id"] != _uid_aluno(conn):
        abort(403, description="Esta tentativa pertence a outro usuário.")
    if t["status"] != "em_andamento":
        return redirect(url_for("resultado.resultado", tid=tid))
    _t, mapa, _regras = t, __import__("json").loads(t["questoes_json"] or "{}"), {}
    pergunta_id = request.form.get("pergunta_id", type=int)
    if pergunta_id:
        _salvar_tolerante(conn, _t, pergunta_id,
                          request.form.get("alternativa_id", type=int))
    if t["modo"] == "treino":
        return redirect(url_for("quiz.executar", tid=tid, feedback=pergunta_id))
    flash("Resposta registrada.", "ok")
    return redirect(url_for("quiz.executar", tid=tid))


@bp.route("/api/tentativa/<int:tid>/resposta", methods=["POST"])
@login_required
def api_resposta(tid):
    """Auto-save da prova de módulo (mesmo contrato do simulado)."""
    from flask import jsonify

    from comum import segundos_ate

    usuario = usuario_atual()
    if usuario is None:
        return jsonify({"ok": False, "erro": "sessao_expirada"}), 401
    conn = db.get_db()
    t, mapa, _regras = sessao.carregar(conn, tid, usuario["id"], exigir_andamento=True)
    data = request.get_json(silent=True) or {}
    if "pergunta_id" in data and data.get("pergunta_id"):
        alt = data.get("alternativa_id")
        try:
            alt = int(alt) if alt not in (None, "") else None
        except (TypeError, ValueError):
            alt = None
        try:
            sessao.salvar_resposta(conn, t, int(data["pergunta_id"]), alt, None)
        except Exception:
            pass
    for pid, alt in (data.get("respostas") or {}).items():
        try:
            alt = int(alt) if alt not in (None, "") else None
        except (TypeError, ValueError):
            continue
        try:
            sessao.salvar_resposta(conn, t, int(pid), alt, None)
        except Exception:
            continue
    return jsonify({"ok": True, "resumo": sessao.resumo_respostas(conn, tid),
                    "restante": segundos_ate(t["limite_em"]) if t["limite_em"] else None})


@bp.route("/tentativa/<int:tid>/entregar", methods=["POST"])
@login_required
def entregar(tid):
    usuario = usuario_atual()
    conn = db.get_db()
    t = db.q1(conn, "SELECT * FROM tentativas WHERE id = ?", [tid])
    if t is None:
        novo = _recuperar_ou_recriar(conn, usuario, tid)
        if novo is None:
            flash("Esta tentativa não existe mais neste servidor (banco temporário).", "aviso")
            return redirect(url_for("geral.dashboard"))
        return redirect(url_for("quiz.executar", tid=novo))
    if t["usuario_id"] != usuario["id"] and t["usuario_id"] != _uid_aluno(conn):
        abort(403, description="Esta tentativa pertence a outro usuário.")
    if t["status"] == "em_andamento":
        for chave, valor in request.form.items():
            if chave.startswith("p_") and valor.isdigit():
                _salvar_tolerante(conn, t, int(chave[2:]), int(valor))
        correcao.corrigir(conn, t)
    return redirect(url_for("resultado.resultado", tid=tid))
