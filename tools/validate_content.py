"""Valida os arquivos de conteudo (data/content/**/*.json).

Uso:
    .venv\\Scripts\\python.exe tools\\validate_content.py

Formato compacto das perguntas:
    e  = enunciado            tp = tipo ('multipla' | 'vf'), padrao 'multipla'
    a  = lista de alternativas (2 a 6)
    c  = indice (0-based) da alternativa correta
    d  = dificuldade ('facil' | 'medio' | 'dificil')
    t  = topico      x = explicacao      r = referencia (bloco do material)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config  # noqa: E402

DIFICULDADES = {"facil", "medio", "dificil"}
TIPOS = {"multipla", "vf"}
erros: list[str] = []


def validar_pergunta(caminho: Path, i: int, p: dict) -> None:
    rotulo = f"{caminho.name} pergunta #{i + 1}"
    if not isinstance(p, dict):
        erros.append(f"{rotulo}: nao e um objeto")
        return
    for campo in ("e", "a", "c"):
        if campo not in p:
            erros.append(f"{rotulo}: campo obrigatorio ausente: {campo}")
    alts = p.get("a") or []
    if not isinstance(alts, list) or len(alts) < 2:
        erros.append(f"{rotulo}: precisa de pelo menos 2 alternativas")
    if len(set(alts)) != len(alts):
        erros.append(f"{rotulo}: alternativas duplicadas")
    correta = p.get("c")
    if not isinstance(correta, int) or not (0 <= correta < len(alts)):
        erros.append(f"{rotulo}: indice da correta invalido ({correta})")
    if p.get("d", "medio") not in DIFICULDADES:
        erros.append(f"{rotulo}: dificuldade invalida ({p.get('d')})")
    if p.get("tp", "multipla") not in TIPOS:
        erros.append(f"{rotulo}: tipo invalido ({p.get('tp')})")
    if p.get("tp") == "vf" and len(alts) != 2:
        erros.append(f"{rotulo}: pergunta V/F deve ter exatamente 2 alternativas")
    if not p.get("x"):
        erros.append(f"{rotulo}: sem explicacao (campo x)")
    if not p.get("t"):
        erros.append(f"{rotulo}: sem topico (campo t)")


def principal() -> int:
    arquivos = sorted(config.CONTENT_DIR.rglob("*.json"))
    if not arquivos:
        print(f"[erro] nenhum arquivo de conteudo em {config.CONTENT_DIR}")
        return 1

    materias: dict[str, str] = {}
    resumo: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    modulos_vistos: dict[str, int] = {}
    total = 0

    for caminho in arquivos:
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except json.JSONDecodeError as erro:
            erros.append(f"{caminho.name}: JSON invalido ({erro})")
            continue

        if isinstance(dados, list):  # materias.json
            for m in dados:
                if not m.get("slug") or not m.get("nome"):
                    erros.append(f"{caminho.name}: materia sem slug/nome")
                    continue
                materias[m["slug"]] = m["nome"]
            continue

        materia = dados.get("materia_slug")
        modulo = dados.get("modulo_slug")
        if not materia or not modulo:
            erros.append(f"{caminho.name}: falta materia_slug/modulo_slug")
            continue
        if "modulo" in dados:
            meta = dados["modulo"]
            if not meta.get("nome"):
                erros.append(f"{caminho.name}: modulo sem nome")
            modulos_vistos[modulo] = modulos_vistos.get(modulo, 0) + 1

        perguntas = dados.get("perguntas", [])
        for i, p in enumerate(perguntas):
            validar_pergunta(caminho, i, p)
            resumo[materia][modulo][p.get("d", "medio")] += 1
        total += len(perguntas)

    print("MATERIAS DECLARADAS:", ", ".join(sorted(materias)) or "(nenhuma)")
    print()
    for materia in sorted(resumo):
        nome = materias.get(materia, f"[SEM DECLARACAO] {materia}")
        print(f"* {nome}  ({materia})")
        for modulo in sorted(resumo[materia]):
            cont = resumo[materia][modulo]
            marca = "" if modulos_vistos.get(modulo) else " [sem arquivo de cabecalho]"
            print(
                f"    - {modulo:28} {sum(cont.values()):>3} perguntas "
                f"(facil {cont['facil']:>2} / medio {cont['medio']:>2} / dificil {cont['dificil']:>2}){marca}"
            )
    print(f"\nTOTAL DE PERGUNTAS: {total}")

    for slug in resumo:
        if slug not in materias:
            erros.append(f"materia '{slug}' usada nos modulos mas nao declarada em materias.json")

    if erros:
        print(f"\n[ERROS] {len(erros)}")
        for e in erros:
            print("  -", e)
        return 1
    print("\n[OK] conteudo valido")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
