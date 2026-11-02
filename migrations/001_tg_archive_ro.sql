-- Read-only роль для MCP-сервера tg-archive.
-- Применять от суперюзера: psql -v ON_ERROR_STOP=1 -v ro_pw="$RO_PW" -d telegram_summarizer -f 001_tg_archive_ro.sql
-- Идемпотентна: повторное применение не должно падать, пароль перезаписывается на переданный.
-- Гранты на public.* уходят в базу, к которой подключился psql (параметр -d) — не хардкодить \c.

SELECT format('CREATE ROLE tg_archive_ro LOGIN')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tg_archive_ro')
\gexec

ALTER ROLE tg_archive_ro PASSWORD :'ro_pw';
ALTER ROLE tg_archive_ro SET default_transaction_read_only = on;
ALTER ROLE tg_archive_ro SET statement_timeout = '10s';
ALTER ROLE tg_archive_ro SET idle_in_transaction_session_timeout = '30s';

GRANT CONNECT ON DATABASE telegram_summarizer TO tg_archive_ro;

GRANT USAGE ON SCHEMA public TO tg_archive_ro;
GRANT SELECT ON public.dialogs, public.messages, public.topics TO tg_archive_ro;
-- ai_requests / ai_responses намеренно не выдаются: логи промптов, не относятся к справочнику чатов.
