"""Cenário 2: simulados por matéria, geral e expiração de tempo."""
from __future__ import annotations

import json

import db
from qa_common import ok, texto, titulo


def executar(cliente, tok: str) -> None:
    conexao = db.connect()

    titulo("Simulados por matéria e geral (execução completa)")
    simulados = db.q(conexao, "SELECT * FROM simulados WHERE tipo IN ('materia', 'geral')"
                              " ORDER BY id LIMIT 2")
    for simulado in simulados:
        cliente.post(f"/simulados/iniciar/{simulado['id']}", data={"_csrf": tok},
                     follow_redirects=True)
        tent = db.q1(conexao, "SELECT * FROM tentativas WHERE simulado_id = ? ORDER BY id DESC LIMIT 1",
                     [simulado["id"]])
        ok(tent is not None and tent["status"] == "em_andamento",
           f"simulado iniciado em andamento: {simulado['nome'][:38]}")
        pagina = cliente.get(f"/simulado/{tent['id']}")
        corpo = texto(pagina)
        ok(pagina.status_code == 200 and "grade-questoes" in corpo,
           "tela de execução exibe a grade de questões")
        ok("js-restante" in corpo or "sem limite de tempo" in corpo,
           "tela de execução exibe o cronômetro")
        total = db.q1(conexao, "SELECT COUNT(*) AS n FROM respostas WHERE tentativa_id = ?",
                      [tent["id"]])["n"]
        ok(total == simulado["n_questoes"], f"sorteio respeitou o nº de questões ({total})")

        linha = db.q(conexao, "SELECT * FROM respostas WHERE tentativa_id = ? ORDER BY ordem LIMIT 1",
                     [tent["id"]])[0]
        certa = db.q1(conexao, "SELECT id FROM alternativas WHERE pergunta_id = ? AND correta = 1",
                      [linha["pergunta_id"]])
        resposta = cliente.post(f"/api/simulado/{tent['id']}/resposta",
                                json={"pergunta_id": linha["pergunta_id"],
                                      "alternativa_id": certa["id"]})
        ok(resposta.status_code == 200
           and json.loads(texto(resposta))["resumo"]["respondidas"] == 1,
           "auto-save grava a resposta pela API")
        resposta = cliente.post(f"/api/simulado/{tent['id']}/resposta",
                                json={"pergunta_id": linha["pergunta_id"], "marcar": 1})
        ok(json.loads(texto(resposta))["resumo"]["marcadas"] == [0],
           "marcar para revisar funciona pela API")
        cliente.post(f"/simulado/{tent['id']}/entregar", data={"_csrf": tok}, follow_redirects=True)
        entregue = db.q1(conexao, "SELECT * FROM tentativas WHERE id = ?", [tent["id"]])
        ok(entregue["status"] == "entregue" and entregue["nota"] is not None,
           f"simulado corrigido: nota {entregue['nota']} ({entregue['acertos']}/{entregue['total']})")
        resultado = texto(cliente.get(f"/simulado/{tent['id']}/resultado"))
        ok("Gabarito comentado" in resultado and "refazer-erradas" in resultado,
           "resultado traz análise, gabarito comentado e refazer erradas")

    titulo("Expiração do tempo (auto-entrega)")
    simulado = db.q1(conexao, "SELECT * FROM simulados WHERE tipo = 'materia' LIMIT 1")
    cliente.post(f"/simulados/iniciar/{simulado['id']}", data={"_csrf": tok}, follow_redirects=True)
    tent = db.q1(conexao, "SELECT * FROM tentativas WHERE simulado_id = ? ORDER BY id DESC LIMIT 1",
                 [simulado["id"]])
    db.run(conexao, "UPDATE tentativas SET limite_em = '2000-01-01 00:00:00' WHERE id = ?",
           [tent["id"]])
    resposta = cliente.post(f"/simulado/{tent['id']}/entregar", data={"_csrf": tok},
                            follow_redirects=True)
    expirada = db.q1(conexao, "SELECT * FROM tentativas WHERE id = ?", [tent["id"]])
    ok(expirada["status"] == "expirada" and "Tempo esgotado" in texto(resposta),
       "simulado com prazo vencido é marcado como expirado, com aviso ao aluno")
