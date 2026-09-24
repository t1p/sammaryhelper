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

INSERT INTO dialogs (id, name, type, folder_id, account_id, data) VALUES
(100, 'Нейрофизиология и ИИ', 'Чат', 1, '+79990001122', '{"id":100,"name":"Нейрофизиология и ИИ","type":"Чат","folder":{"id":1,"title":"Работа"},"unread_count":3}'),
(101, 'LazGram Dev News', 'Канал', NULL, '+79990001122', '{"id":101,"name":"LazGram Dev News","type":"Канал","folder":null,"unread_count":0}'),
(102, 'Игорь Трапезников', 'Личка', NULL, '+79990001122', '{"id":102,"name":"Игорь Трапезников","type":"Личка","folder":null,"unread_count":0}'),
(103, 'Второй аккаунт чат', 'Чат', NULL, '+70001112233', '{"id":103,"name":"Второй аккаунт чат","type":"Чат","folder":null,"unread_count":0}');

INSERT INTO messages (id, dialog_id, sender_id, sender_name, text, date, account_id, data) VALUES
(1, 100, 555, 'Игорь', 'Обсудим план по FastGPT интеграции завтра', NOW() - INTERVAL '3 hours', '+79990001122', '{"id":1}'),
(2, 100, 556, 'Таня', 'Ок, я подготовлю материалы', NOW() - INTERVAL '2 hours', '+79990001122', '{"id":2}'),
(3, 101, 999, 'Channel', 'LazGram release notes v2', NOW() - INTERVAL '10 days', '+79990001122', '{"id":3}');
