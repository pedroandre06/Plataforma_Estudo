"""Verificacao do modo sem senha: acesso livre, sem login e sem CSRF.

Rodar: .venv\\Scripts\\python.exe tools\\teste_correcao_login.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

import config  # noqa: E402

config.DB_PATH = BASE / "data" / "qa_e2e.db"

import app as appmod  # noqa: E402
import db  # noqa: E402
from qa_common import ok, relatorio, texto, titulo  # noqa: E402


def main() -> int:
    appmod.app.config.update(TESTING=True)
    cliente = appmod.app.test_client()

    titulo("Acesso livre (sem senha)")
    resposta = cliente.post("/modulo/fundamentos-dw/quiz/iniciar",
                            data={"modo": "treino"}, follow_redirects=False)
    ok(resposta.status_code in (302, 303),
       "POST de escrita funciona sem login e sem CSRF")
    ok(cliente.get("/").status_code == 200, "painel abre sem login")

    titulo("Chave de sessao estavel sem SECRET_KEY")
    salvo_env = os.environ.pop("SECRET_KEY", None)
    salvo_dsn = os.environ.pop("DATABASE_URL", None)
    salvo_pg = os.environ.pop("POSTGRES_URL", None)
    salvo_arquivo = config.SECRET_KEY_FILE
    try:
        # Simula disco so-leitura: aponta o arquivo para uma pasta inexistente
        # em uma raiz invalida para forcarr o OSError.
        config.SECRET_KEY_FILE = Path("Z:/pasta/que/nao/existe/<<impossivel>>/.secret_key")
        os.environ["DATABASE_URL"] = "postgresql://user:senha@host/dbestavel"
        chave1 = config.secret_key()
        origem1 = config.origem_chave()
        os.environ.pop("DATABASE_URL")
        os.environ["POSTGRES_URL"] = "postgresql://user:senha@host/dbestavel"
        chave2 = config.secret_key()
        origem2 = config.origem_chave()
        ok(origem1 == "dsn" and origem2 == "dsn",
           f"origem da chave e 'dsn' quando ha DATABASE_URL ({origem1}/{origem2})")
        ok(chave1 == chave2 and len(chave1) == 64,
           "chave derivada do DSN e identica entre instancias (estavel)")

        os.environ.pop("POSTGRES_URL")
        chave3 = config.secret_key()
        ok(config.origem_chave() == "efemera" and chave3 != chave1,
           "sem SECRET_KEY, arquivo e DSN, cai para chave efemera (com aviso)")
    finally:
        config.SECRET_KEY_FILE = salvo_arquivo
        if salvo_env is not None:
            os.environ["SECRET_KEY"] = salvo_env
        if salvo_dsn is not None:
            os.environ["DATABASE_URL"] = salvo_dsn
        if salvo_pg is not None:
            os.environ["POSTGRES_URL"] = salvo_pg

    titulo("Diagnostico no /healthz")
    resposta = cliente.get("/healthz")
    corpo = texto(resposta)
    ok(resposta.status_code == 200 and '"sessao"' in corpo,
       "/healthz expoe a origem da chave da sessao")
    ok(f'"sessao":"{config.origem_chave()}"' in corpo.replace(" ", ""),
       "origem reportada no /healthz bate com config.origem_chave()")

    return relatorio()


if __name__ == "__main__":
    raise SystemExit(main())
