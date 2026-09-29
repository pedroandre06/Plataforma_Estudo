"""Verificacao estatica da camada de banco dupla - roda sem nenhum banco aberto.

Checa o que so apareceria como erro 500 no primeiro acesso em producao:

  1. schema.sql e schema_pg.sql descrevem as MESMAS tabelas com as MESMAS colunas;
  2. nenhum SQL escrito nos .py do projeto usa funcao exclusiva de um motor
     (strftime, IFNULL, CAST AS REAL, PRAGMA...): a traducao de db.py nao resolve
     esses casos e a query quebraria no PostgreSQL;
  3. todo SQL com '?' passa pelo tradutor de db.py e sai com a mesma quantidade de
     marcadores (%s) e de '%' escapados - nada se perde no caminho;
  4. schema_pg.sql e separavel comando por comando (o Postgres nao aceita lote unico).

Uso:
    .venv\\Scripts\\python.exe tools\\verificar_dialeto.py
"""
from __future__ import annotations

import ast
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import config  # noqa: E402
import db  # noqa: E402

# Termos que so existem em um dos motores. Se aparecerem em SQL do projeto, o
# tradutor de db.py nao da conta e a query quebra no Postgres.
PROIBIDO: dict[str, str] = {
    "strftime": r"\bstrftime\s*\(",
    "julianday": r"\bjulianday\s*\(",
    "datetime(...)": r"\bdatetime\s*\(",
    "date('now')": r"\bdate\s*\(",
    "GROUP_CONCAT": r"\bgroup_concat\s*\(",
    "IFNULL": r"\bifnull\s*\(",
    "INSERT OR REPLACE": r"\binsert\s+or\s+replace\b",
    "AUTOINCREMENT": r"\bautoincrement\b",
    "CAST(... AS REAL)": r"\bcast\s*\([^)]*\bas\s+real\b",
    "ROUND com 2 argumentos": r"\bround\s*\([^,()]*,",
    "sqlite_master": r"\bsqlite_master\b",
    "PRAGMA": r"\bpragma\b",
    "last_insert_rowid": r"\blast_insert_rowid\s*\(",
    "COLLATE NOCASE": r"\bcollate\s+nocase\b",
    "GLOB": r"\bglob\b",
}
COMECOS_SQL = ("select", "insert", "update", "delete", "with", "create", "alter", "drop",
               "and", "or", "where", "set", "values", "order", "group", "having", "limit",
               "join", "from", "on conflict")
# db.py e este arquivo citam esses termos de proposito (sao o proprio tradutor/verificador).
IGNORAR = {"db.py", "verificar_dialeto.py"}

FALHAS: list[str] = []


def ok(condicao: bool, descricao: str) -> bool:
    if not condicao:
        FALHAS.append(descricao)
    print(("[ok]   " if condicao else "[ERRO] ") + descricao)
    return bool(condicao)


def eh_sql(texto: str) -> bool:
    return texto.strip().lower().startswith(COMECOS_SQL)


def verificar_fonte() -> None:
    print("\n== SQL escrito nos .py (dialeto portavel) ==")
    com_id = {t for t, c in colunas_sqlite().items() if "id" in c}
    arquivos = [a for a in sorted(BASE.glob("*.py")) if a.name not in IGNORAR]
    avaliadas = 0
    for arquivo in arquivos:
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        except SyntaxError as erro:
            ok(False, f"{arquivo.name} pode ser lido pelo Python ({erro})")
            continue
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Constant) and isinstance(no.value, str)):
                continue
            texto = no.value
            if not eh_sql(texto):
                continue
            avaliadas += 1
            local = f"{arquivo.name}:{no.lineno}"
            for nome, padrao in PROIBIDO.items():
                if re.search(padrao, texto, re.IGNORECASE):
                    ok(False, f"{local} nao usa {nome} -> {texto[:60]!r}")
            if "?" in texto:
                traduzido, devolve_id, _ = db.para_postgres(texto, lambda: com_id)
                if texto.count("?") != traduzido.count("%s"):
                    ok(False, f"{local} perdeu marcadores na traducao -> {texto[:60]!r}")
                if texto.count("%") != traduzido.count("%%"):
                    ok(False, f"{local} tem '%' que nao foi escapado para o psycopg -> {texto[:60]!r}")
            alvo = re.match(r"\s*insert\s+(?:or\s+ignore\s+)?into\s+(\w+)", texto, re.IGNORECASE)
            if alvo and alvo.group(1).lower() in com_id and not devolve_id:
                ok(False, f"{local} insere em {alvo.group(1)} sem devolver o id -> {texto[:60]!r}")
    ok(avaliadas >= 150, f"{avaliadas} constantes de SQL conferidas (esperado >= 150)")


def colunas_sqlite() -> dict[str, list[str]]:
    conexao = sqlite3.connect(":memory:")
    conexao.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
    tabelas = [r[0] for r in conexao.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    resultado = {t: sorted(r[1] for r in conexao.execute(f"PRAGMA table_info({t})")) for t in tabelas}
    conexao.close()
    return resultado


def _corpo(texto: str, inicio: int) -> str:
    nivel, i = 0, inicio
    while i < len(texto):
        if texto[i] == "(":
            nivel += 1
        elif texto[i] == ")":
            nivel -= 1
            if nivel == 0:
                return texto[inicio + 1:i]
        i += 1
    return ""


def _fatiar(corpo: str) -> list[str]:
    """Divide o corpo de um CREATE TABLE nas definicoes (',' dentro de parenteses nao separa)."""
    partes, atual, nivel, em_string = [], [], 0, False
    for c in corpo:
        if em_string:
            atual.append(c)
            if c == "'":
                em_string = False
            continue
        if c == "'":
            em_string = True
        elif c == "(":
            nivel += 1
        elif c == ")":
            nivel -= 1
        elif c == "," and nivel == 0:
            partes.append("".join(atual))
            atual = []
            continue
        atual.append(c)
    partes.append("".join(atual))
    return [p.strip() for p in partes if p.strip()]


def colunas_postgres() -> dict[str, list[str]]:
    texto = config.SCHEMA_PG_PATH.read_text(encoding="utf-8")
    resultado: dict[str, list[str]] = {}
    for achado in re.finditer(r"CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)\s*\(", texto, re.IGNORECASE):
        colunas = []
        for linha in _fatiar(_corpo(texto, achado.end() - 1)):
            primeira = linha.split()[0].lower()
            if primeira in ("primary", "foreign", "unique", "check", "constraint"):
                continue
            colunas.append(primeira)
        resultado[achado.group(1).lower()] = sorted(colunas)
    return resultado


def verificar_schemas() -> None:
    print("\n== schema.sql x schema_pg.sql ==")
    sq, pg = colunas_sqlite(), colunas_postgres()
    ok(bool(pg), f"{len(pg)} tabelas lidas do schema_pg.sql")
    ok(set(sq) == set(pg), f"mesmas tabelas nos dois schemas (so SQLite: {sorted(set(sq) - set(pg))}; "
                           f"so Postgres: {sorted(set(pg) - set(sq))})")
    divergentes = [t for t in sorted(set(sq) & set(pg)) if sq[t] != pg[t]]
    for tabela in divergentes:
        print(f"       SQLite   {tabela}: {sq[tabela]}\n"
              f"       Postgres {tabela}: {pg[tabela]}")
    ok(not divergentes, f"colunas conferidas tabela por tabela ({len(sq)} tabelas)")
    padrao = r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)"
    i_sq = set(re.findall(padrao, config.SCHEMA_PATH.read_text(encoding="utf-8"), re.IGNORECASE))
    i_pg = set(re.findall(padrao, config.SCHEMA_PG_PATH.read_text(encoding="utf-8"), re.IGNORECASE))
    ok(not (i_sq - i_pg), f"todos os indices do SQLite existem no Postgres (faltam: {sorted(i_sq - i_pg)}); "
                          f"extras so no Postgres: {sorted(i_pg - i_sq)}")


def verificar_script() -> None:
    print("\n== schema_pg.sql comando por comando ==")
    comandos = db.dividir_comandos(config.SCHEMA_PG_PATH.read_text(encoding="utf-8"))
    esperados = len(re.findall(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)",
                               config.SCHEMA_PG_PATH.read_text(encoding="utf-8"), re.IGNORECASE))
    ok(len(comandos) == esperados,
       f"{len(comandos)} comandos separados pelo divisor, mesmo numero de CREATE ({esperados})")
    sobras = [c for c in comandos if "--" in c or not c.strip()]
    ok(not sobras, f"nenhum comando com comentario pendurado ({len(sobras)} sobras)")
    quebrados = [c for c in comandos if "CREATE TABLE" in c.upper() and c.count("(") != c.count(")")]
    ok(not quebrados, "todos os CREATE TABLE com parenteses balanceados")


def main() -> int:
    print("verificador de dialecto |", db.resumo())
    verificar_fonte()
    verificar_schemas()
    verificar_script()
    print("\n" + "=" * 66)
    if FALHAS:
        print(f"[FALHOU] {len(FALHAS)} problema(s):")
        for f in FALHAS:
            print("  -", f)
        return 1
    print("[OK] SQL, schemas e traducao coerentes nos dois motores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

