"""Camada de acesso ao banco - SQLite (local) ou PostgreSQL (nuvem / Vercel).

O SQL do projeto e escrito uma unica vez, no dialeto do SQLite (placeholders "?",
INSERT OR IGNORE etc.). Quando DATABASE_URL aponta para um PostgreSQL, a classe
ConexaoPostgres abaixo assume a compatibilidade em tempo de execucao:

  * "?" vira "%s" (e os "%" literais do SQL sao escapados);
  * "INSERT OR IGNORE" vira "INSERT ... ON CONFLICT DO NOTHING";
  * todo INSERT em tabela que tem coluna "id" ganha "RETURNING id", para que
    db.run() devolva o identificador gerado - equivalente ao lastrowid do SQLite;
  * as linhas chegam em db.Linha, que aceita acesso por nome e por posicao exatamente
    como sqlite3.Row - por isso os templates Jinja nao precisam mudar nada.

Schemas: schema.sql (SQLite) e schema_pg.sql (PostgreSQL), com as mesmas tabelas.

Unica regra de escrita para o SQL do projeto: nada de funcao exclusiva de um motor.
Por isso os relatorios arredondam com ROUND(x * 10) / 10 (o Postgres so aceita
ROUND(numeric, int) e AVG devolve double) e as divisoes usam "* 1.0" em vez de
CAST(... AS REAL).
"""
from __future__ import annotations

import re
import sqlite3
import sys
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, Optional

import config


class Linha:
    """Linha de resultado do PostgreSQL compativel com sqlite3.Row (nome e indice)."""

    __slots__ = ("_chaves", "_valores")

    def __init__(self, chaves: tuple[str, ...], valores: tuple[Any, ...]) -> None:
        self._chaves = chaves
        self._valores = valores

    def keys(self) -> tuple[str, ...]:
        return self._chaves

    def get(self, chave: str, padrao: Any = None) -> Any:
        return self[chave] if chave in self._chaves else padrao

    def __getitem__(self, chave: Any) -> Any:
        if isinstance(chave, str):
            try:
                return self._valores[self._chaves.index(chave)]
            except ValueError:
                raise KeyError(chave) from None
        return self._valores[chave]

    def __contains__(self, chave: str) -> bool:
        return chave in self._chaves

    def __iter__(self) -> Iterator[Any]:
        return iter(self._valores)

    def __len__(self) -> int:
        return len(self._valores)

    def __repr__(self) -> str:
        return f"<Linha {dict(zip(self._chaves, self._valores))}>"


def dividir_comandos(sql: str) -> list[str]:
    """Separa um script SQL em comandos pelo ';', ignorando comentarios '--' e strings."""
    comandos: list[str] = []
    atual: list[str] = []
    em_string = False
    i = 0
    while i < len(sql):
        c = sql[i]
        if em_string:
            atual.append(c)
            if c == "'":
                em_string = False
            i += 1
            continue
        if c == "'":
            em_string = True
            atual.append(c)
            i += 1
            continue
        if c == "-" and sql.startswith("--", i):
            quebra = sql.find("\n", i)
            i = len(sql) if quebra < 0 else quebra
            continue
        if c == ";":
            comando = "".join(atual).strip()
            if comando:
                comandos.append(comando)
            atual = []
            i += 1
            continue
        atual.append(c)
        i += 1
    resto = "".join(atual).strip()
    if resto:
        comandos.append(resto)
    return comandos


# 'INSERT OR IGNORE' so existe no SQLite; no Postgres o equivalente e ON CONFLICT DO NOTHING.
_INSERT_OR_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)", re.IGNORECASE)
_INSERT_INTO = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.IGNORECASE)


def para_postgres(sql: str, obter_tabelas_com_id: Callable[[], set[str]]) -> tuple[str, bool, bool]:
    """Traduz SQL do dialeto SQLite para o Postgres.

    Devolve (sql_traduzido, devolve_id, tem_placeholders).
    """
    texto = sql
    ignorar_duplicados = False
    tabela: Optional[str] = None
    achado = _INSERT_OR_IGNORE.match(texto)
    if achado:
        ignorar_duplicados = True
        tabela = achado.group(1)
        texto = "INSERT INTO " + achado.group(1) + texto[achado.end():]
    else:
        achado = _INSERT_INTO.match(texto)
        if achado:
            tabela = achado.group(1)

    devolve_id = False
    if tabela is not None:
        texto = texto.rstrip().rstrip(";")
        if ignorar_duplicados:
            texto += "\nON CONFLICT DO NOTHING"
        if tabela.lower() in obter_tabelas_com_id() and " returning" not in texto.lower():
            texto += "\nRETURNING id"
            devolve_id = True

    tem_placeholders = "?" in sql
    if tem_placeholders:
        texto = texto.replace("%", "%%").replace("?", "%s")
    return texto, devolve_id, tem_placeholders


class ConexaoPostgres:
    """Conexao PostgreSQL que entende o SQL escrito para o SQLite (veja o topo do modulo)."""

    def __init__(self, conexao: Any) -> None:
        self._conn = conexao
        self._tabelas: Optional[set[str]] = None

    def tabelas_com_id(self) -> set[str]:
        """Tabelas do schema atual que tem coluna 'id' (consulta unica por conexao)."""
        if self._tabelas is None:
            linhas = self._conn.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND column_name = 'id'"
            ).fetchall()
            self._tabelas = {linha[0] for linha in linhas}
        return self._tabelas

    def execute(self, sql: str, params: Iterable[Any] = ()) -> CursorPos:
        args = tuple(params) if params else ()
        texto, devolve_id, tem_placeholders = para_postgres(sql, self.tabelas_com_id)
        cursor = self._conn.execute(texto, args if tem_placeholders else None)
        return CursorPos(cursor, devolve_id)

    def executescript(self, texto: str) -> None:
        """Aplica um script DDL comando por comando (o Postgres nao aceita lote unico)."""
        for comando in dividir_comandos(texto):
            self._conn.execute(comando)

    def commit(self) -> None:
        """A conexao roda em autocommit: cada db.run() ja fica gravado na hora."""

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def conectar_postgres(dsn: str) -> ConexaoPostgres:
    """Abre a conexao PostgreSQL (autocommit, timeout curto, amigavel a pooler tipo Neon)."""
    import psycopg  # import tardio: o modo SQLite funciona sem psycopg instalado

    conexao = (dsn or "").strip()
    if conexao.startswith("postgres://"):
        conexao = "postgresql://" + conexao[len("postgres://"):]
    bruta = psycopg.connect(
        conninfo=conexao,
        autocommit=True,         # mesma semantics do db.run(): gravar e imediato
        connect_timeout=20,
        application_name="plataforma-estudos",
        prepare_threshold=None,  # sem prepared statements: pooler de transacao nao suporta
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )
    return ConexaoPostgres(bruta)


def connect() -> Any:
    """Abre a conexao do motor configurado: Postgres se DATABASE_URL existir, senao SQLite."""
    if config.usar_postgres():
        return conectar_postgres(config.dsn_postgres())
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class CursorPos:
    """Cursor do Postgres com a mesma interface que os helpers q/q1/run esperam."""

    def __init__(self, cursor: Any, devolve_id: bool) -> None:
        self._cursor = cursor
        self.lastrowid: Optional[int] = None
        self.rowcount = cursor.rowcount if (cursor.rowcount or 0) > 0 else 0
        if devolve_id:
            registro = cursor.fetchone()
            self.lastrowid = int(registro[0]) if registro and registro[0] is not None else None

    def _chaves(self) -> tuple[str, ...]:
        return tuple(col.name for col in (self._cursor.description or ()))

    def fetchall(self) -> list[Linha]:
        chaves = self._chaves()
        linhas = [Linha(chaves, tuple(linha)) for linha in self._cursor.fetchall()]
        self._fechar()
        return linhas

    def fetchone(self) -> Optional[Linha]:
        chaves = self._chaves()
        registro = self._cursor.fetchone()
        self._fechar()
        return None if registro is None else Linha(chaves, tuple(registro))

    def scalar(self) -> Any:
        registro = self.fetchone()
        return None if registro is None else registro[0]

    def _fechar(self) -> None:
        try:
            self._cursor.close()
        except Exception:  # noqa: BLE001 - fechar nunca derruba a requisicao
            pass


def schema_do_motor() -> str:
    """Texto do script DDL do motor ativo: schema.sql (SQLite) ou schema_pg.sql (Postgres)."""
    caminho = config.SCHEMA_PG_PATH if config.usar_postgres() else config.SCHEMA_PATH
    return caminho.read_text(encoding="utf-8")


def criar_tabelas(conn, verbose: bool = False) -> None:
    """Aplica o schema do motor ativo numa conexao ja aberta (idempotente)."""
    if verbose:
        print(f"[db] aplicando schema em {resumo()}")
    conn.executescript(schema_do_motor())
    conn.commit()


def init_db(verbose: bool = True) -> None:
    """Cria o banco a partir do schema do motor em uso (idempotente)."""
    if config.usar_postgres():
        with abrir() as conn:
            criar_tabelas(conn)
        if verbose:
            print(f"[db] schema aplicado no PostgreSQL: {config.resumo_dsn()}")
        return
    sql = config.SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(sql)
        migrar(conn, verbose=verbose)
    if verbose:
        print(f"[db] banco pronto em {config.DB_PATH}")


def motor() -> str:
    """'postgres' ou 'sqlite' - util para logs, diagnostico e ferramentas."""
    return "postgres" if config.usar_postgres() else "sqlite"


def resumo() -> str:
    """De onde este processo esta lendo/gravando dados (sem expor senha)."""
    return f"{motor()}: {config.resumo_dsn()}"


_schema_verificado = False


def garantir_schema(verbose: bool = False) -> None:
    """Aplica o schema uma unica vez, se o banco ainda nao tiver as tabelas.

    E o que dispensa passo manual no deploy: no primeiro cold start da Vercel o app
    cria as tabelas no Postgres recem-criado. Depois disso a checagem nao custa nada.
    """
    global _schema_verificado
    if _schema_verificado:
        return
    _schema_verificado = True
    if config.usar_postgres():
        with abrir() as conn:
            falta = q1(conn, "SELECT to_regclass('public.usuarios') AS tabela")["tabela"] is None
        if falta:
            init_db(verbose=True)
        elif verbose:
            print(f"[db] schema ja aplicado em {config.resumo_dsn()}")
        return
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    bruta = sqlite3.connect(config.DB_PATH)
    try:
        existe = bruta.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'usuarios' LIMIT 1"
        ).fetchone()
    finally:
        bruta.close()
    if not existe:
        init_db(verbose=True)


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


def migrar(conn: Any, verbose: bool = True) -> None:
    """Ajustes de schema em bancos SQLite ja existentes (seguro para rodar sempre).

    No PostgreSQL isto nao se aplica: la nao ha heranca de schema antigo, e o
    PRAGMA/CHECK de integridade e especifico do SQLite.
    """
    if config.usar_postgres():
        return
    _reparar_fk_respostas(conn, verbose=verbose)
    _migrar_tentativas_reforco(conn, verbose=verbose)
    if verbose:
        problemas = q(conn, "PRAGMA foreign_key_check")
        if problemas:
            print(f"[db] atencao: {len(problemas)} problema(s) de chave estrangeira no banco")
        else:
            print("[db] integridade das chaves estrangeiras: OK")


# ------------------------------------------------------------------ helpers
# conn e' Any de proposito: sqlite3.Connection ou db.ConexaoPostgres - a interface
# usada aqui (execute/commit/close) e identica nos dois.
def q(conn: Any, sql: str, params: Iterable[Any] = ()) -> list[Any]:
    return conn.execute(sql, tuple(params)).fetchall()


def q1(conn: Any, sql: str, params: Iterable[Any] = ()) -> Optional[Any]:
    return conn.execute(sql, tuple(params)).fetchone()


def run(conn: Any, sql: str, params: Iterable[Any] = ()) -> int:
    """Executa um INSERT/UPDATE/DELETE com commit e devolve lastrowid/rowcount."""
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur.lastrowid if cur.lastrowid else cur.rowcount


@contextmanager
def abrir() -> Any:
    """Uso em scripts: with db.abrir() as conn: ..."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------- contexto do Flask
def get_db() -> Any:
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
