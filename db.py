"""Camada de acesso ao SQLite (funciona dentro do Flask e em scripts)."""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Optional

import config


def connect() -> sqlite3.Connection:
    """Abre uma conexao configurada (Row + foreign keys)."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(verbose: bool = True) -> None:
    """Cria o banco a partir do schema.sql (idempotente)."""
    sql = config.SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(sql)
        migrar(conn, verbose=verbose)
    if verbose:
        print(f"[db] banco pronto em {config.DB_PATH}")


# ---------------------------------------------------------------- migracoes
def _schema_sql() -> str:
    return config.SCHEMA_PATH.read_text(encoding="utf-8")


def _ddl(nome: str) -> Optional[str]:
    """Extrai o CREATE TABLE de 'nome' direto do schema.sql (com parenteses balanceados)."""
    sql = _schema_sql()
    achado = re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(nome)}\s*\(", sql, re.IGNORECASE)
    if not achado:
        return None
    nivel = 0
    for i in range(achado.end() - 1, len(sql)):
        if sql[i] == "(":
            nivel += 1
        elif sql[i] == ")":
            nivel -= 1
            if nivel == 0:
                return sql[achado.start():i + 1]
    return None


def _ddl_com_nome(nome: str, novo: str) -> Optional[str]:
    """Mesmo CREATE TABLE, mas com outro nome de tabela (usado na tabela temporaria)."""
    ddl = _ddl(nome)
    if not ddl:
        return None
    return re.sub(rf"(CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+){re.escape(nome)}\b", rf"\1{novo}",
                  ddl, count=1, flags=re.IGNORECASE)


def _indices(nome: str) -> list[str]:
    """Todos os CREATE INDEX ... ON <nome> declarados no schema.sql."""
    return [m.group(0).strip() for m in re.finditer(
        rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+\S+\s+ON\s+{re.escape(nome)}\s*\([^;]*\)",
        _schema_sql(), re.IGNORECASE)]


def _reconstruir(conn: sqlite3.Connection, nome: str, verbose: bool = True) -> bool:
    """Recria a tabela com a definicao atual do schema.sql, preservando as linhas.

    Segue o procedimento recomendado pelo SQLite (nova tabela -> copia -> drop ->
    rename). Os pragmas sao essenciais:
      * foreign_keys = OFF  -> o DROP da tabela antiga nao cascadeia/apaga filhos;
      * legacy_alter_table = ON -> o RENAME nao reescreve os REFERENCES de outras
        tabelas (comportamento do SQLite >= 3.25 caso contrario).
    """
    ddl = _ddl_com_nome(nome, f"{nome}_migracao")
    colunas = [r["name"] for r in q(conn, f"PRAGMA table_info({nome})")]
    if not ddl or not colunas:
        return False
    temp = f"{nome}_migracao"
    lista = ", ".join(colunas)
    passos = [
        "PRAGMA foreign_keys = OFF;",
        "PRAGMA legacy_alter_table = ON;",
        "BEGIN;",
        f"DROP TABLE IF EXISTS {temp};",
        f"{ddl};",
        f"INSERT INTO {temp} ({lista}) SELECT {lista} FROM {nome};",
        f"DROP TABLE {nome};",
        f"ALTER TABLE {temp} RENAME TO {nome};",
    ]
    passos += [f"{indice};" for indice in _indices(nome)]
    passos += ["COMMIT;", "PRAGMA legacy_alter_table = OFF;", "PRAGMA foreign_keys = ON;"]
    try:
        conn.executescript("\n".join(passos))
    except sqlite3.Error as erro:
        if verbose:
            print(f"[db] migracao de {nome} ignorada: {erro}")
        return False
    return True


def _migrar_tentativas_reforco(conn: sqlite3.Connection, verbose: bool = True) -> None:
    """Bancos antigos nao aceitavam modo='reforco' em tentativas.modo."""
    linha = q1(conn, "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tentativas'")
    if linha is None or "reforco" in (linha[0] or ""):
        return
    if _reconstruir(conn, "tentativas", verbose=verbose) and verbose:
        print("[db] migracao aplicada: modo 'reforco' liberado em tentativas.modo")


def _reparar_fk_respostas(conn: sqlite3.Connection, verbose: bool = True) -> None:
    """Corrige respostas cuja FK ficou apontando para uma tabela temporaria de migracao."""
    linha = q1(conn, "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'respostas'")
    if linha is None or "tentativas_migracao" not in (linha[0] or ""):
        return
    if _reconstruir(conn, "respostas", verbose=verbose) and verbose:
        print("[db] migracao aplicada: respostas.tentativa_id voltou a apontar para tentativas")


def migrar(conn: sqlite3.Connection, verbose: bool = True) -> None:
    """Ajustes de schema em bancos ja existentes (seguro para rodar sempre)."""
    _reparar_fk_respostas(conn, verbose=verbose)
    _migrar_tentativas_reforco(conn, verbose=verbose)
    if verbose:
        problemas = q(conn, "PRAGMA foreign_key_check")
        if problemas:
            print(f"[db] atencao: {len(problemas)} problema(s) de chave estrangeira no banco")
        else:
            print("[db] integridade das chaves estrangeiras: OK")


# ------------------------------------------------------------------ helpers
def q(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def q1(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchone()


def run(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    """Executa um INSERT/UPDATE/DELETE com commit e devolve lastrowid/rowcount."""
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur.lastrowid if cur.lastrowid else cur.rowcount


@contextmanager
def abrir():
    """Uso em scripts: with db.abrir() as conn: ..."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------- contexto do Flask
def get_db() -> sqlite3.Connection:
    from flask import g

    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exception=None) -> None:
    from flask import g

    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
