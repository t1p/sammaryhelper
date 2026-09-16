-- Схема маппинга tg_map: чаты/алиасы/аккаунты, накапливаемые нами (не архив Sammaryhelper).
-- Применять от суперюзера: psql -v ON_ERROR_STOP=1 -v map_pw="$MAP_PW" -d telegram_summarizer -f 002_tg_map.sql
-- Идемпотентна.

CREATE SCHEMA IF NOT EXISTS tg_map;

SELECT format('CREATE ROLE tg_map_rw LOGIN PASSWORD %L', :'map_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tg_map_rw')
\gexec

GRANT CONNECT ON DATABASE telegram_summarizer TO tg_map_rw;
GRANT USAGE, CREATE ON SCHEMA tg_map TO tg_map_rw;
GRANT USAGE ON SCHEMA tg_map TO tg_archive_ro;

CREATE TABLE IF NOT EXISTS tg_map.account (
    account_key         text PRIMARY KEY,
    archive_account_id  text UNIQUE,
    lazgram_account     text UNIQUE,
    tg_user_id          bigint,
    note                text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tg_map.chat (
    account_key   text NOT NULL REFERENCES tg_map.account,
    chat_id        bigint NOT NULL,
    chat_type      text,
    username       text,
    title_live     text,
    title_archive  text,
    in_archive     boolean NOT NULL DEFAULT false,
    is_live        boolean NOT NULL DEFAULT false,
    first_seen     timestamptz NOT NULL DEFAULT now(),
    last_seen      timestamptz,
    source         text NOT NULL,
    PRIMARY KEY (account_key, chat_id)
);

CREATE TABLE IF NOT EXISTS tg_map.chat_alias (
    account_key  text NOT NULL,
    chat_id       bigint NOT NULL,
    alias         text NOT NULL,
    source        text NOT NULL,
    seen_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_key, chat_id, alias),
    FOREIGN KEY (account_key, chat_id) REFERENCES tg_map.chat (account_key, chat_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS chat_alias_lower_alias_idx ON tg_map.chat_alias (lower(alias));

CREATE TABLE IF NOT EXISTS tg_map.sync_run (
    id            bigserial PRIMARY KEY,
    source        text,
    started_at    timestamptz,
    finished_at   timestamptz,
    rows_seen     int,
    rows_written  int,
    status        text,
    error         text
);

-- Сид аккаунта: архив хранит телефон, lazgram — ключ.
INSERT INTO tg_map.account (account_key, archive_account_id, lazgram_account)
VALUES ('igor', '79253010707', 'prod')
ON CONFLICT (account_key) DO UPDATE
    SET archive_account_id = EXCLUDED.archive_account_id,
        lazgram_account    = EXCLUDED.lazgram_account,
        updated_at         = now();

-- Бэкфилл чатов из архива (~2010 строк). Русские типы конвертируются в TDLib-нотацию.
INSERT INTO tg_map.chat (account_key, chat_id, chat_type, title_archive, in_archive, last_seen, source)
SELECT
    'igor',
    d.id,
    CASE d.type
        WHEN 'Личка' THEN 'private'
        WHEN 'Чат'   THEN 'group'
        WHEN 'Канал' THEN 'channel'
        ELSE lower(d.type)
    END,
    d.name,
    true,
    d.updated_at,
    'archive'
FROM public.dialogs d
WHERE d.account_id = '79253010707'
ON CONFLICT (account_key, chat_id) DO UPDATE
    SET title_archive = EXCLUDED.title_archive,
        in_archive     = true,
        last_seen      = EXCLUDED.last_seen;

INSERT INTO tg_map.chat_alias (account_key, chat_id, alias, source)
SELECT 'igor', d.id, d.name, 'archive'
FROM public.dialogs d
WHERE d.account_id = '79253010707'
  AND d.name IS NOT NULL
ON CONFLICT (account_key, chat_id, alias) DO NOTHING;

-- Единственная точка, куда ходит MCP-сервер. Статистика по messages сюда намеренно не входит
-- (seq scan по 46 МБ без индекса на каждую строку вью) — считается точечно, по запрошенному чату.
CREATE OR REPLACE VIEW tg_map.v_chat AS
SELECT
    c.account_key,
    c.chat_id,
    c.chat_type,
    c.username,
    c.title_live,
    c.title_archive,
    COALESCE(c.title_live, c.title_archive) AS title,
    c.in_archive,
    c.is_live,
    d.folder_id,
    d.updated_at AS archive_updated_at,
    c.first_seen,
    c.last_seen,
    c.source
FROM tg_map.chat c
LEFT JOIN tg_map.account a ON a.account_key = c.account_key
LEFT JOIN public.dialogs d ON d.id = c.chat_id AND d.account_id = a.archive_account_id;

GRANT SELECT ON ALL TABLES IN SCHEMA tg_map TO tg_archive_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA tg_map GRANT SELECT ON TABLES TO tg_archive_ro;
