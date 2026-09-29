"""Inspecao rapida do banco - funciona com SQLite local e com PostgreSQL.

Uso:
    .venv\\Scripts\\python.exe tools\\inspecionar_db.py
    DATABASE_URL=postgresql://... .venv\\Scripts\\python.exe tools\\inspecionar_db.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import config  # noqa: E402
import db  # noqa: E402

TABELAS = ("materias", "modulos", "perguntas", "alternativas", "flashcards", "simulados",
           "simulado_materias", "simulado_questoes", "usuarios", "tentativas", "respostas",
           "progresso", "anotacoes")


def nomes_de_tabelas(conn) -> set[str]:
    if config.usar_postgres():
        return {r[0] for r in db.q(
            conn, "SELECT table_name FROM information_schema.tables "
                  "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'")}
    return {r[0] for r in db.q(
        conn, "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}


def principal() -> int:
    print("banco:", db.resumo())
    if not config.usar_postgres():
        print("arquivo:", config.DB_PATH, "| existe:", config.DB_PATH.exists())
    with db.abrir() as c:
        tabelas = nomes_de_tabelas(c)
        print("tabelas:", sorted(tabelas) or "(nenhuma - rode python -c \"import db; db.init_db()\")")
        for t in TABELAS:
            if t in tabelas:
                print(f"  {t:<20}{db.q1(c, f'SELECT COUNT(*) FROM {t}')[0]:>7}")
        if config.usar_postgres():
            print("versao:", db.q1(c, "SHOW server_version")[0])
        else:
            violacoes = db.q(c, "PRAGMA foreign_key_check")
            print("integridade:", db.q1(c, "PRAGMA integrity_check")[0],
                  "| violacoes de FK:", len(violacoes))
            ddl = db.q1(c, "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tentativas'")
            print("tentativas aceita modo='reforco':", "reforco" in ((ddl or [""])[0] or ""))
            print("versao: sqlite", sqlite3.sqlite_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
