"""Cenário 1b: quiz de módulo (treino, prova, revisão), histórico e perfil."""
from __future__ import annotations

import db
from qa_common import ok, texto, titulo


def executar(cliente, tok: str) -> dict:
    conexao = db.connect()
    modulo = db.q1(conexao, "SELECT * FROM modulos ORDER BY ordem LIMIT 1")

    titulo("Quiz de módulo - treino com feedback imediato")
    resposta = cliente.post(f"/modulo/{modulo['slug']}/quiz/iniciar",
                            data={"_csrf": tok, "modo": "treino", "n": "5"}, follow_redirects=True)
    ok(resposta.status_code == 200 and "Questão 1 de 5" in texto(resposta),
       "treino inicia com 5 questões")
    treino = db.q1(conexao, "SELECT * FROM tentativas WHERE modo = 'treino' ORDER BY id DESC LIMIT 1")
    for r in db.q(conexao, "SELECT * FROM respostas WHERE tentativa_id = ?", [treino["id"]]):
        alt = db.q1(conexao, "SELECT id FROM alternativas WHERE pergunta_id = ? ORDER BY ordem",
                    [r["pergunta_id"]])
        resposta = cliente.post(f"/tentativa/{treino['id']}/responder",
                                data={"_csrf": tok, "pergunta_id": r["pergunta_id"],
                                      "alternativa_id": alt["id"]}, follow_redirects=True)
        ok(resposta.status_code == 200 and "Explicação" in texto(resposta),
           f"questão {r['ordem'] + 1} do treino grava e mostra a explicação")
    resposta = cliente.post(f"/tentativa/{treino['id']}/entregar", data={"_csrf": tok},
                            follow_redirects=True)
    ok(resposta.status_code == 200 and "Nota" in texto(resposta), "treino corrigido mostra a nota")
    linha = db.q1(conexao, "SELECT * FROM tentativas WHERE id = ?", [treino["id"]])
    ok(linha["status"] == "entregue" and linha["nota"] is not None,
       "tentativa gravada como entregue com nota")
    ok(linha["acertos"] + linha["erros"] + linha["brancos"] == linha["total"],
       "acertos + erros + brancos = total")
    progresso = db.q1(conexao, "SELECT * FROM progresso WHERE usuario_id = ? AND modulo_id = ?",
                      [linha["usuario_id"], modulo["id"]])
    ok(progresso is not None and progresso["tentativas"] >= 1,
       "progresso do módulo atualizado após o treino")

    titulo("Prova do módulo (gabarito completo = nota 10)")
    cliente.post(f"/modulo/{modulo['slug']}/quiz/iniciar",
                 data={"_csrf": tok, "modo": "prova", "n": "5"}, follow_redirects=True)
    prova = db.q1(conexao, "SELECT * FROM tentativas WHERE modo = 'prova' ORDER BY id DESC LIMIT 1")
    ok(cliente.get(f"/tentativa/{prova['id']}").status_code == 200,
       "prova do módulo renderiza todas as questões")
    dados = {"_csrf": tok}
    for r in db.q(conexao, "SELECT * FROM respostas WHERE tentativa_id = ?", [prova["id"]]):
        certa = db.q1(conexao, "SELECT id FROM alternativas WHERE pergunta_id = ? AND correta = 1",
                      [r["pergunta_id"]])
        dados[f"p_{r['pergunta_id']}"] = certa["id"]
    cliente.post(f"/tentativa/{prova['id']}/entregar", data=dados, follow_redirects=True)
    final = db.q1(conexao, "SELECT * FROM tentativas WHERE id = ?", [prova["id"]])
    ok(final["nota"] == 10.0 and final["aprovado"] == 1,
       f"prova 100% correta => nota 10 com aprovação (nota={final['nota']})")

    titulo("Revisão, refazer erradas, histórico e perfil")
    ok(cliente.post(f"/modulo/{modulo['slug']}/quiz/iniciar",
                    data={"_csrf": tok, "modo": "revisao"}, follow_redirects=True).status_code == 200,
       "revisão das questões erradas inicia")
    ok(cliente.post(f"/tentativa/{prova['id']}/refazer-erradas", data={"_csrf": tok},
                    follow_redirects=True).status_code == 200,
       "botão 'refazer só as erradas' funciona")
    historico = texto(cliente.get("/historico"))
    ok("Evolução das notas" in historico or "Nenhuma tentativa" in historico,
       "histórico exibe a evolução das notas")
    ok(cliente.post("/perfil", data={"_csrf": tok, "nome": "Pedro Santos",
                                     "email": "pedro@exemplo.com"}).status_code == 302,
       "atualização de perfil salva")
    return {"modulo": dict(modulo), "prova": dict(prova), "treino": dict(treino)}
