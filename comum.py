"""Helpers compartilhados: datas, CSRF, autenticação e formatação."""
from __future__ import annotations

import random
import unicodedata
from datetime import datetime, timedelta
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

import config
import db

FORMATO = "%Y-%m-%d %H:%M:%S"


def agora() -> str:
    return datetime.now().strftime(FORMATO)


def em_minutos(minutos: int) -> str:
    return (datetime.now() + timedelta(minutes=minutos)).strftime(FORMATO)


def para_data(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.strptime(texto[:19], FORMATO)
    except (ValueError, TypeError):
        return None


def segundos_ate(texto: str | None) -> int:
    alvo = para_data(texto)
    return max(0, int((alvo - datetime.now()).total_seconds())) if alvo else 0


def segundos_desde(texto: str | None) -> int:
    inicio = para_data(texto)
    return max(0, int((datetime.now() - inicio).total_seconds())) if inicio else 0


def slugificar(texto: str) -> str:
    limpo = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return "-".join("".join(c if c.isalnum() else " " for c in limpo).split())


def fmt_nota(valor) -> str:
    return "-" if valor is None else f"{float(valor):.1f}".replace(".", ",")


# ------------------------------------------------------------------ CSRF
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = random.getrandbits(64).to_bytes(8, "big").hex()
    return session["csrf"]


def proteger_post() -> None:
    """Valida o token CSRF em toda requisição de escrita (exceto /api/ e login/registro)."""
    if request.method in ("POST", "PUT", "DELETE") and not request.path.startswith("/api/"):
        if request.path in ("/login", "/registro"):
            return
        enviado = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not enviado or enviado != session.get("csrf"):
            abort(400, description="Token CSRF inválido. Recarregue a página e tente novamente.")


# ------------------------------------------------------------- usuários
def usuario_atual():
    if "usuario_id" not in session:
        return None
    if "usuario" not in g:
        g.usuario = db.q1(
            db.get_db(), "SELECT * FROM usuarios WHERE id = ? AND ativo = 1", [session["usuario_id"]]
        )
        if g.usuario is None:
            session.clear()
    return g.usuario


def login_required(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        if usuario_atual() is None:
            flash("Faça login para continuar.", "aviso")
            return redirect(url_for("login", proximo=request.path))
        return funcao(*args, **kwargs)

    return wrapper


def admin_required(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        usuario = usuario_atual()
        if usuario is None:
            return redirect(url_for("login", proximo=request.path))
        if usuario["papel"] != "admin":
            abort(403, description="Acesso restrito ao administrador.")
        return funcao(*args, **kwargs)

    return wrapper


def registrar_app(app) -> None:
    """Conecta os helpers ao app Flask (globals de template e hooks)."""
    app.before_request(proteger_post)
    app.jinja_env.globals.update(
        csrf_token=csrf_token,
        fmt_nota=fmt_nota,
        usuario_atual=usuario_atual,
        agora=agora,
    )
