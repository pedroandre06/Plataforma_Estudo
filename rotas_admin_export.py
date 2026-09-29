"""Exportação do banco de questões (JSON e CSV)."""
from __future__ import annotations

import csv
import io
import json

from flask import Blueprint, Response

import db
from comum import admin_required

bp = Blueprint("admin_exp", __name__)

CABECALHO_CSV = ["materia_slug", "modulo_slug", "enunciado", "tipo", "dificuldade", "topico",
                 "explicacao", "referencia", "alternativa_1", "alternativa_2", "alternativa_3",
                 "alternativa_4", "correta"]


def perguntas_do_modulo(conn, modulo_id):
    saida = []
    for p in db.q(conn, "SELECT * FROM perguntas WHERE modulo_id = ? AND ativo = 1 ORDER BY id",
                  [modulo_id]):
        alts = db.q(conn, "SELECT * FROM alternativas WHERE pergunta_id = ? ORDER BY ordem", [p["id"]])
        if len(alts) < 2:
            continue
        saida.append({"enunciado": p["enunciado"], "tipo": p["tipo"], "dificuldade": p["dificuldade"],
                      "topico": p["topico"], "explicacao": p["explicacao"],
                      "referencia": p["referencia"], "alternativas": [a["texto"] for a in alts],
                      "correta": next((i for i, a in enumerate(alts) if a["correta"]), 0)})
    return saida


@bp.route("/admin/exportar")
@admin_required
def exportar():
    conn = db.get_db()
    modulos = db.q(conn, """
        SELECT mt.slug AS materia_slug, mo.id, mo.slug AS modulo_slug
        FROM modulos mo JOIN materias mt ON mt.id = mo.materia_id ORDER BY mt.ordem, mo.ordem
    """)
    if request_formato() == "csv":
        saida = io.StringIO()
        escritor = csv.writer(saida, delimiter=";")
        escritor.writerow(CABECALHO_CSV)
        for mo in modulos:
            for p in perguntas_do_modulo(conn, mo["id"]):
                escritor.writerow([mo["materia_slug"], mo["modulo_slug"], p["enunciado"], p["tipo"],
                                   p["dificuldade"], p["topico"] or "", p["explicacao"] or "",
                                   p["referencia"] or ""] + p["alternativas"] + [p["correta"]])
        return Response(saida.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=questoes.csv"})
    dados = [{"materia_slug": mo["materia_slug"], "modulo_slug": mo["modulo_slug"],
              "perguntas": [{"e": p["enunciado"], "tp": p["tipo"], "d": p["dificuldade"], "t": p["topico"],
                             "x": p["explicacao"], "r": p["referencia"], "a": p["alternativas"],
                             "c": p["correta"]} for p in perguntas_do_modulo(conn, mo["id"])]}
             for mo in modulos]
    return Response(json.dumps(dados, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=questoes.json"})


def request_formato() -> str:
    from flask import request

    return request.args.get("formato", "json")
