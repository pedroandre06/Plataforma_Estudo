"""Troca a senha de um usuário (uso local do administrador).

Uso:
    .venv\\Scripts\\python.exe tools\\trocar_senha.py pedro.santos
    # digite a nova senha quando pedido (mínimo 8 caracteres)

Ou via variável de ambiente (evita digitar no terminal):
    set NOVA_SENHA=minha-senha-forte && .venv\\Scripts\\python.exe tools\\trocar_senha.py pedro.santos
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import config  # noqa: E402
import db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def principal() -> int:
    if len(sys.argv) < 2:
        print("Uso: trocar_senha.py <usuario>")
        return 1
    usuario = sys.argv[1].strip()
    nova = (os.environ.get("NOVA_SENHA") or "").strip()
    if not nova:
        nova = getpass.getpass(f"Nova senha para '{usuario}': ").strip()
        confirma = getpass.getpass("Confirme a nova senha: ").strip()
        if nova != confirma:
            print("[erro] as senhas não conferem.")
            return 1
    if len(nova) < config.MIN_SENHA:
        print(f"[erro] a senha deve ter ao menos {config.MIN_SENHA} caracteres.")
        return 1
    db.init_db(verbose=False)
    with db.abrir() as conn:
        linha = db.q1(conn, "SELECT id FROM usuarios WHERE lower(usuario) = lower(?)", [usuario])
        if not linha:
            print(f"[erro] usuário '{usuario}' não encontrado.")
            return 1
        db.run(conn, "UPDATE usuarios SET senha_hash = ?, tentativas_falhas = 0, bloqueado_ate = NULL WHERE id = ?",
               [generate_password_hash(nova), linha["id"]])
    print(f"[ok] senha de '{usuario}' atualizada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
