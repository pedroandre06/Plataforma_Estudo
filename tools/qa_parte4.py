"""Cenário 4: importação e prova oficial (modo sem senha)."""
from __future__ import annotations

from io import BytesIO

import db
from qa_common import ok, texto, titulo


def executar(cliente, tok: str, contexto: dict) -> None:  # noqa: ARG001
    conexao = db.connect()

    titulo("Importação de questões (JSON)")
    corpo = [{"materia_slug": "data-warehouse", "modulo_slug": "fundamentos-dw",
              "perguntas": [{"e": "Pergunta importada pelo teste?",
                             "a": ["Errada", "Certa", "Outra"], "c": 1, "d": "facil",
                             "t": "Importação", "x": "Importada via JSON."}]}]
    resposta = cliente.post("/admin/importar",
                            data={"_csrf": tok,
                                  "arquivo": (BytesIO(str(corpo).replace("'", '"').encode("utf-8")),
                                              "lote.json")},
                            content_type="multipart/form-data", follow_redirects=True)
    importada = db.q1(conexao, "SELECT * FROM perguntas WHERE enunciado LIKE 'Pergunta importada%'")
    ok(importada is not None and "1 inseridas" in texto(resposta),
       "importação de JSON insere a questão no módulo correto")
    if importada:
        ok(db.q1(conexao, "SELECT texto FROM alternativas WHERE pergunta_id = ? AND correta = 1",
                 [importada["id"]])["texto"] == "Certa", "alternativa correta da importação")
        db.run(conexao, "DELETE FROM perguntas WHERE id = ?", [importada["id"]])

    titulo("Prova oficial (questões fixas e limite de tentativas)")
    ids = [str(r["id"]) for r in db.q(conexao, "SELECT id FROM perguntas LIMIT 5")]
    resposta = cliente.post("/admin/prova/nova",
                            data={"_csrf": tok, "nome": "Prova do teste", "tempo_min": "30",
                                  "nota_corte": "6", "max_tentativas": "1", "pergunta_id": ids},
                            follow_redirects=True)
    prova = db.q1(conexao, "SELECT * FROM simulados WHERE tipo = 'oficial' ORDER BY id DESC LIMIT 1")
    ok(prova is not None and resposta.status_code == 200, "prova oficial criada pelo admin")
    if prova:
        fixas = db.q1(conexao, "SELECT COUNT(*) AS n FROM simulado_questoes WHERE simulado_id = ?",
                      [prova["id"]])["n"]
        ok(fixas == 5 and prova["tempo_min"] == 30 and prova["max_tentativas"] == 1,
           "prova oficial com 5 questões fixas, 30 min e 1 tentativa")
        cliente.post(f"/simulados/iniciar/{prova['id']}", data={"_csrf": tok}, follow_redirects=True)
        tent = db.q1(conexao, "SELECT * FROM tentativas WHERE simulado_id = ? ORDER BY id DESC LIMIT 1",
                     [prova["id"]])
        questoes_da_prova = db.q1(conexao, "SELECT COUNT(*) AS n FROM respostas WHERE tentativa_id = ?",
                                  [tent["id"]])["n"]
        ok(questoes_da_prova == 5, "execução da prova oficial traz as 5 questões fixas")
        cliente.post(f"/simulado/{tent['id']}/entregar", data={"_csrf": tok})
        resposta = cliente.post(f"/simulados/iniciar/{prova['id']}", data={"_csrf": tok},
                                follow_redirects=True)
        ok("Limite de tentativas" in texto(resposta),
           "limite de tentativas da prova oficial é respeitado")
        cliente.post(f"/admin/prova/{prova['id']}/excluir", data={"_csrf": tok})
        ok(db.q1(conexao, "SELECT 1 FROM simulados WHERE id = ?", [prova["id"]]) is None,
           "prova oficial pode ser excluída pelo admin")
