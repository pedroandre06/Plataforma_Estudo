"""Smoke test do servidor real: sobe `python app.py` e faz requisições HTTP.

Uso:
    .venv\\Scripts\\python.exe tools\\smoke_servidor.py

Confirma que a aplicação sobe de verdade (não só o test_client do Flask),
que o login responde 200 e que páginas protegidas redirecionam visitantes.
O processo do servidor é encerrado no final (inclusive o reloader do Flask).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PORTA = 5080
URL = f"http://127.0.0.1:{PORTA}"


class SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Impede o urllib de seguir o 302 (para conferir os redirecionamentos)."""

    def redirect_request(self, *args, **kwargs):  # noqa: D102
        return None


def buscar(caminho: str, seguir: bool = True) -> tuple[int, str, str]:
    manipuladores = [] if seguir else [SemRedirecionar()]
    abridor = urllib.request.build_opener(*manipuladores)
    try:
        with abridor.open(URL + caminho, timeout=10) as resposta:
            return resposta.status, resposta.headers.get("Location", ""), resposta.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        local = erro.headers.get("Location", "") if erro.headers else ""
        return erro.code, local, ""
    except urllib.error.URLError:
        # conexao recusada: o servidor ainda esta subindo (aguardar_servidor vai tentar de novo)
        return 0, "", ""


def aguardar_servidor(limite_seg: int = 30) -> bool:
    inicio = time.time()
    while time.time() - inicio < limite_seg:
        codigo, _, _ = buscar("/login")
        if codigo == 200:
            return True
        time.sleep(0.5)
    return False


def principal() -> int:
    log = BASE / "data" / "servidor_smoke.log"
    ambiente = {**os.environ, "PORT": str(PORTA)}
    with log.open("w", encoding="utf-8") as saida:
        processo = subprocess.Popen([sys.executable, "app.py"], cwd=str(BASE), stdout=saida,
                                   stderr=subprocess.STDOUT, env=ambiente)
    falhas = 0

    def conferir(condicao: bool, descricao: str) -> None:
        nonlocal falhas
        print(("OK   " if condicao else "FALHA"), descricao)
        falhas += 0 if condicao else 1

    try:
        if not aguardar_servidor():
            print(f"[FALHA] o servidor não respondeu em {URL} (log: {log})")
            return 1
        print(f"OK    servidor no ar (python app.py, porta {PORTA})")

        codigo, _, corpo = buscar("/login")
        conferir(codigo == 200 and "Entrar" in corpo, f"GET /login -> {codigo} com formulário")

        codigo, local, _ = buscar("/", seguir=False)
        conferir(codigo in (301, 302) and "/login" in local, f"GET / sem sessão -> {codigo} {local}")

        codigo, local, _ = buscar("/admin", seguir=False)
        conferir(codigo in (301, 302) and "/login" in local, f"GET /admin sem sessão -> {codigo} {local}")

        codigo, _, _ = buscar("/registro")
        conferir(codigo == 200, f"GET /registro -> {codigo}")

        codigo, _, _ = buscar("/rota-que-nao-existe-xyz", seguir=False)
        conferir(codigo == 404, f"GET /rota-que-nao-existe-xyz -> {codigo} (404 esperado)")

        codigo, _, corpo = buscar("/healthz")
        conferir(codigo == 200 and '"status":"ok"' in corpo.replace(" ", ""),
                 f"GET /healthz -> {codigo} {corpo[:80]}")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(processo.pid)], capture_output=True, text=True)
        processo.wait(timeout=15)
        print(f"[smoke] servidor encerrado (log: {log.name})")

    if falhas:
        print(f"\n[FALHOU] {falhas} verificação(ões) do servidor")
        return 1
    print("\n[OK] servidor sobe, protege as rotas e responde ao público")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
