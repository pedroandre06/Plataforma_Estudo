"""Helpers compartilhados: datas e formatação (modo sem senha)."""
from __future__ import annotations

import html
import unicodedata
from datetime import datetime, timedelta

from flask import g, make_response, render_template

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
# Modo sem senha: sem sessão e sem CSRF. Token fixo só para os formulários
# existentes continuarem enviando o campo _csrf sem travar.
def csrf_token() -> str:
    return "livre"


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
    # Modo sem senha: usuário fixo do banco, sem depender de cookie/sessão.
    # Nunca pede login e nunca invalida por chave de sessão diferente.
    if "usuario" not in g:
        try:
            g.usuario = _garantir_usuario_livre()
        except Exception:
            g.usuario = None
    return g.usuario



def login_required(funcao):
    # Modo sem senha: acesso livre (decorador mantido só p/ não mexer nas rotas).
    return funcao



def admin_required(funcao):
    # Modo sem senha: área admin também livre.
    return funcao


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
    # Modo sem senha: sem before_request de sessão/CSRF.
    app.jinja_env.globals.update(
        csrf_token=csrf_token,
        fmt_nota=fmt_nota,
        usuario_atual=usuario_atual,
        agora=agora,
    )
