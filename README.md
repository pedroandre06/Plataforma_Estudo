# Plataforma de Estudos — Pós em Engenharia de Dados

Aplicação web em Flask para estudar o material do curso: resumo dos módulos, PDF original,
flashcards, quiz de treino com feedback imediato, provas por módulo, simulados por matéria,
simulado geral, simulado personalizado, simulado de reforço (gerado a partir dos seus erros)
e prova oficial com questões fixas.

Tudo roda localmente, em SQLite, sem dependências externas além do Flask.

---

## 1. Requisitos

- Windows (os comandos abaixo são de `cmd.exe`), Python 3.11+.
- Ambiente virtual já criado na pasta `.venv` (se não existir, veja “Criando do zero”).

Dependências (`requirements.txt`): `flask>=3.0`, `pypdf>=5.0`
(`pypdf` só é usado para importar/extrair o texto dos PDFs das disciplinas).

## 2. Rodar a plataforma

```bat
.venv\Scripts\python.exe app.py
```

Abra <http://127.0.0.1:5000> e entre com o usuário administrador criado pelo seed:

| usuário       | senha |
| ------------- | ----- |
| `pedro.santos`| `1234`|

Outras portas/hosts (opcional): `set PORT=8080` e/ou `set HOST=0.0.0.0` antes de rodar.

## 3. Preparar/atualizar os dados

```bat
.venv\Scripts\python.exe seed_data.py            :: cria admin + importa conteúdo (idempotente)
.venv\Scripts\python.exe seed_data.py --reset    :: limpa conteúdo, tentativas e simulados e reimporta
```

O seed lê `data/content/**/*.json` (198 questões em 10 módulos / 3 matérias) e cria os
simulados padrão (um por matéria + o geral). Rodar de novo **não duplica** questões: as que
já existem no módulo (mesmo enunciado) são puladas. O `--reset` apaga o conteúdo e o seu
histórico de estudo (tentativas/respostas/progresso/simulados), mas **preserva os usuários**.

Para reconhecer/reimportar os PDFs das disciplinas:

```bat
.venv\Scripts\python.exe tools\extract_pdfs.py   :: gera data/materiais/*.txt + manifest.json
```

O extrator procura os PDFs em **todas** as pastas prováveis do material (`OneDrive\Pós dados`
e `Documents\Pós dados`) e, quando o mesmo arquivo existe nas duas, usa a cópia mais recente.
Para apontar para outra pasta: `set DOCS_DIR=D:\caminho\da\pasta`. O nome do PDF de cada
módulo fica em `pdf_origem` (`data/content/<materia>/<modulo>-00.json`); o `seed_data.py`
copia esse caminho para o banco, e a aba **Material original (PDF)** mostra o arquivo. Os PDFs
originais **não são copiados nem modificados** — a plataforma lê o arquivo direto do disco.

## 4. Testes e verificações

| comando | o que valida |
| ------- | ------------ |
| `.venv\Scripts\python.exe tools\teste_e2e.py` | 100 verificações de ponta a ponta (login, CSRF, quiz, simulados, provas, admin, permissões) |
| `.venv\Scripts\python.exe tools\smoke_login.py` | login e páginas principais contra o **banco real** (só GET, não altera nada) |
| `.venv\Scripts\python.exe tools\smoke_servidor.py` | sobe o `app.py` de verdade, faz requisições HTTP e encerra o servidor |
| `.venv\Scripts\python.exe tools\smoke_templates.py` | compila todos os templates-chave do Jinja |
| `.venv\Scripts\python.exe tools\validate_content.py` | valida a estrutura das questões em `data/content` |
| `.venv\Scripts\python.exe tools\inspecionar_db.py` | contagens e integridade do banco (`PRAGMA foreign_key_check`) |

> Os testes E2E usam um banco descartável `data/qa_e2e.db`, recriado a cada execução —
> **seus dados de estudo em `data/platform.db` não são alterados**. Pode apagar o
> `data/qa_e2e.db` a qualquer momento.

## 5. Estrutura do projeto

```
app.py                  cria o app Flask, registra blueprints e configs
config.py               caminhos (banco, conteúdo, materiais), segurança, regras padrão
db.py                   acesso ao SQLite + migrações automáticas de schema
schema.sql              DDL completo (tabelas, checks, índices)
comum.py                login_required/admin_required, CSRF, helpers de data/hora
auth.py                 /login /registro /logout e páginas de erro
rotas_catalogo.py       painel (dashboard) e página de matéria
rotas_modulo.py         módulo (resumo, praticar), anotações, PDF original
rotas_quiz.py           quiz de módulo: treino (feedback), prova e revisão
rotas_resultado.py      confirmação, resultado, refazer erradas, abandonar
rotas_simulados.py      lista de simulados, iniciar e simulado de reforço
rotas_simulados_novo.py criação de simulado personalizado
rotas_simulado_exec.py  execução do simulado, auto-save (API) e entrega
rotas_admin*.py         painel admin, CRUD de questões, importar/exportar, provas oficiais
rotas_extra.py          perfil, histórico, flashcards, busca
motor.py                sorteio de questões e criação de tentativas
correcao.py             correção, nota, análise por módulo
sessao_tentativa.py     carregar/responder/entregar tentativas em andamento
seed_data.py            admin + conteúdo + simulados padrão
seed_conteudo.py        importação de data/content para o banco
tools/                  testes, smoke tests e utilitários
templates/ static/      interface (Jinja + CSS/JS sem dependências)
data/                   banco, conteúdo (JSON) e textos dos PDFs
```

## 6. Segurança implementada

- Senhas com hash (`werkzeug.security`), mínimo de 4 caracteres, bloqueio após 5 tentativas
  por 2 minutos.
- Token CSRF em todo POST/PUT/DELETE do site (exceto `/api/...`, que é JSON e valida a
  sessão); `login`/`registro` isentos por serem o ponto de entrada.
- Isolamento por usuário: tentativas, respostas, anotações e histórico são filtrados por
  `usuario_id`; rotas `/admin` exigem papel `admin`; tentativa de outro usuário devolve 403.
- `SECRET_KEY` persistida em `data/.secret_key`; cookies `HttpOnly` e `SameSite=Lax`.

## 7. Migrações de schema (bancos antigos)

`db.init_db()` (usado pelo `app.py`, pelo seed e pelos testes) aplica automaticamente as
migrações necessárias em bancos já existentes, preservando os dados:

- `tentativas.modo` passou a aceitar `'reforco'` (simulado de reforço);
- correção de `respostas.tentativa_id`, que em versões antigas podia ficar apontando para a
  tabela temporária usada na migração.

A reconstrução de tabelas segue o procedimento recomendado pelo SQLite (criar a nova tabela,
copiar as linhas, remover a antiga e renomear) com `PRAGMA foreign_keys=OFF` e
`PRAGMA legacy_alter_table=ON`, finalizando com `PRAGMA foreign_key_check`.

### Zerar tudo e começar de novo

```bat
.venv\Scripts\python.exe seed_data.py --reset    :: apaga conteúdo, tentativas e simulados (mantém usuários)
```

Ou, para zerar de fato (e recriar o admin):

```bat
del data\platform.db
.venv\Scripts\python.exe seed_data.py
```

## 8. Pontos conhecidos

- **Flashcards**: a tela (`/modulo/<slug>/flashcards`) e a tabela existem e funcionam, mas
  nenhuma fonte popula `flashcards` ainda — por isso a aba só aparece quando houver cartões
  para o módulo. Para incluir cartões, insira em `flashcards (modulo_id, frente, verso, ordem)`.
- **Servidor de desenvolvimento**: o `app.py` usa `debug=True` (recarrega ao salvar), adequado
  para uso local. Se um dia precisar expor na rede, ajuste o `HOST`/`PORT` e considere um
  servidor WSGI de produção.

## 9. Criando do zero (máquina nova)

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe seed_data.py
.venv\Scripts\python.exe app.py
```
