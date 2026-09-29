-- =====================================================================
--  Plataforma de Estudos - Pos em Engenharia de Dados
--  Banco: SQLite  (gerado/atualizado por db.init_db())
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------- usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario           TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome              TEXT NOT NULL,
    email             TEXT,
    senha_hash        TEXT NOT NULL,
    papel             TEXT NOT NULL DEFAULT 'aluno' CHECK (papel IN ('admin', 'aluno')),
    ativo             INTEGER NOT NULL DEFAULT 1,
    criado_em         TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    ultimo_login_em   TEXT,
    tentativas_falhas INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate     TEXT
);

-- ------------------------------------------------------------- materias
CREATE TABLE IF NOT EXISTS materias (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    slug      TEXT NOT NULL UNIQUE,
    nome      TEXT NOT NULL,
    descricao TEXT,
    cor       TEXT NOT NULL DEFAULT '#4f9cf9',
    ordem     INTEGER NOT NULL DEFAULT 0,
    ativo     INTEGER NOT NULL DEFAULT 1
);

-- -------------------------------------------------------------- modulos
CREATE TABLE IF NOT EXISTS modulos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    materia_id  INTEGER NOT NULL REFERENCES materias (id) ON DELETE CASCADE,
    slug        TEXT NOT NULL,
    nome        TEXT NOT NULL,
    descricao   TEXT,
    resumo      TEXT,
    pdf_origem  TEXT,
    texto_path  TEXT,
    ordem       INTEGER NOT NULL DEFAULT 0,
    ativo       INTEGER NOT NULL DEFAULT 1,
    UNIQUE (materia_id, slug)
);

-- ------------------------------------------------------------ perguntas
CREATE TABLE IF NOT EXISTS perguntas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo_id   INTEGER NOT NULL REFERENCES modulos (id) ON DELETE CASCADE,
    enunciado   TEXT NOT NULL,
    tipo        TEXT NOT NULL DEFAULT 'multipla' CHECK (tipo IN ('multipla', 'vf')),
    dificuldade TEXT NOT NULL DEFAULT 'medio' CHECK (dificuldade IN ('facil', 'medio', 'dificil')),
    topico      TEXT,
    explicacao  TEXT,
    referencia  TEXT,
    ativo       INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_perguntas_modulo ON perguntas (modulo_id, ativo);

-- --------------------------------------------------------- alternativas
CREATE TABLE IF NOT EXISTS alternativas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pergunta_id INTEGER NOT NULL REFERENCES perguntas (id) ON DELETE CASCADE,
    texto       TEXT NOT NULL,
    correta     INTEGER NOT NULL DEFAULT 0,
    ordem       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alternativas_pergunta ON alternativas (pergunta_id);

-- ----------------------------------------------------------- flashcards
CREATE TABLE IF NOT EXISTS flashcards (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo_id  INTEGER NOT NULL REFERENCES modulos (id) ON DELETE CASCADE,
    frente     TEXT NOT NULL,
    verso      TEXT NOT NULL,
    ordem      INTEGER NOT NULL DEFAULT 0
);

-- ------------------------------------------------------------ anotacoes
CREATE TABLE IF NOT EXISTS anotacoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    modulo_id     INTEGER NOT NULL REFERENCES modulos (id) ON DELETE CASCADE,
    texto         TEXT NOT NULL,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_anotacoes_unica ON anotacoes (usuario_id, modulo_id);

-- =====================================================================
--  Simulados, provas e desempenho
-- =====================================================================

-- ------------------------------------------------------------- simulados
CREATE TABLE IF NOT EXISTS simulados (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nome             TEXT NOT NULL,
    tipo             TEXT NOT NULL DEFAULT 'personalizado'
                     CHECK (tipo IN ('modulo', 'materia', 'geral', 'personalizado', 'reforco', 'oficial')),
    descricao        TEXT,
    criado_por       INTEGER REFERENCES usuarios (id) ON DELETE SET NULL,
    n_questoes       INTEGER NOT NULL DEFAULT 20,
    tempo_min        INTEGER NOT NULL DEFAULT 40,
    nota_corte       REAL NOT NULL DEFAULT 6.0,
    max_tentativas   INTEGER NOT NULL DEFAULT 0,          -- 0 = ilimitado
    embaralhar       INTEGER NOT NULL DEFAULT 1,
    mostrar_gabarito TEXT NOT NULL DEFAULT 'fim' CHECK (mostrar_gabarito IN ('imediato', 'fim', 'nunca')),
    dificuldade      TEXT NOT NULL DEFAULT 'todas' CHECK (dificuldade IN ('todas', 'facil', 'medio', 'dificil')),
    publico          INTEGER NOT NULL DEFAULT 1,
    ativo            INTEGER NOT NULL DEFAULT 1,
    criado_em        TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- materias que participam do sorteio (+ peso por materia)
CREATE TABLE IF NOT EXISTS simulado_materias (
    simulado_id INTEGER NOT NULL REFERENCES simulados (id) ON DELETE CASCADE,
    materia_id  INTEGER NOT NULL REFERENCES materias (id) ON DELETE CASCADE,
    peso        REAL NOT NULL DEFAULT 1,
    PRIMARY KEY (simulado_id, materia_id)
);

-- questoes fixas (prova oficial). Fica vazia em simulados sorteados.
CREATE TABLE IF NOT EXISTS simulado_questoes (
    simulado_id INTEGER NOT NULL REFERENCES simulados (id) ON DELETE CASCADE,
    pergunta_id INTEGER NOT NULL REFERENCES perguntas (id) ON DELETE CASCADE,
    ordem       INTEGER NOT NULL DEFAULT 0,
    peso        REAL NOT NULL DEFAULT 1,
    PRIMARY KEY (simulado_id, pergunta_id)
);

-- ------------------------------------------------------------ tentativas
CREATE TABLE IF NOT EXISTS tentativas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    modulo_id     INTEGER REFERENCES modulos (id) ON DELETE SET NULL,
    simulado_id   INTEGER REFERENCES simulados (id) ON DELETE SET NULL,
    modo          TEXT NOT NULL DEFAULT 'treino'
                  CHECK (modo IN ('treino', 'prova', 'revisao', 'simulado', 'reforco', 'oficial')),
    status        TEXT NOT NULL DEFAULT 'em_andamento'
                  CHECK (status IN ('em_andamento', 'entregue', 'expirada')),
    inicio_em     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    fim_em        TEXT,
    limite_em     TEXT,                                   -- inicio + tempo_min
    tempo_seg     INTEGER,
    total         INTEGER NOT NULL DEFAULT 0,
    acertos       INTEGER NOT NULL DEFAULT 0,
    erros         INTEGER NOT NULL DEFAULT 0,
    brancos       INTEGER NOT NULL DEFAULT 0,
    nota          REAL,
    nota_corte    REAL,
    aprovado      INTEGER,
    config_json   TEXT,                                   -- snapshot das regras
    questoes_json TEXT                                    -- ordem/embaralhamento das alternativas
);

CREATE INDEX IF NOT EXISTS idx_tentativas_usuario ON tentativas (usuario_id, status);
CREATE INDEX IF NOT EXISTS idx_tentativas_simulado ON tentativas (simulado_id);

-- ------------------------------------------------------------- respostas
CREATE TABLE IF NOT EXISTS respostas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tentativa_id    INTEGER NOT NULL REFERENCES tentativas (id) ON DELETE CASCADE,
    pergunta_id     INTEGER NOT NULL REFERENCES perguntas (id) ON DELETE CASCADE,
    alternativa_id  INTEGER REFERENCES alternativas (id) ON DELETE SET NULL,
    ordem           INTEGER NOT NULL DEFAULT 0,
    correta         INTEGER,                              -- NULL enquanto nao corrigido
    marcada_revisao INTEGER NOT NULL DEFAULT 0,
    tempo_seg       INTEGER,
    UNIQUE (tentativa_id, pergunta_id)
);

-- ------------------------------------------------------------- progresso
CREATE TABLE IF NOT EXISTS progresso (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    modulo_id     INTEGER NOT NULL REFERENCES modulos (id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'nao_iniciado'
                  CHECK (status IN ('nao_iniciado', 'em_andamento', 'concluido')),
    melhor_nota   REAL,
    tentativas    INTEGER NOT NULL DEFAULT 0,
    acertos       INTEGER NOT NULL DEFAULT 0,
    respostas     INTEGER NOT NULL DEFAULT 0,
    ultimo_acesso TEXT,
    concluido_em  TEXT,
    UNIQUE (usuario_id, modulo_id)
);
