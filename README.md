# Plataforma de Estudos — Pós em Engenharia de Dados

Aplicação web em Flask para estudar o material do curso: resumo dos módulos, PDF original,
flashcards, quiz de treino com feedback imediato, provas por módulo, simulados por matéria,
simulado geral, simulado personalizado, simulado de reforço (gerado a partir dos seus erros)
e prova oficial com questões fixas.

Tudo roda localmente com SQLite (nenhum serviço externo), mas a camada de banco também fala
**PostgreSQL** — é o que permite o deploy na Vercel, onde o disco é somente leitura.
Veja a seção 8.

---

## 1. Requisitos

- Windows (os comandos abaixo são de `cmd.exe`), Python 3.11+.
- Ambiente virtual já criado na pasta `.venv` (se não existir, veja “Criando do zero”).

Dependências (`requirements.txt`): `flask>=3.0`, `pypdf>=5.0`, `psycopg[binary]>=3.2`.
(`pypdf` só é usado para importar/extrair o texto dos PDFs das disciplinas; `psycopg` só é
acionado quando `DATABASE_URL` aponta para um PostgreSQL — sem essa variável nada dele é usado.)

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

O seed lê `data/content/**/*.json` (219 questões em 11 módulos / 3 matérias) e cria os
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
| `.venv\Scripts\python.exe tools\teste_e2e.py` | 102 verificações de ponta a ponta (login, CSRF, quiz, simulados, provas, admin, permissões) |
| `.venv\Scripts\python.exe tools\teste_correcao_login.py` | 8 verificações da correção de login/CSRF: sessão expirada redireciona para o login (não 400), token errado continua bloqueado, chave de sessão estável sem `SECRET_KEY` e diagnóstico no `/healthz` |
| `.venv\Scripts\python.exe tools\smoke_login.py` | login e páginas principais contra o **banco real** (só GET, não altera nada) |
| `.venv\Scripts\python.exe tools\smoke_servidor.py` | sobe o `app.py` de verdade, faz requisições HTTP e encerra o servidor |
| `.venv\Scripts\python.exe tools\smoke_templates.py` | compila todos os templates-chave do Jinja |
| `.venv\Scripts\python.exe tools\validate_content.py` | valida a estrutura das questões em `data/content` |
| `.venv\Scripts\python.exe tools\inspecionar_db.py` | contagens, índices e integridade do banco — funciona com SQLite (`PRAGMA`) e com Postgres (`information_schema`) |
| `.venv\Scripts\python.exe tools\verificar_dialeto.py` | varredura estática: SQL portável nos `.py`, igualdade entre `schema.sql` e `schema_pg.sql` e a tradução `SQLite → Postgres` comando a comando |
| `.venv\Scripts\python.exe tools\migrar_para_postgres.py` | copia o `data/platform.db` para o Postgres, preservando os `id` e conferindo as contagens (seção 8) |

> Os testes E2E usam um banco descartável, recriado a cada execução —
> **seus dados de estudo em `data/platform.db` não são alterados**. No SQLite é o arquivo
> `data/qa_e2e.db` (pode apagar quando quiser); no Postgres é o banco apontado por
> `DATABASE_URL`, e a ferramenta **recusa** qualquer destino que não tenha `qa` no nome,
> exatamente para não cair no banco de produção:
> `set DATABASE_URL=postgresql://postgres:postgres@localhost:55432/qa_plataforma` antes de rodar.

## 5. Estrutura do projeto

```
app.py                  cria o app Flask, registra blueprints e configs
config.py               caminhos (banco, conteúdo, materiais), segurança, regras padrão
db.py                   acesso ao banco nos dois motores + migrações automáticas de schema
schema.sql              DDL no dialeto SQLite (tabelas, checks, índices)
schema_pg.sql           o mesmo DDL em dialeto PostgreSQL (usado quando DATABASE_URL existe)
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
- `SECRET_KEY` persistida em `data/.secret_key`; na Vercel ela vem da variável `SECRET_KEY`
  (o disco é somente leitura, então gravar o arquivo não é opção) — cookies `HttpOnly` e
  `SameSite=Lax`.

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

## 8. PostgreSQL e deploy na Vercel

A camada de banco decide o motor pela variável `DATABASE_URL`:

| `DATABASE_URL` | motor usado | quando |
| --- | --- | --- |
| ausente | SQLite em `data/platform.db` | desenvolvimento local (padrão) |
| `postgres://…` / `postgresql://…` | PostgreSQL | produção (Neon, Supabase, Render…) |

O SQL continua escrito **sempre no dialeto do SQLite** (`?`, `INSERT OR IGNORE`,
`cursor.lastrowid`) e o `db.py` traduz na hora para o Postgres (`%s`,
`ON CONFLICT DO NOTHING`, `RETURNING id`), consultando uma vez as tabelas que têm coluna
`id`. Assim as rotas não levam `if/else` de banco. As regras que essa camada exige — e que
`tools/verificar_dialeto.py` confere em todas as strings SQL do projeto — são:

- `LIKE` sempre com `lower()` dos dois lados (no SQLite o `LIKE` ignora maiúsculas por
  padrão; no Postgres **não** ignora, e a busca deixaria de achar “Teste”);
- `COALESCE` em vez de `IFNULL`, `EXTRACT(EPOCH FROM …)` em vez de `julianday`, sem
  `strftime`, sem `PRAGMA`, sem `CAST(… AS REAL)` (tipo que só existe no SQLite);
- nenhum `%` literal fora de `LIKE` (para o psycopg, `%` é marcador de parâmetro).

### Variáveis de ambiente

| variável | obrigatória na Vercel | o que faz |
| --- | --- | --- |
| `DATABASE_URL` (também aceita `POSTGRES_URL` / `DATABASE_POSTGRES`) | **sim** | aponta o Postgres. Sem ela o app tenta abrir o SQLite e, como o disco da Vercel é somente leitura, tudo quebra (a tela de boot avisa disso). O Postgres do Marketplace da Vercel (Neon) já injeta essas variáveis sozinho |
| `SECRET_KEY` | **sim** | assina o cookie de sessão; sem ela cada deployment derrubava todo mundo do login |
| `INIT_DB_ON_STARTUP` | não (padrão `1`) | cria/completa as tabelas no primeiro acesso |
| `SEED_ON_STARTUP` | não (padrão `1`) | no banco vazio, cadastra o admin, o conteúdo das disciplinas e os simulados no primeiro acesso (deixa o deploy pronto sem passo manual) |

No boot o app imprime `config.resumo()` (motor e caminho) e `/healthz` responde
`{"status": "ok", "motor": "postgres", "banco": "…", "consulta": 1, "sessao": "arquivo"}` — o `consulta` é o
resultado de um `SELECT 1` real, útil para o monitoramento da Vercel, e `sessao` diz de
onde veio a chave que assina os cookies (`ambiente`, `arquivo`, `dsn` ou `efemera`).

### Erro de CSRF / "pede login toda hora"

Os dois sintomas têm a mesma causa: **o cookie de sessão não sobrevive entre
requisições**, então o token CSRF do form não bate com o da sessão (400) e o usuário
é deslogado em seguida. Causas e solução:

| causa | como aparece | solução |
| --- | --- | --- |
| `SECRET_KEY` ausente na Vercel (disco somente leitura, `data/.secret_key` excluído do deploy) | cada instância/lambda assina os cookies com uma chave diferente: logout aleatório + CSRF 400 | defina `SECRET_KEY` nas Environment Variables (ou deixe o app derivá-la do `DATABASE_URL`, fallback automático) e faça Redeploy |
| `DATABASE_URL` ausente | cada cold start usa um SQLite temporário diferente: a sessão aponta para um usuário que "não existe" | defina `DATABASE_URL` (Neon/Supabase) |
| página aberta de um form antigo (botão "voltar") | 400 "Token CSRF inválido" pontual | recarregar a página; logado, o POST continua bloqueado (400); sem sessão, agora leva direto ao login |
| sessão expirada / cookie inválido | — | corrigido: o POST sem sessão redireciona para `/login` com aviso, em vez de um 400 em beco |

Confira rápido com `curl https://<seu-site>/healthz`: se `sessao` vier `efemera`, a
chave não está persistindo — é essa a origem do logout constante.

### Deploy na Vercel

1. Crie o banco (Neon/Supabase) e copie a string de conexão.
2. Settings → Environment Variables: adicione `DATABASE_URL` e `SECRET_KEY`.
3. Faça o deploy: no primeiro acesso as tabelas são criadas (a partir do `schema_pg.sql`)
   e, se o banco estiver vazio, o admin + o conteúdo + os simulados são cadastrados
   automaticamente.
4. `vercel env pull .env.local` para espelhar as variáveis no `app.py` local (o arquivo
   `data/.env.local` já está no `.gitignore` e a Vercel também lê `.env.local`).

### Erro 500 (Internal Server Error) no deploy

O site só mostra um 500 quando **o próprio banco falha na preparação**. As causas mais
comuns e como conferir:

| causa | como aparece | solução |
| --- | --- | --- |
| `DATABASE_URL` ausente | o app cai para o SQLite, mas o disco da Vercel é somente leitura e a abertura do arquivo falha | defina `DATABASE_URL` (Neon/Supabase) nas Environment Variables e faça Redeploy |
| `DATABASE_URL` apontando para o exemplo (`localhost:55432`) | erro de conexão recusada | troque pela string real do banco hospedado |
| banco novo e vazio | antigamente logava normal, mas não havia admin/conteúdo | com `SEED_ON_STARTUP=1` (padrão) tudo é criado no primeiro acesso |

Em qualquer falha de banco a aplicação agora responde com uma **página de diagnóstico**
(HTTP 503) que mostra o motor, o alvo da conexão e o erro técnico — em vez do 500 em
branco. Para uma conferência rápida, abra `/healthz`:

### Postgres local para testar (Docker)

```bat
docker run -d --name pg-plataforma -e POSTGRES_PASSWORD=*** -e POSTGRES_DB=plataforma ^
    -p 55432:5432 postgres:16-alpine

set DATABASE_URL=postgresql://postgres:postgres@localhost:55432/plataforma
.venv\Scripts\python.exe seed_data.py
.venv\Scripts\python.exe app.py
```

Para os testes E2E contra o Postgres, aponte para um banco com `qa` no nome (a ferramenta
recusa os outros) e use o botão **“Reset schema”** da interface ou rode o `tools\teste_e2e.py`:

```bat
docker exec pg-plataforma psql -U postgres -c "CREATE DATABASE qa_plataforma"
set DATABASE_URL=postgresql://postgres:postgres@localhost:55432/qa_plataforma
.venv\Scripts\python.exe tools\teste_e2e.py
```

### Levar o histórico do SQLite para o Postgres

```bat
set DATABASE_URL=postgresql://postgres:postgres@localhost:55432/plataforma
.venv\Scripts\python.exe tools\migrar_para_postgres.py            :: só simula, não grava
.venv\Scripts\python.exe tools\migrar_para_postgres.py --apply    :: grava de verdade
```

O utilitário cria as tabelas se preciso, copia na ordem das FKs, **preserva os `id`**,
realinha as sequências e confere as contagens tabela por tabela. Ele se recusa a gravar num
destino que já tenha dados — migre para um banco vazio.

## 9. Pontos conhecidos

- **Flashcards**: a tela (`/modulo/<slug>/flashcards`) e a tabela existem e funcionam, mas
  nenhuma fonte popula `flashcards` ainda — por isso a aba só aparece quando houver cartões
  para o módulo. Para incluir cartões, insira em `flashcards (modulo_id, frente, verso, ordem)`.
- **Servidor de desenvolvimento**: o `app.py` usa `debug=True` (recarrega ao salvar), adequado
  para uso local. Se um dia precisar expor na rede, ajuste o `HOST`/`PORT` e considere um
  servidor WSGI de produção.

## 10. Criando do zero (máquina nova)

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe seed_data.py
.venv\Scripts\python.exe app.py
```
