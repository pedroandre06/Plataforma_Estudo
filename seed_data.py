"""Popula o banco: conteúdo, usuário administrador e simulados padrão.

Uso:
    .venv\\Scripts\\python.exe seed_data.py            (idempotente)
    .venv\\Scripts\\python.exe seed_data.py --reset    (apaga conteúdo e recarrega)
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import db  # noqa: E402
import seed_conteudo  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

ADMIN_USUARIO = "pedro.santos"
ADMIN_SENHA_PADRAO = "trocar123"
ADMIN_NOME = "Pedro Santos"


def criar_admin(conn) -> None:
    senha = (os.environ.get("ADMIN_SENHA") or "").strip() or ADMIN_SENHA_PADRAO
    existente = db.q1(conn, "SELECT id, papel FROM usuarios WHERE lower(usuario) = lower(?)",
                      [ADMIN_USUARIO])
    if existente:
        if existente["papel"] != "admin":
            db.run(conn, "UPDATE usuarios SET papel = 'admin' WHERE id = ?", [existente["id"]])
        print(f"[seed] usuário admin já existe: {ADMIN_USUARIO}")
        return
    db.run(conn, """INSERT INTO usuarios (usuario, nome, senha_hash, papel) VALUES (?, ?, ?, 'admin')""",
           [ADMIN_USUARIO, ADMIN_NOME, generate_password_hash(senha)])
    if senha == ADMIN_SENHA_PADRAO:
        print(f"[seed] admin criado -> usuário: {ADMIN_USUARIO} | senha padrão '{senha}' "
              f"(TROQUE com: perfil ou ADMIN_SENHA=nova seed_data.py)")
    else:
        print(f"[seed] admin criado -> usuário: {ADMIN_USUARIO} (senha via ADMIN_SENHA)")


def simulados_padrao(conn) -> None:
    materias = db.q(conn, """
        SELECT mt.id, mt.nome, COUNT(p.id) AS n
        FROM materias mt
        JOIN modulos m ON m.materia_id = mt.id
        JOIN perguntas p ON p.modulo_id = m.id AND p.ativo = 1
        GROUP BY mt.id ORDER BY mt.ordem
    """)
    if db.q1(conn, "SELECT 1 FROM simulados WHERE tipo IN ('materia','geral') LIMIT 1"):
        print("[seed] simulados por matéria/geral já existem (nada a fazer)")
    else:
        for m in materias:
            n = min(20, m["n"])
            sid = db.run(conn, """INSERT INTO simulados (nome, tipo, descricao, n_questoes, tempo_min,
                            nota_corte, max_tentativas, embaralhar, mostrar_gabarito, publico)
                            VALUES (?, 'materia', ?, ?, 40, 6.0, 0, 1, 'fim', 1)""",
                         [f"Simulado - {m['nome']}",
                          f"{n} questões sorteadas de todos os módulos da matéria.", n])
            db.run(conn, "INSERT INTO simulado_materias (simulado_id, materia_id) VALUES (?,?)", [sid, m["id"]])
            print(f"[seed] simulado por matéria: {m['nome']} ({n} questões)")
        total = db.q1(conn, "SELECT COUNT(*) AS n FROM perguntas WHERE ativo = 1")["n"]
        n_geral = min(30, total)
        sid = db.run(conn, """INSERT INTO simulados (nome, tipo, descricao, n_questoes, tempo_min, nota_corte,
                        max_tentativas, embaralhar, mostrar_gabarito, publico)
                        VALUES ('Simulado geral (prova final)', 'geral',
                        'Questões de todas as matérias, como uma prova final.', ?, 60, 6.0, 0, 1, 'fim', 1)""",
                     [n_geral])
        for m in materias:
            db.run(conn, "INSERT OR IGNORE INTO simulado_materias (simulado_id, materia_id) VALUES (?,?)",
                   [sid, m["id"]])
        print(f"[seed] simulado geral criado ({n_geral} questões)")
    prova_oficial_padrao(conn, materias)


def prova_oficial_padrao(conn, materias) -> None:
    """Prova oficial padrão: 10 questões fixas por matéria (30 total), 90 min, 1 tentativa.

    Idempotente: só cria se ainda não existir nenhuma prova oficial.
    """
    if db.q1(conn, "SELECT 1 FROM simulados WHERE tipo = 'oficial' LIMIT 1"):
        print("[seed] prova oficial já existe (nada a fazer)")
        return
    admin = db.q1(conn, "SELECT id FROM usuarios WHERE lower(usuario) = lower(?)", [ADMIN_USUARIO])
    criado_por = admin["id"] if admin else None
    sid = db.run(conn, """INSERT INTO simulados (nome, tipo, descricao, criado_por, n_questoes,
                    tempo_min, nota_corte, max_tentativas, embaralhar, mostrar_gabarito, publico)
                    VALUES ('Prova oficial (padrão)', 'oficial',
                    'Avaliação final com 10 questões fixas de cada matéria.', ?, 30,
                    90, 6.0, 1, 0, 'fim', 1)""", [criado_por])
    ordem = 0
    total_fixas = 0
    for m in materias:
        fixas = db.q(conn, """SELECT p.id FROM perguntas p JOIN modulos mo ON mo.id = p.modulo_id
                              WHERE mo.materia_id = ? AND p.ativo = 1 ORDER BY p.id LIMIT 10""",
                     [m["id"]])
        for f in fixas:
            db.run(conn, """INSERT OR IGNORE INTO simulado_questoes (simulado_id, pergunta_id, ordem)
                            VALUES (?,?,?)""", [sid, f["id"], ordem])
            ordem += 1
            total_fixas += 1
        db.run(conn, "INSERT OR IGNORE INTO simulado_materias (simulado_id, materia_id) VALUES (?,?)",
               [sid, m["id"]])
    print(f"[seed] prova oficial padrão criada ({total_fixas} questões fixas)")


def principal() -> int:
    parser = argparse.ArgumentParser(description="Popula o banco da plataforma de estudos")
    parser.add_argument("--reset", action="store_true", help="apaga o conteúdo antes de recarregar")
    args = parser.parse_args()
    db.init_db(verbose=False)
    with db.abrir() as conn:
        if args.reset:
            seed_conteudo.limpar(conn)
        criar_admin(conn)
        total = seed_conteudo.importar_conteudo(conn)
        simulados_padrao(conn)
        stats = db.q1(conn, """SELECT (SELECT COUNT(*) FROM materias) AS materias,
                                      (SELECT COUNT(*) FROM modulos) AS modulos,
                                      (SELECT COUNT(*) FROM perguntas WHERE ativo = 1) AS perguntas,
                                      (SELECT COUNT(*) FROM simulados) AS simulados,
                                      (SELECT COUNT(*) FROM usuarios) AS usuarios""")
    print(f"\n[seed] matérias: {stats['materias']} | módulos: {stats['modulos']} | "
          f"questões: {stats['perguntas']} | simulados: {stats['simulados']} | "
          f"usuários: {stats['usuarios']} | novas questões: {total}")
    print(f"[seed] acesso -> usuário '{ADMIN_USUARIO}' (senha definida via ADMIN_SENHA ou padrão)")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
