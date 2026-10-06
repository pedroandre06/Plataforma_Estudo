"""Helpers compartilhados dos testes de QA (modo sem senha)."""
from __future__ import annotations

FALHAS: list[str] = []
PASSOS: list[str] = []


def ok(condicao: bool, descricao: str) -> bool:
    PASSOS.append(("OK    " if condicao else "FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)
    return bool(condicao)


def titulo(texto: str) -> None:
    PASSOS.append(f"\n== {texto} ==")


def token(_cliente) -> str:
    # Modo sem senha: sem CSRF de sessão; formulários usam token fixo "livre".
    return "livre"


def texto(resposta) -> str:
    return resposta.get_data(as_text=True)


def entrar(cliente, usuario="aluno", senha=""):  # noqa: ARG001
    # Modo sem senha: só visita o painel (login redireciona para lá).
    cliente.get("/", follow_redirects=True)
    return token(cliente)


def relatorio() -> int:
    print("\n".join(PASSOS))
    print("\n" + "=" * 66)
    if FALHAS:
        print(f"[FALHOU] {len(FALHAS)} verificação(ões):")
        for f in FALHAS:
            print("  -", f)
        return 1
    print(f"[OK] todas as {len([p for p in PASSOS if p.startswith('OK')])} verificações passaram")
    return 0
