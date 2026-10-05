"""Confere o login e as páginas principais usando o banco REAL (data/platform.db).

Uso:
    .venv\\Scripts\\python.exe tools\\smoke_login.py

Diferente de tools/teste_e2e.py (que roda num banco descartável e cria dados),
este smoke usa o banco de estudos de verdade e faz somente requisições GET:
não cria, altera nem apaga nada.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

import config  # noqa: E402

import app as appmod  # noqa: E402
import db  # noqa: E402
from qa_common import entrar, ok, relatorio, texto, titulo  # noqa: E402


def main() -> int:
    appmod.app.config.update(TESTING=True)
    cliente = appmod.app.test_client()
    conexao = db.connect()

    titulo(f"Login no banco real ({config.DB_PATH})")
    ok(cliente.get("/").status_code == 302, "visitante sem sessão é mandado para o login")
    tok = entrar(cliente)
    ok(bool(tok), "login pedro.santos/trocar123 funciona (hash preservado) e gera token CSRF")
    painel = cliente.get("/")
    ok(painel.status_code == 200 and "Painel de estudos" in texto(painel),
       "dashboard renderiza com os dados reais")

    titulo("Páginas principais")
    for caminho in ("/simulados", "/simulados/novo", "/historico", "/perfil", "/busca?q=esquema"):
        ok(cliente.get(caminho).status_code == 200, f"{caminho} responde 200")

    for materia in db.q(conexao, "SELECT slug FROM materias ORDER BY ordem"):
        ok(cliente.get(f"/materia/{materia['slug']}").status_code == 200,
           f"matéria abre: {materia['slug']}")
    for modulo in db.q(conexao, "SELECT id, slug, nome FROM modulos ORDER BY ordem"):
        pagina = cliente.get(f"/modulo/{modulo['slug']}")
        ok(pagina.status_code == 200 and "Resumo" in texto(pagina),
           f"módulo abre com resumo: {modulo['nome'][:34]}")
        ok(cliente.get(f"/modulo/{modulo['slug']}/flashcards").status_code == 200,
           f"flashcards abrem: {modulo['nome'][:34]}")

    titulo("Material original (PDF)")
    com_pdf = db.q(conexao, "SELECT id, nome, pdf_origem FROM modulos WHERE pdf_origem IS NOT NULL ORDER BY ordem")
    ok(bool(com_pdf), f"{len(com_pdf)} módulos com PDF mapeado")
    for modulo in com_pdf:
        ok(os.path.exists(modulo["pdf_origem"]),
           f"PDF existe no disco: {os.path.basename(modulo['pdf_origem'])[:12]}")
        resposta = cliente.get(f"/material/{modulo['id']}")
        ok(resposta.status_code == 200 and resposta.mimetype == "application/pdf",
           f"PDF servido: {modulo['nome'][:34]}")
    sem_pdf = db.q1(conexao, "SELECT COUNT(*) AS n FROM modulos WHERE pdf_origem IS NULL OR pdf_origem = ''")
    ok(sem_pdf["n"] == 0, "nenhum módulo ficou sem material original")

    titulo("Área do administrador")
    for caminho in ("/admin", "/admin/perguntas", "/admin/pergunta/nova", "/admin/importar",
                    "/admin/exportar", "/admin/prova/nova"):
        ok(cliente.get(caminho).status_code == 200, f"{caminho} responde 200 para o admin")

    titulo("Estado do banco")
    stats = db.q1(conexao, """SELECT (SELECT COUNT(*) FROM materias) AS materias,
                                     (SELECT COUNT(*) FROM modulos) AS modulos,
                                     (SELECT COUNT(*) FROM perguntas WHERE ativo = 1) AS perguntas,
                                     (SELECT COUNT(*) FROM simulados) AS simulados""")
    ok(stats["perguntas"] > 0, f"banco tem conteúdo ({stats['perguntas']} questões ativas, "
                              f"{stats['modulos']} módulos, {stats['materias']} matérias, "
                              f"{stats['simulados']} simulados)")
    return relatorio()


if __name__ == "__main__":
    raise SystemExit(main())
