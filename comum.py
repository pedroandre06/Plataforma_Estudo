"""Helpers compartilhados: datas, CSRF, autenticação e formatação."""
from __future__ import annotations

import html
import random
import unicodedata
from datetime import datetime, timedelta
from functools import wraps

from flask import (abort, flash, g, make_response, redirect, render_template, request,
                   session, url_for)

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
    """Valida o token CSRF em toda requisição de escrita (exceto /api/ e login/registro).

    Se a sessao nem existe mais (cookie assinado com outra chave, expirado ou limpo),
    nao faz sentido devolver 400 - o usuario nao tem nem como "recarregar" o form certo.
    Nesse caso redireciona para o login com um aviso claro; a escrita NAO acontece.
    """
    if request.method in ("POST", "PUT", "DELETE") and not request.path.startswith("/api/"):
        if request.path in ("/login", "/registro"):
            return
        enviado = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if enviado and enviado == session.get("csrf"):
            return
        if "usuario_id" not in session:
            # Sessao invalida/expirada: leva para o login em vez de um beco 400.
            flash("Sua sessão expirou ou a página ficou desatualizada. "
                  "Faça login novamente para continuar.", "aviso")
            return redirect(url_for("login", proximo=request.path))
        # Logado com form antigo (ex.: botao "voltar"): bloqueia, mas pede recarga.
        abort(400, description="Token CSRF inválido. Recarregue a página e tente novamente.")


# ------------------------------------------------------------- usuários
USUARIO_LIVRE = "aluno"


def _garantir_usuario_livre():
    """Usuário padrão do modo sem senha: cria na hora se ainda não existir."""
    from werkzeug.security import generate_password_hash
    import secrets

    conn = db.get_db()
    linha = db.q1(conn, "SELECT * FROM usuarios WHERE lower(usuario) = lower(?)",
                  [USUARIO_LIVRE])
    if linha is None:
        db.run(conn, "INSERT INTO usuarios (usuario, nome, email, senha_hash, papel)"
                     " VALUES (?,?,?,?,?)",
               [USUARIO_LIVRE, "Aluno", None,
                generate_password_hash(secrets.token_hex(16)), "admin"])
        linha = db.q1(conn, "SELECT * FROM usuarios WHERE lower(usuario) = lower(?)",
                      [USUARIO_LIVRE])
    return linha


def usuario_atual():
    # Modo sem senha: sempre há um usuário (padrão "aluno"), nunca pede login.
    if "usuario_id" not in session:
        try:
            padrao = _garantir_usuario_livre()
            session.permanent = True
            session["usuario_id"] = padrao["id"]
            if "csrf" not in session:
                csrf_token()
        except Exception:
            return None
    if "usuario" not in g:
        g.usuario = db.q1(
            db.get_db(), "SELECT * FROM usuarios WHERE id = ? AND ativo = 1", [session["usuario_id"]]
        )
        if g.usuario is None:
            session.clear()
    return g.usuario



def login_required(funcao):
    # Modo sem senha: acesso livre, sem redirect para /login.
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        usuario_atual()
        return funcao(*args, **kwargs)

    return wrapper



def admin_required(funcao):
    # Modo sem senha: área admin também livre (usuário padrão é admin).
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        usuario_atual()
        return funcao(*args, **kwargs)

    return wrapper


def pagina_de_problema(erro: Exception, codigo: int = 503, titulo: str | None = None):
    """Pagina de diagnostico que NAO depende do banco.

    Usada quando o proprio banco falha (por exemplo, deploy sem DATABASE_URL): como
    ela nao consulta o banco nem a sessao, o usuario ve a causa real em vez de um
    500 generico em branco. Se ate o template falhar, devolve um HTML minimo.
    """
    titulo = titulo or "Não foi possível preparar o banco de dados"
    try:
        banco = config.resumo_dsn()
        motor = db.motor()
    except Exception:  # noqa: BLE001 - diagnostico nunca pode derrubar a pagina
        banco, motor = "desconhecido", "desconhecido"
    try:
        corpo = render_template(
            "problema.html",
            codigo=codigo,
            titulo=titulo,
            mensagem="A aplicação não conseguiu conectar ou preparar o banco de dados.",
            detalhe=str(erro),
            motor=motor,
            banco=banco,
        )
        return make_response(corpo, codigo)
    except Exception:  # noqa: BLE001 - ultimo recurso: HTML minimo, sem templates
        minimo = (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
            f"<title>{codigo}</title></head><body>"
            f"<h1>{codigo}</h1><p>{html.escape(titulo)}</p>"
            f"<p>Motor: {html.escape(str(motor))} | Banco: {html.escape(str(banco))}</p>"
            f"<p>Detalhe: {html.escape(str(erro))}</p></body></html>"
        )
        return make_response(minimo, codigo)


def registrar_app(app) -> None:
    """Conecta os helpers ao app Flask (globals de template e hooks)."""
    app.before_request(proteger_post)
    app.before_request(_renovar_sessao)
    app.jinja_env.globals.update(
        csrf_token=csrf_token,
        fmt_nota=fmt_nota,
        usuario_atual=usuario_atual,
        agora=agora,
    )


def _renovar_sessao():
    """Mantém a sessão ativa enquanto o usuário navega (sliding expiration).

    Sessões antigas criadas como não-permanentes (cookie de navegador) são
    promovidas a permanentes, para não expirar ao fechar o navegador.
    Com SESSION_REFRESH_EACH_REQUEST=True, cada resposta renova o cookie.
    """
    if "usuario_id" in session:
        session.permanent = True
