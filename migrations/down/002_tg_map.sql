-- Откат 002_tg_map.sql
-- Применять от суперюзера: psql -v ON_ERROR_STOP=1 -d telegram_summarizer -f down/002_tg_map.sql

DROP SCHEMA IF EXISTS tg_map CASCADE;

DROP OWNED BY tg_map_rw;

\c postgres

DROP ROLE IF EXISTS tg_map_rw;
