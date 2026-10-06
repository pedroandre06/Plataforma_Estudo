"""Cenário 1a: autenticação, navegação geral e material original (PDF)."""
from __future__ import annotations

import db
from qa_common import entrar, ok, texto, titulo


def executar(cliente) -> str:
    conexao = db.connect()

    titulo("Acesso livre (sem senha)")
    ok(cliente.get("/").status_code == 200, "painel abre direto, sem login")
    ok(cliente.get("/login").status_code == 302, "rota /login antiga só redireciona")
    ok(cliente.get("/registro").status_code == 302, "rota /registro antiga só redireciona")
    tok = entrar(cliente)
    ok(tok == "livre", "modo sem senha usa token fixo")

    titulo("Navegação e conteúdo")
    ok("Painel de estudos" in texto(cliente.get("/")), "dashboard renderiza")
    ok(cliente.get("/materia/data-warehouse").status_code == 200, "página da matéria abre")
    ok(cliente.get("/simulados").status_code == 200, "lista de simulados abre")
    ok(cliente.get("/simulados/novo").status_code == 200, "formulário de simulado abre")
    ok(cliente.get("/historico").status_code == 200, "histórico abre")
    ok(cliente.get("/perfil").status_code == 200, "perfil abre")
    ok(cliente.get("/busca?q=esquema").status_code == 200, "busca por questões funciona")
    ok(cliente.get("/modulo/nao-existe").status_code == 404, "módulo inexistente devolve 404")
    for materia in db.q(conexao, "SELECT slug FROM materias"):
        ok(cliente.get(f"/materia/{materia['slug']}").status_code == 200,
           f"matéria {materia['slug']} abre")
    for modulo in db.q(conexao, "SELECT slug, nome FROM modulos"):
        pagina = cliente.get(f"/modulo/{modulo['slug']}")
        ok(pagina.status_code == 200 and "Resumo" in texto(pagina),
           f"módulo abre com resumo: {modulo['nome'][:34]}")
        ok(cliente.get(f"/modulo/{modulo['slug']}?aba=praticar").status_code == 200,
           f"aba praticar abre: {modulo['nome'][:34]}")

    titulo("Material original (PDF)")
    com_pdf = db.q1(conexao, "SELECT id FROM modulos WHERE pdf_origem IS NOT NULL LIMIT 1")
    if com_pdf:
        resposta = cliente.get(f"/material/{com_pdf['id']}")
        ok(resposta.status_code == 200 and resposta.mimetype == "application/pdf",
           "PDF do módulo é servido pelo servidor")
    return tok
