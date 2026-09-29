"""Plataforma de Estudos - Pós em Engenharia de Dados.

Cria o app Flask e registra os módulos de rotas.

Executar:
    .venv\\Scripts\\python.exe app.py     ->  http://127.0.0.1:5000
"""
from __future__ import annotations

from datetime import timedelta

from flask import Flask, render_template

import comum
import config
import db

MODOS_QUIZ = {"treino": "Treino", "prova": "Prova do módulo", "revisao": "Revisão"}
MODOS_SIMULADO = {"materia": "Simulado por matéria", "geral": "Simulado geral",
                  "personalizado": "Simulado personalizado", "reforco": "Simulado de reforço",
                  "oficial": "Prova oficial"}
DIFICULDADES = {"facil": "Fácil", "medio": "Médio", "dificil": "Difícil"}


def criar_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=config.SESSION_DIAS),
        MAX_CONTENT_LENGTH=config.limite_upload_bytes(),
        JSON_AS_ASCII=False,
    )
    db.init_app(app)
    comum.registrar_app(app)
    app.jinja_env.globals.update(MODOS_QUIZ=MODOS_QUIZ, MODOS_SIMULADO=MODOS_SIMULADO,
                                 DIFICULDADES=DIFICULDADES)

    @app.before_request
    def _garantir_banco_pronto():
        """No primeiro cold start (Vercel) cria as tabelas se o banco estiver vazio."""
        db.garantir_schema()

    @app.route("/healthz")
    def healthz():
        """Checagem de sanidade: confirma a conexao e mostra qual motor esta em uso."""
        from flask import jsonify

        try:
            linha = db.q1(db.get_db(), "SELECT 1 AS ok")
            return jsonify(status="ok", motor=db.motor(), banco=config.resumo_dsn(),
                           consulta=linha["ok"] if linha is not None else None)
        except Exception as erro:  # noqa: BLE001 - o healthz nunca devolve 500 cru
            return jsonify(status="erro", motor=db.motor(), banco=config.resumo_dsn(),
                           detalhe=str(erro)), 500


    from auth import registrar_erros, registrar_rotas_auth
    from rotas_admin import bp as bp_admin
    from rotas_admin_export import bp as bp_admin_exp
    from rotas_admin_io import bp as bp_admin_io
    from rotas_admin_perguntas import bp as bp_admin_q
    from rotas_admin_prova import bp as bp_admin_prova
    from rotas_catalogo import bp as bp_geral
    from rotas_extra import bp as bp_extra
    from rotas_modulo import bp as bp_aula
    from rotas_quiz import bp as bp_quiz
    from rotas_resultado import bp as bp_resultado
    from rotas_simulado_exec import bp as bp_sim_exec
    from rotas_simulados import bp as bp_sim
    from rotas_simulados_novo import bp as bp_sim_cfg

    registrar_rotas_auth(app)
    for blue in (bp_geral, bp_aula, bp_extra, bp_quiz, bp_resultado, bp_sim, bp_sim_cfg,
                 bp_sim_exec, bp_admin, bp_admin_q, bp_admin_io, bp_admin_exp, bp_admin_prova):
        app.register_blueprint(blue)
    registrar_erros(app)
    return app


app = criar_app()

if __name__ == "__main__":
    import os

    db.init_db(verbose=False)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    print(f"Plataforma de Estudos -> http://{host}:{port}")
    print(f"Banco de dados: {db.resumo()}")
    app.run(host=host, port=port, debug=True)
