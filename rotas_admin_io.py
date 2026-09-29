"""Importação de questões (JSON no formato compacto ou CSV)."""
from __future__ import annotations

import csv
import io
import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

import db
from comum import admin_required

bp = Blueprint("admin_io", __name__)

CABECALHO_CSV = ["materia_slug", "modulo_slug", "enunciado", "tipo", "dificuldade", "topico",
                 "explicacao", "referencia", "alternativa_1", "alternativa_2", "alternativa_3",
                 "alternativa_4", "correta"]


def _modulo_id(conn, materia_slug, modulo_slug):
    linha = db.q1(conn, """SELECT mo.id FROM modulos mo JOIN materias mt ON mt.id = mo.materia_id
                           WHERE mt.slug = ? AND mo.slug = ?""", [materia_slug, modulo_slug])
    return linha["id"] if linha else None


def inserir_pergunta(conn, modulo_id, p) -> bool:
    """Insere uma questão no formato compacto (e, a, c, d, t, x, r, tp)."""
    enunciado = (p.get("e") or p.get("enunciado") or "").strip()
    alternativas = p.get("a") or p.get("alternativas") or []
    correta = p.get("c")
    if not enunciado or len(alternativas) < 2 or correta is None:
        return False
    try:
        indice = int(correta)
    except (TypeError, ValueError):
        return False
    if not 0 <= indice < len(alternativas):
        return False
    dificuldade = p.get("d") or p.get("dificuldade") or "medio"
    if dificuldade not in ("facil", "medio", "dificil"):
        dificuldade = "medio"
    pid = db.run(conn, """INSERT INTO perguntas (modulo_id, enunciado, tipo, dificuldade, topico,
                    explicacao, referencia) VALUES (?,?,?,?,?,?,?)""",
                 [modulo_id, enunciado, p.get("tp") or p.get("tipo") or "multipla", dificuldade,
                  p.get("t") or p.get("topico"), p.get("x") or p.get("explicacao"),
                  p.get("r") or p.get("referencia")])
    for ordem, texto in enumerate(alternativas):
        db.run(conn, "INSERT INTO alternativas (pergunta_id, texto, correta, ordem) VALUES (?,?,?,?)",
               [pid, str(texto).strip(), 1 if ordem == indice else 0, ordem])
    return True


@bp.route("/admin/importar", methods=["GET", "POST"])
@admin_required
def importar():
    conn = db.get_db()
    if request.method == "POST":
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            flash("Selecione um arquivo JSON ou CSV.", "erro")
            return redirect(url_for("admin_io.importar"))
        conteudo = arquivo.read().decode("utf-8-sig", errors="replace")
        inseridas = ignoradas = 0
        try:
            if arquivo.filename.lower().endswith(".csv"):
                for linha in csv.DictReader(io.StringIO(conteudo), delimiter=";"):
                    alts = [linha.get(f"alternativa_{i}", "") for i in range(1, 5)]
                    item = {"e": linha.get("enunciado"), "a": [a for a in alts if a and a.strip()],
                            "c": linha.get("correta") or 0, "d": linha.get("dificuldade"),
                            "t": linha.get("topico"), "x": linha.get("explicacao"),
                            "r": linha.get("referencia"), "tp": linha.get("tipo")}
                    mid = _modulo_id(conn, linha.get("materia_slug"), linha.get("modulo_slug"))
                    if mid and inserir_pergunta(conn, mid, item):
                        inseridas += 1
                    else:
                        ignoradas += 1
            else:
                dados = json.loads(conteudo)
                for lote in (dados if isinstance(dados, list) else [dados]):
                    mid = lote.get("modulo_id") or _modulo_id(conn, lote.get("materia_slug"),
                                                              lote.get("modulo_slug"))
                    perguntas = lote.get("perguntas", [])
                    if not mid:
                        ignoradas += len(perguntas)
                        continue
                    for p in perguntas:
                        if inserir_pergunta(conn, mid, p):
                            inseridas += 1
                        else:
                            ignoradas += 1
        except Exception as erro:  # noqa: BLE001
            flash(f"Falha ao importar: {erro}", "erro")
            return redirect(url_for("admin_io.importar"))
        flash(f"Importação concluída: {inseridas} inseridas, {ignoradas} ignoradas.", "ok")
        return redirect(url_for("admin_q.perguntas"))
    return render_template("admin_importar.html",
                           modulos=db.q(conn, """SELECT mo.slug AS modulo_slug, mo.nome,
                                                 mt.slug AS materia_slug, mt.nome AS materia_nome
                                                 FROM modulos mo JOIN materias mt ON mt.id = mo.materia_id
                                                 ORDER BY mt.ordem, mo.ordem"""))
