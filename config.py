"""Configuracao central da Plataforma de Estudos (Pos em Engenharia de Dados).

Banco de dados - o mesmo codigo roda em dois motores, sem mudar uma linha de SQL:
  * SQLite  (padrao): arquivo data/platform.db, zero configuracao, otimo no computador.
  * PostgreSQL (Neon, Supabase, Railway, Docker...): basta definir DATABASE_URL
    (ou POSTGRES_URL) no ambiente. E o modo usado no deploy da Vercel.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sys
import tempfile
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


def pasta_gravavel(pasta: Path) -> bool:
    """True quando da para criar/gravar arquivos na pasta.

    No deploy da Vercel o disco e somente leitura; detectar isso evita o erro 500
    (o SQLite nao consegue abrir o arquivo e a requisicao inteira quebra).
    """
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        teste = pasta / ".escrita_ok"
        teste.write_text("ok", encoding="utf-8")
        teste.unlink()
        return True
    except OSError:
        return False


_caminho_sqlite_escolhido: dict[str, Path] = {}


def caminho_sqlite() -> Path:
    """Arquivo SQLite em uso.

    Preferencia: data/platform.db. Se o disco for somente leitura (Vercel sem
    DATABASE_URL), cai para um diretorio temporario gravavel, para o site ao menos
    nao cair com 500 - ainda que, nesse caso, os dados fiquem efemeros.
    """
    chave = str(DB_PATH)
    escolhido = _caminho_sqlite_escolhido.get(chave)
    if escolhido is not None:
        return escolhido
    if pasta_gravavel(DB_PATH.parent):
        escolhido = DB_PATH
    else:
        try:
            pasta_temp = Path(tempfile.gettempdir()) / "plataforma-estudos"
            pasta_temp.mkdir(parents=True, exist_ok=True)
            escolhido = pasta_temp / "platform.db"
        except OSError:
            escolhido = DB_PATH
        print(f"[config] aviso: {DB_PATH.parent} parece somente leitura; usando SQLite "
              f"temporario em {escolhido}. Defina DATABASE_URL para dados persistentes.",
              file=sys.stderr)
    _caminho_sqlite_escolhido[chave] = escolhido
    return escolhido


def resumo_dsn() -> str:
    """DSN sem a senha, para aparecer em logs e mensagens (nunca imprima a senha)."""
    dsn = dsn_postgres()
    if not dsn:
        return f"sqlite:///{caminho_sqlite()}"
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
MIN_SENHA = 8
MIN_USUARIO = 3
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_MINUTOS = 2
# Cadastro aberto por padrao; PERMITIR_REGISTRO=0 no ambiente fecha a pagina /registro.
PERMITIR_REGISTRO = (_env("PERMITIR_REGISTRO") or "1").lower() not in ("0", "false", "nao", "off")

# Provisionamento automatico no primeiro acesso (o que faz o deploy da Vercel
# funcionar sem passo manual). Coloque 0 no ambiente para desligar.
INIT_DB_ON_STARTUP = (_env("INIT_DB_ON_STARTUP") or "1").lower() not in ("0", "false", "nao", "off")
SEED_ON_STARTUP = (_env("SEED_ON_STARTUP") or "1").lower() not in ("0", "false", "nao", "off")

# ------------------------------------------------------------------- simulados
NOTA_CORTE_PADRAO = 6.0
SIMULADO_MATERIA_QUESTOES = 20
SIMULADO_MATERIA_MINUTOS = 40
SIMULADO_GERAL_QUESTOES = 30
SIMULADO_GERAL_MINUTOS = 60


_CHAVE_EPHEMERA: str | None = None
_ORIGEM_CHAVE = "desconhecida"


def origem_chave() -> str:
    """De onde veio a chave de sessao: 'ambiente', 'arquivo', 'dsn' ou 'efemera'.

    'efemera' significa que cada instancia/reinicio do servidor assina os cookies
    com uma chave diferente - todo mundo e deslogado e os tokens CSRF deixam de
    bater. Use no /healthz para diagnosticar "pede login toda hora".
    """
    return _ORIGEM_CHAVE


def secret_key() -> str:
    """Chave que assina o cookie de sessao.

    Ordem: variavel SECRET_KEY (recomendada na nuvem) -> arquivo data/.secret_key ->
    chave derivada do DATABASE_URL (disco somente leitura, mas ESTAVEL entre
    instancias, e' o que faz o deploy da Vercel manter a sessao) -> chave aleatoria
    valida so enquanto o processo estiver de pe (ultimo recurso; causa logout
    aleatorio e erro de CSRF, por isso avisa no log).
    """
    global _CHAVE_EPHEMERA, _ORIGEM_CHAVE
    valor = _env("SECRET_KEY")
    if valor:
        _ORIGEM_CHAVE = "ambiente"
        return valor
    try:
        SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SECRET_KEY_FILE.exists():
            gravada = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if gravada:
                _ORIGEM_CHAVE = "arquivo"
                return gravada
        nova = secrets.token_hex(32)
        SECRET_KEY_FILE.write_text(nova, encoding="utf-8")
        _ORIGEM_CHAVE = "arquivo"
        return nova
    except OSError:  # disco somente leitura (Vercel, container etc.)
        # Sem SECRET_KEY e sem arquivo, a chave ainda pode ser ESTAVEL se o
        # DATABASE_URL existir: o Postgres e compartilhado por todas as
        # instancias, entao derivamos a chave dele (o DSN ja e um segredo do
        # ambiente; quem tem o DSN tem o banco inteiro). Assim o login persiste
        # mesmo sem configurar SECRET_KEY.
        dsn = dsn_postgres()
        if dsn:
            _ORIGEM_CHAVE = "dsn"
            print("[config] aviso: SECRET_KEY ausente e disco somente leitura - derivando "
                  "a chave de sessao do DATABASE_URL (funciona, mas defina SECRET_KEY "
                  "explicitamente para trocar a chave sem derrubar as sessoes).",
                  file=sys.stderr)
            return hashlib.sha256(("[sessao] " + dsn).encode("utf-8")).hexdigest()
        _ORIGEM_CHAVE = "efemera"
        if _CHAVE_EPHEMERA is None:
            _CHAVE_EPHEMERA = secrets.token_hex(32)
            print("[config] aviso: disco somente leitura, SECRET_KEY e DATABASE_URL ausentes - "
                  "usando chave temporaria: cada reinicio desloga todo mundo e quebra o CSRF "
                  "(defina SECRET_KEY no ambiente para sessoes persistentes).",
                  file=sys.stderr)
        return _CHAVE_EPHEMERA
