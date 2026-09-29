"""Configuracao central da Plataforma de Estudos (Pos em Engenharia de Dados)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------- banco de dados
DB_PATH = BASE_DIR / "data" / "platform.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
MATERIAIS_DIR = BASE_DIR / "data" / "materiais"   # texto extraido dos PDFs
CONTENT_DIR = BASE_DIR / "data" / "content"       # banco de questoes (JSON)

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
PERMITIR_REGISTRO = True

# ------------------------------------------------------------------- simulados
NOTA_CORTE_PADRAO = 6.0
SIMULADO_MATERIA_QUESTOES = 20
SIMULADO_MATERIA_MINUTOS = 40
SIMULADO_GERAL_QUESTOES = 30
SIMULADO_GERAL_MINUTOS = 60


def secret_key() -> str:
    """Le (ou cria) uma chave de sessao persistente em data/.secret_key."""
    SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_FILE.exists():
        valor = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
        if valor:
            return valor
    valor = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(valor, encoding="utf-8")
    return valor
