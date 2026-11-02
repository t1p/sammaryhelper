DROP DATABASE IF EXISTS telegram_summarizer;
CREATE DATABASE telegram_summarizer;
\c telegram_summarizer

CREATE TABLE dialogs (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    folder_id INTEGER,
    account_id TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE messages (
    id BIGINT NOT NULL,
    dialog_id BIGINT NOT NULL,
    sender_id BIGINT,
    sender_name TEXT,
    text TEXT,
    date TIMESTAMP NOT NULL,
    account_id TEXT NOT NULL,
    message_thread_id BIGINT,
    data JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, dialog_id)
);
