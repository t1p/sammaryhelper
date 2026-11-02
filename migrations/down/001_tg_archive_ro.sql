-- Откат 001_tg_archive_ro.sql
-- Применять от суперюзера: psql -v ON_ERROR_STOP=1 -d telegram_summarizer -f down/001_tg_archive_ro.sql
-- DROP OWNED BY снимает гранты в БД, к которой подключился psql (-d); без этого DROP ROLE упадёт.

DROP OWNED BY tg_archive_ro;

DROP ROLE IF EXISTS tg_archive_ro;
