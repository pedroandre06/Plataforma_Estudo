"""Reproduz o fluxo do navegador: login -> praticar -> comecar treino.

Sobe `python app.py` como subprocesso (mesmo padrao de tools/smoke_servidor.py)
e usa cookies reais (urllib + http.cookiejar) para achar onde a sessao se perde.
"""
from __future__ import annotations

import http.cookiejar
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PORTA = 5061
URL = f"http://127.0.0.1:{PORTA}"
SLUG = "fundamentos-dw"


class SemSeguir(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D102
        return None


def main() -> int:
    log = BASE_DIR / "tmp_server.log"
    ambiente = {**os.environ, "PORT": str(PORTA)}
    with log.open("w", encoding="utf-8") as saida:
        processo = subprocess.Popen([sys.executable, "app.py"], cwd=str(BASE_DIR),
                                    stdout=saida, stderr=subprocess.STDOUT, env=ambiente)
    falhas = 0
    jar = http.cookiejar.CookieJar()
    navegador = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    direto = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), SemSeguir())

    def ok(cond, msg):
        nonlocal falhas
        print(("OK   " if cond else "FALHA"), msg)
        falhas += 0 if cond else 1

    def pegar(caminho):
        """GET seguindo redirects; devolve (status, url, corpo)."""
        try:
            with navegador.open(URL + caminho, timeout=10) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, URL + caminho, ""

    def postar(caminho, dados):
        """POST sem seguir redirect; devolve (status, location, corpo)."""
        corpo = urllib.parse.urlencode(dados).encode()
        try:
            with direto.open(urllib.request.Request(URL + caminho, data=corpo), timeout=10) as r:
                return r.status, r.headers.get("Location", ""), ""
        except urllib.error.HTTPError as e:
            return e.code, (e.headers or {}).get("Location", ""), ""

    try:
        for _ in range(60):
            try:
                if pegar("/login")[0] == 200:
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.5)
        else:
            print("[FALHA] servidor nao subiu (log: tmp_server.log)")
            return 1

        # 1. GET /login -> pega CSRF
        st, _, corpo = pegar("/login")
        m = re.search(r'name="_csrf" value="([0-9a-f]+)"', corpo)
        ok(st == 200 and m is not None, "GET /login tem token CSRF")
        print("     cookies apos /login:", [c.name for c in jar])

        # 2. POST /login (lembrar=1)
        st, loc, _ = postar("/login", {"usuario": "pedro.santos", "senha": "1234",
                                       "lembrar": "1", "_csrf": m.group(1)})
        ok(st == 302 and "/login" not in (loc or ""), f"POST /login -> {st} {loc}")
        print("     cookies apos login:", [c.name for c in jar],
              "| permanentes:", [(c.name, c.expires) for c in jar])

        # 3. GET /
        st, url, _ = pegar("/")
        ok(st == 200 and "/login" not in url, f"GET / -> {st} {url}")

        # 4. GET modulo aba=praticar
        st, url, corpo = pegar(f"/modulo/{SLUG}?aba=praticar")
        ok(st == 200 and "/login" not in url, f"GET modulo?aba=praticar -> {st} {url}")
        m = re.search(r'name="_csrf" value="([0-9a-f]+)"', corpo)
        ok(m is not None, "aba praticar tem token CSRF no form")

        # 5. POST quiz/iniciar (Comecar treino)
        st, loc, _ = postar(f"/modulo/{SLUG}/quiz/iniciar",
                            {"modo": "treino", "n": "10", "_csrf": m.group(1)})
        ok(st == 302 and "/tentativa/" in (loc or ""), f"POST quiz/iniciar -> {st} {loc}")
        if loc and "/login" in loc:
            print("     *** REPRODUZIDO: voltou para o login no POST ***")
            _, _, corpo = pegar(loc)
            print("     flash:", re.findall(r'flash flash-\w+">([^<]+)', corpo))

        # 6. GET tentativa (o treino abre)
        if loc and "/tentativa/" in loc:
            st, url, _ = pegar(loc.replace(URL, ""))
            ok(st == 200 and "/login" not in url, f"GET {loc} -> {st} {url}")

        # 7. Pagina de novo depois de 2s (sessao continua?)
        time.sleep(2)
        st, url, _ = pegar("/")
        ok(st == 200 and "/login" not in url, f"GET / de novo -> {st} {url}")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(processo.pid)],
                       capture_output=True, text=True)
        processo.wait(timeout=15)
        print("[repro] servidor encerrado")

    print(f"\n[{'FALHOU' if falhas else 'OK'}] {falhas} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
