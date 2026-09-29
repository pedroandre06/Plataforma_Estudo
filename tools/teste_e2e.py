"""Teste de ponta a ponta da plataforma (usa o test_client do Flask).

Roda contra um banco de QA descartavel, recriado a cada execucao, para nao mexer
nos seus dados de estudo:
  * SQLite  -> arquivo data/qa_e2e.db
  * Postgres-> o banco apontado por DATABASE_URL (o nome precisa ter "qa",
               ou entao rode com --force). Cuidado: ele APAGA o schema public.

Uso:
    .venv\\Scripts\\python.exe tools\\teste_e2e.py
    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/qa_plataforma ^
        .venv\\Scripts\\python.exe tools\\teste_e2e.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

import config  # noqa: E402

# Precisa vir antes de importar app/db: db.connect() lê config.DB_PATH na hora.
config.DB_PATH = BASE / "data" / "qa_e2e.db"

import app as appmod  # noqa: E402
import db  # noqa: E402
import qa_common  # noqa: E402


def preparar_banco() -> None:
    """Recria o banco de QA do zero: schema + admin + conteúdo + simulados."""
    if config.usar_postgres():
        with db.abrir() as conn:
            nome = db.q1(conn, "SELECT current_database() AS db")["db"]
            if "qa" not in nome.lower() and "--force" not in sys.argv:
                raise SystemExit(
                    f"[e2e] recusei apagar o PostgreSQL '{nome}'. Use um banco com 'qa' no nome\n"
                    f"        ou passe --force para confirmar que este banco pode ser zerado.")
            print(f"[e2e] zerando o schema public de '{nome}'")
            conn.executescript("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    else:
        for sufixo in ("", "-wal", "-shm"):
            arquivo = Path(str(config.DB_PATH) + sufixo)
            if arquivo.exists():
                arquivo.unlink()
    db.init_db(verbose=False)
    import seed_conteudo
    import seed_data

    with db.abrir() as conn:
        seed_data.criar_admin(conn)
        seed_conteudo.importar_conteudo(conn)
        seed_data.simulados_padrao(conn)


def main() -> int:
    preparar_banco()
    print(f"[e2e] banco de teste: {db.resumo()}")
    appmod.app.config.update(TESTING=True)
    cliente = appmod.app.test_client()

    import qa_parte1
    import qa_parte1b
    import qa_parte2
    import qa_parte3
    import qa_parte4

    tok = qa_parte1.executar(cliente)
    if not tok:
        return qa_common.relatorio()
    contexto = qa_parte1b.executar(cliente, tok)
    qa_parte2.executar(cliente, tok)
    qa_parte3.executar(cliente, tok, contexto)
    qa_parte4.executar(cliente, tok, contexto)
    return qa_common.relatorio()


if __name__ == "__main__":
    raise SystemExit(main())
