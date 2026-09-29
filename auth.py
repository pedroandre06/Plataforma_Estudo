"""Autenticação: login, registro, logout e páginas de erro."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import comum
import config
import db


def registrar_rotas_auth(app: Flask) -> None:
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if comum.usuario_atual():
            return redirect(url_for("geral.dashboard"))
        if request.method == "POST":
            nome_usuario = (request.form.get("usuario") or "").strip()
            senha = request.form.get("senha") or ""
            conn = db.get_db()
            linha = db.q1(conn, "SELECT * FROM usuarios WHERE usuario = ?", [nome_usuario])
            if linha is not None and linha["bloqueado_ate"] and linha["bloqueado_ate"] > comum.agora():
                flash(f"Conta bloqueada até {linha['bloqueado_ate'][11:16]}.", "erro")
                return render_template("login.html")
            if linha is None or not check_password_hash(linha["senha_hash"], senha):
                if linha is not None:
                    falhas = linha["tentativas_falhas"] + 1
                    bloqueio = None
                    if falhas >= config.MAX_TENTATIVAS_LOGIN:
                        bloqueio = (datetime.now() + timedelta(minutes=config.BLOQUEIO_MINUTOS)
                                    ).strftime("%Y-%m-%d %H:%M:%S")
                        falhas = 0
                    db.run(conn, "UPDATE usuarios SET tentativas_falhas = ?, bloqueado_ate = ? WHERE id = ?",
                           [falhas, bloqueio, linha["id"]])
                    if bloqueio:
                        flash(f"Muitas tentativas: conta bloqueada por {config.BLOQUEIO_MINUTOS} min.", "erro")
                        return render_template("login.html")
                flash("Usuário ou senha inválidos.", "erro")
            elif not linha["ativo"]:
                flash("Usuário desativado. Fale com o administrador.", "erro")
            else:
                db.run(conn, "UPDATE usuarios SET tentativas_falhas = 0, bloqueado_ate = NULL,"
                             " ultimo_login_em = ? WHERE id = ?", [comum.agora(), linha["id"]])
                session.clear()
                session.permanent = bool(request.form.get("lembrar"))
                session["usuario_id"] = linha["id"]
                comum.csrf_token()
                flash(f"Bem-vindo(a), {linha['nome'].split()[0]}!", "ok")
                return redirect(request.args.get("proximo") or url_for("geral.dashboard"))
        return render_template("login.html")

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if not config.PERMITIR_REGISTRO:
            flash("O cadastro de novos usuários está desativado no momento.", "aviso")
            return redirect(url_for("login"))
        dados = request.form if request.method == "POST" else {}
        if request.method == "POST":
            nome_usuario = (request.form.get("usuario") or "").strip()
            nome = (request.form.get("nome") or "").strip()
            email = (request.form.get("email") or "").strip() or None
            senha = request.form.get("senha") or ""
            confirma = request.form.get("confirma") or ""
            erros = []
            if len(nome_usuario) < config.MIN_USUARIO or " " in nome_usuario:
                erros.append(f"O usuário deve ter ao menos {config.MIN_USUARIO} caracteres, sem espaços.")
            if not nome:
                erros.append("Informe seu nome.")
            if len(senha) < config.MIN_SENHA:
                erros.append(f"A senha deve ter ao menos {config.MIN_SENHA} caracteres.")
            if senha != confirma:
                erros.append("As senhas não conferem.")
            conn = db.get_db()
            if db.q1(conn, "SELECT 1 FROM usuarios WHERE usuario = ?", [nome_usuario]):
                erros.append("Este usuário já existe.")
            if erros:
                for e in erros:
                    flash(e, "erro")
                return render_template("registro.html", dados=dados)
            uid = db.run(conn, "INSERT INTO usuarios (usuario, nome, email, senha_hash) VALUES (?,?,?,?)",
                         [nome_usuario, nome, email, generate_password_hash(senha)])
            session.clear()
            session["usuario_id"] = uid
            comum.csrf_token()
            flash("Conta criada com sucesso! Bons estudos.", "ok")
            return redirect(url_for("geral.dashboard"))
        return render_template("registro.html", dados=dados)

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sessão encerrada.", "ok")
        return redirect(url_for("login"))


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
