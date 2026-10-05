"""Verificacao das correcoes do erro de CSRF / login constante.

Cenarios novos (a mais:
  1. POST sem sessao valida -> redirect para /login (nao mais 400 em beco).
  2. POST logado com token errado -> continua 400 (seguranca preservada).
  3. secret_key() sem SECRET_KEY, disco so-leitura e com DATABASE_URL -> chave
     ESTAVEL derivada do DSN (nao efemera).
  4. secret_key() sem SECRET_KEY, disco so-leitura e sem DSN -> chave efemera.
  5. /healthz expoe a origem da chave da sessao.

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

    titulo("POST sem sessao valida (cookie expirado/assinado com outra chave)")
    # Envia um cookie de sessao invalido: o Flask nao o decodifica e a sessao
    # fica vazia - exatamente o que acontece quando a SECRET_KEY muda.
    resposta = cliente.post("/modulo/fundamentos-dw/quiz/iniciar",
                            data={"modo": "treino"},
                            headers={"Cookie": "session=eyJhbGciOiJIUzI1NiJ9.invalido.xxxxx"},
                            follow_redirects=False)
    ok(resposta.status_code == 302 and "/login" in resposta.headers.get("Location", ""),
       "POST sem sessao redireciona para /login (nao 400)")
    ok("login" in texto(cliente.get(resposta.headers["Location"])).lower()
       or cliente.get(resposta.headers["Location"]).status_code == 200,
       "a pagina de login abre apos o redirect")

    titulo("POST logado com token CSRF errado (seguranca preservada)")
    cliente.post("/login", data={"usuario": "pedro.santos", "senha": "1234", "lembrar": "1"},
                 follow_redirects=True)
    resposta = cliente.post("/modulo/fundamentos-dw/quiz/iniciar",
                            data={"modo": "treino", "_csrf": "token_errado"})
    ok(resposta.status_code == 400 and "CSRF" in texto(resposta),
       "POST logado com token errado continua bloqueado (400)")

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
