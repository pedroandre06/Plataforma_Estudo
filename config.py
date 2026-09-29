"""Configuracao central da Plataforma de Estudos (Pos em Engenharia de Dados).

Banco de dados - o mesmo codigo roda em dois motores, sem mudar uma linha de SQL:
  * SQLite  (padrao): arquivo data/platform.db, zero configuracao, otimo no computador.
  * PostgreSQL (Neon, Supabase, Railway, Docker...): basta definir DATABASE_URL
    (ou POSTGRES_URL) no ambiente. E o modo usado no deploy da Vercel.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------- banco de dados
DB_PATH = BASE_DIR / "data" / "platform.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
SCHEMA_PG_PATH = BASE_DIR / "schema_pg.sql"      # mesmo schema, dialeto PostgreSQL
MATERIAIS_DIR = BASE_DIR / "data" / "materiais"   # texto extraido dos PDFs
CONTENT_DIR = BASE_DIR / "data" / "content"       # banco de questoes (JSON)


# ------------------------------------------------------------------ PostgreSQL
def _env(nome: str) -> str:
    return (os.environ.get(nome) or "").strip()


def dsn_postgres() -> str:
    """String de conexao do Postgres definida no ambiente (vazio = usar SQLite)."""
    return _env("DATABASE_URL") or _env("POSTGRES_URL") or _env("DATABASE_POSTGRES")


def usar_postgres() -> bool:
    """True quando a aplicacao deve conversar com PostgreSQL em vez de SQLite."""
    return bool(dsn_postgres())


def resumo_dsn() -> str:
    """DSN sem a senha, para aparecer em logs e mensagens (nunca imprima a senha)."""
    dsn = dsn_postgres()
    if not dsn:
        return f"sqlite:///{DB_PATH}"
    esquema, _, resto = dsn.partition("://")
    _, _, sem_senha = resto.rpartition("@")
    return f"{esquema}://{sem_senha}" if sem_senha else f"{esquema}://(senha oculta)"


def limite_upload_bytes() -> int:
    """Limite de upload em bytes (a Vercel corta requisicoes acima de ~4,5 MB)."""
    try:
        megas = int(_env("MAX_UPLOAD_MB") or "8")
    except ValueError:
        megas = 8
    return megas * 1024 * 1024

# --------------------------------------------------- material original do curso
# Pastas onde estao os PDFs das disciplinas (nao copiamos os arquivos).
# O curso costuma ficar no OneDrive; "Documents" pode ter apenas uma copia antiga.
# Para apontar para outro lugar: set DOCS_DIR=C:\caminho\da\pasta
def pastas_de_material() -> list[Path]:
    """Todas as pastas que podem conter os PDFs, na ordem de preferencia."""
    candidatas: list[Path] = []
    extra = os.environ.get("DOCS_DIR")
    if extra:
        candidatas.append(Path(extra))
    candidatas += [Path.home() / "OneDrive" / "Pós dados",
                   Path.home() / "Documents" / "Pós dados"]
    vistas: set[str] = set()
    saida: list[Path] = []
    for pasta in candidatas:
        marca = str(pasta.resolve()).lower()
        if pasta.is_dir() and marca not in vistas:
            vistas.add(marca)
            saida.append(pasta)
    return saida


DOCS_DIR = (pastas_de_material() or [Path.home() / "Documents" / "Pós dados"])[0]

# ------------------------------------------------------------------- seguranca
SECRET_KEY_FILE = BASE_DIR / "data" / ".secret_key"
SESSION_DIAS = 30
MIN_SENHA = 4
MIN_USUARIO = 3
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_MINUTOS = 2
# Cadastro aberto por padrao; PERMITIR_REGISTRO=0 no ambiente fecha a pagina /registro.
PERMITIR_REGISTRO = (_env("PERMITIR_REGISTRO") or "1").lower() not in ("0", "false", "nao", "off")

# ------------------------------------------------------------------- simulados
NOTA_CORTE_PADRAO = 6.0
SIMULADO_MATERIA_QUESTOES = 20
SIMULADO_MATERIA_MINUTOS = 40
SIMULADO_GERAL_QUESTOES = 30
SIMULADO_GERAL_MINUTOS = 60


_CHAVE_EPHEMERA: str | None = None


def secret_key() -> str:
    """Chave que assina o cookie de sessao.

    Ordem: variavel SECRET_KEY (obrigatoria na nuvem, onde o disco e somente
    leitura) -> arquivo data/.secret_key -> chave aleatoria valida so enquanto o
    processo estiver de pe (sessoes caem a cada reinicio do servidor).
    """
    valor = _env("SECRET_KEY")
    if valor:
        return valor
    try:
        SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SECRET_KEY_FILE.exists():
            gravada = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if gravada:
                return gravada
        nova = secrets.token_hex(32)
        SECRET_KEY_FILE.write_text(nova, encoding="utf-8")
        return nova
    except OSError:  # disco somente leitura (Vercel, container etc.)
        global _CHAVE_EPHEMERA
        if _CHAVE_EPHEMERA is None:
            _CHAVE_EPHEMERA = secrets.token_hex(32)
            print("[config] aviso: disco somente leitura e SECRET_KEY ausente - usando chave "
                  "temporaria (defina SECRET_KEY no ambiente para sessoes persistentes).",
                  file=sys.stderr)
        return _CHAVE_EPHEMERA
