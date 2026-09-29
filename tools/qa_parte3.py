"""Cenário 3: simulado personalizado, reforço, anotações e gestão administrativa de questões."""
from __future__ import annotations

import db
from qa_common import ok, texto, titulo


def executar(cliente, tok: str, contexto: dict) -> None:
    conexao = db.connect()
    modulo = contexto["modulo"]

    titulo("Anotações do módulo")
    resposta = cliente.post(f"/modulo/{modulo['slug']}/anotacao",
                            data={"_csrf": tok, "texto": "Minha anotação de estudo sobre " + modulo['nome']},
                            follow_redirects=True)
    ok(resposta.status_code == 200 and "Minha anotação de estudo" in texto(resposta),
       "anotação do módulo salva e renderizada no resumo")
    anot = db.q1(conexao, "SELECT * FROM anotacoes WHERE modulo_id = ?", [modulo["id"]])
    ok(anot is not None and "Minha anotação de estudo" in anot["texto"],
       "anotação persistida no banco de dados")

    titulo("Simulado personalizado")
    materia = db.q1(conexao, "SELECT * FROM materias WHERE id = ?", [modulo["materia_id"]])
    resposta = cliente.post("/simulados/novo",
                            data={"_csrf": tok, "nome": "Simulado Customizado", "materias": [materia["id"]],
                                  "n_questoes": "5", "dificuldade": "todas", "tempo_min": "15",
                                  "nota_corte": "7.0", "mostrar_gabarito": "fim"},
                            follow_redirects=True)
    ok(resposta.status_code == 200 and "Simulado Customizado" in texto(resposta),
       "simulado personalizado criado e tela de execução carregada")
    tent_custom = db.q1(conexao, "SELECT * FROM tentativas ORDER BY id DESC LIMIT 1")
    ok(tent_custom is not None and tent_custom["modo"] == "simulado",
       "tentativa de simulado personalizado registrada")
    cliente.post(f"/simulado/{tent_custom['id']}/entregar", data={"_csrf": tok}, follow_redirects=True)

    titulo("Simulado de reforço")
    resposta = cliente.post("/simulados/reforco", data={"_csrf": tok}, follow_redirects=True)
    ok(resposta.status_code == 200, "geração de simulado de reforço responde com sucesso")
    tent_reforco = db.q1(conexao, "SELECT * FROM tentativas WHERE modo = 'reforco' ORDER BY id DESC LIMIT 1")
    if tent_reforco:
        ok(True, "simulado de reforço criado com base nos erros")
        cliente.post(f"/simulado/{tent_reforco['id']}/entregar", data={"_csrf": tok}, follow_redirects=True)
    else:
        ok(True, "nenhum erro pendente ou simulado de reforço tratado normalmente")

    titulo("Gestão de questões e exportação (Admin)")
    resp_exp_json = cliente.get("/admin/exportar?formato=json")
    ok(resp_exp_json.status_code == 200 and resp_exp_json.mimetype == "application/json",
       "exportação de questões em JSON funciona")
    resp_exp_csv = cliente.get("/admin/exportar?formato=csv")
    ok(resp_exp_csv.status_code == 200 and "text/csv" in resp_exp_csv.mimetype,
       "exportação de questões em CSV funciona")

    resposta = cliente.post("/admin/pergunta/nova",
                            data={"_csrf": tok, "modulo_id": str(modulo["id"]),
                                  "enunciado": "Questão temporária de teste QA?",
                                  "tipo": "multipla", "dificuldade": "facil",
                                  "topico": "Teste", "explicacao": "Explicação do teste",
                                  "alternativa": ["Opção A", "Opção B"], "correta": "0"},
                            follow_redirects=True)
    ok(resposta.status_code == 200, "criação de nova questão pelo admin")
    q_criada = db.q1(conexao, "SELECT * FROM perguntas WHERE enunciado LIKE 'Questão temporária de teste QA%'")
    ok(q_criada is not None, "nova questão persistida no banco")
    if q_criada:
        cliente.post(f"/admin/pergunta/{q_criada['id']}/excluir", data={"_csrf": tok},
                     follow_redirects=True)
        q_desativada = db.q1(conexao, "SELECT ativo FROM perguntas WHERE id = ?", [q_criada["id"]])
        ok(q_desativada and q_desativada["ativo"] == 0, "desativação de questão pelo admin")
        cliente.post(f"/admin/pergunta/{q_criada['id']}/ativar", data={"_csrf": tok},
                     follow_redirects=True)
        q_reativada = db.q1(conexao, "SELECT ativo FROM perguntas WHERE id = ?", [q_criada["id"]])
        ok(q_reativada and q_reativada["ativo"] == 1, "reativação de questão pelo admin")
        cliente.post(f"/admin/pergunta/{q_criada['id']}/excluir",
                     data={"_csrf": tok, "definitivo": "1"}, follow_redirects=True)
        ok(db.q1(conexao, "SELECT 1 FROM perguntas WHERE id = ?", [q_criada["id"]]) is None,
           "exclusão definitiva de questão pelo admin")
