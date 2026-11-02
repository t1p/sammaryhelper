-- Down migration: drop message_cache table
-- Идемпотентна.

DROP TABLE IF EXISTS tg_map.message_cache CASCADE;
