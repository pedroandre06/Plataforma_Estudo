"""Autenticação: modo sem senha (login/registro/logout só redirecionam)."""
from __future__ import annotations

from flask import Flask, redirect, url_for


def registrar_rotas_auth(app: Flask) -> None:
    # Modo sem senha: /login, /registro e /logout redirecionam para o painel.
    # Mantidos apenas para não quebrar links antigos; nenhum exige senha.
    @app.route("/login", methods=["GET", "POST"])
    def login():
        return redirect(url_for("geral.dashboard"))

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        return redirect(url_for("geral.dashboard"))

    @app.route("/logout")
    def logout():
        return redirect(url_for("geral.dashboard"))


def registrar_erros(app: Flask) -> None:
    @app.errorhandler(400)
    def erro_400(e):
        return render_template("erro.html", codigo=400,
                               mensagem=getattr(e, "description", "Requisição inválida.")), 400

    @app.errorhandler(403)
    def erro_403(e):
        return render_template("erro.html", codigo=403,
                               mensagem=getattr(e, "description", "Acesso negado.")), 403

    @app.errorhandler(404)
    def erro_404(e):
        return render_template("erro.html", codigo=404,
                               mensagem=getattr(e, "description", "Página não encontrada.")), 404

    @app.errorhandler(500)
    def erro_500(e):
        """Erro interno: mostra o diagnostico (pagina independente do banco)."""
        erro = getattr(e, "original_exception", None) or e
        return comum.pagina_de_problema(erro, codigo=500, titulo="Erro interno do servidor")

    @app.errorhandler(Exception)
    def erro_inesperado(e):
        """Qualquer excecao nao tratada vira uma pagina de diagnostico, nao um 500 vazio."""
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            # Deixa o Flask usar o handler especifico (400/403/404 etc.).
            return e.get_response()
        return comum.pagina_de_problema(e, codigo=500, titulo="Erro interno do servidor")
