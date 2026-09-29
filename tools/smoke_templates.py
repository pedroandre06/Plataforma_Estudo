"""Smoke test rápido: compila templates-chave e importa o app sem subir o servidor."""
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import app as appmod

alvos = ["dashboard.html", "modulo.html", "quiz_treino.html", "quiz_prova.html",
         "quiz_confirmar.html", "resultado.html", "simulados.html", "simulado_exec.html",
         "simulado_resultado.html", "simulado_novo.html", "admin_prova.html",
         "admin_perguntas.html", "login.html", "historico.html"]
env = appmod.app.jinja_env
for nome in alvos:
    src = (BASE / "templates" / nome).read_text(encoding="utf-8")
    env.parse(src)
    print("OK", nome)
print("[SMOKE] templates parse OK + app import OK")