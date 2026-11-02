-- Кэш сообщений LazGram, наполняется через lazgram_sync.
-- Применять от суперюзера: psql -v ON_ERROR_STOP=1 -d telegram_summarizer -f 003_tg_map_message_cache.sql
-- Идемпотентна.

CREATE TABLE IF NOT EXISTS tg_map.message_cache (
    account_key TEXT NOT NULL,
    chat_id     BIGINT NOT NULL,
    message_id  BIGINT NOT NULL,
    sender_id   BIGINT,
    text        TEXT,
    sent_at     TIMESTAMPTZ NOT NULL,
    raw_json    JSONB,
    cached_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, message_id)
);

-- Индекс на account_key, chat_id для быстрого поиска сообщений конкретного чата
CREATE INDEX IF NOT EXISTS message_cache_account_chat_idx
    ON tg_map.message_cache (account_key, chat_id);

-- Индекс на sent_at для сортировки сообщений по времени
CREATE INDEX IF NOT EXISTS message_cache_sent_at_idx
    ON tg_map.message_cache (sent_at DESC);

GRANT SELECT ON tg_map.message_cache TO tg_archive_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON tg_map.message_cache TO tg_map_rw;
