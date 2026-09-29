"""Inspeção rápida do banco (tabelas, DDL de tentativas, contagens)."""
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import config  # noqa: E402

c = sqlite3.connect(config.DB_PATH)
print("db:", config.DB_PATH, "| existe:", config.DB_PATH.exists())
tabelas = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("tabelas:", tabelas)
ddl = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tentativas'").fetchone()
print("tentativas aceita modo='reforco':", "reforco" in (ddl[0] if ddl else ""))
for t in ("materias", "modulos", "perguntas", "simulados", "usuarios", "tentativas"):
    if t in tabelas:
        print(t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
print(f"integridade: {c.execute('PRAGMA integrity_check').fetchone()[0]}",
      f"| violacoes de FK: {len(c.execute('PRAGMA foreign_key_check').fetchall())}")
print("versao sqlite:", sqlite3.sqlite_version)
