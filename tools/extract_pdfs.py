"""Extrai o texto dos PDFs das disciplinas para data/materiais/*.txt.

Uso:
    .venv\\Scripts\\python.exe tools\\extract_pdfs.py

Gera:
    data/materiais/<materia>/<arquivo>.txt   -> texto pagina a pagina
    data/materiais/manifest.json             -> metadados (paginas, tamanho, amostra)
Os PDFs originais NAO sao copiados nem alterados.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config  # noqa: E402
from pypdf import PdfReader  # noqa: E402


def slug(texto: str) -> str:
    """'Interações entre big data' -> 'interacoes-entre-big-data'."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpo = "".join(c if c.isalnum() else "-" for c in sem_acento.lower())
    while "--" in limpo:
        limpo = limpo.replace("--", "-")
    return limpo.strip("-") or "arquivo"


def extrair_paginas(caminho: Path) -> tuple[str, int]:
    leitor = PdfReader(str(caminho))
    partes: list[str] = []
    for i, pagina in enumerate(leitor.pages, start=1):
        try:
            texto = pagina.extract_text() or ""
        except Exception as erro:  # pragma: no cover - PDF problematico
            texto = f"[erro ao extrair pagina: {erro}]"
        partes.append(f"\n\n===== PAGINA {i} =====\n{texto.strip()}")
    return "".join(partes), len(leitor.pages)


def principal() -> int:
    raizes = config.pastas_de_material()
    if not raizes:
        print(f"[erro] pasta de PDFs nao encontrada: {config.DOCS_DIR}")
        return 1

    config.MATERIAIS_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    # Junta os PDFs de todas as pastas: quando o mesmo arquivo existe em duas
    # (ex.: OneDrive e Documents), vale a copia mais recente.
    candidatos: dict[tuple[str, str], Path] = {}
    ignorados: dict[tuple[str, str], Path] = {}
    for raiz in raizes:
        print(f"[material] lendo {raiz}")
        for materia in sorted(p for p in raiz.iterdir() if p.is_dir()):
            for pdf in sorted(materia.glob("*.pdf")):
                chave = (slug(materia.name), pdf.name)
                atual = candidatos.get(chave)
                if atual is None:
                    candidatos[chave] = pdf
                elif pdf.stat().st_mtime > atual.stat().st_mtime:
                    candidatos[chave] = pdf
                    ignorados[chave] = atual
                else:
                    ignorados[chave] = pdf

    for (materia_slug, _nome), pdf in sorted(candidatos.items()):
        destino = config.MATERIAIS_DIR / materia_slug
        destino.mkdir(parents=True, exist_ok=True)
        try:
            texto, paginas = extrair_paginas(pdf)
        except Exception as erro:
            print(f"  [falha] {pdf.name}: {erro}")
            continue
        arquivo = destino / f"{slug(pdf.stem)}.txt"
        arquivo.write_text(texto, encoding="utf-8")
        manifest.append(
            {
                "materia": pdf.parent.name,
                "materia_slug": materia_slug,
                "raiz": pdf.parent.parent.name,
                "pdf": str(pdf),
                "pdf_nome": pdf.name,
                "texto": str(arquivo),
                "paginas": paginas,
                "caracteres": len(texto),
                "amostra": " ".join(texto.split())[:400],
            }
        )
        print(f"  ok {pdf.parent.name[:26]:28} {pdf.name[:12]:14} {paginas:>4} pag  {len(texto):>8} chars")

    for (materia_slug, nome), pdf in sorted(ignorados.items()):
        print(f"  (ignorado: copia mais antiga de {nome} em {pdf.parent.parent.name})")

    (config.MATERIAIS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[ok] {len(manifest)} PDFs extraidos de {len(raizes)} pasta(s) -> {config.MATERIAIS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
