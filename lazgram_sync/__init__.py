"""Синхронизация архива Sammaryhelper с живым Telegram через LazGram.

LazGram (github.com/t1p/lazgram-node) — отдельный сервис на TDLib,
подключённый как MCP-коннектор. Этот пакет — MCP-*клиент*: он сам
подключается к `lazgram-mcp.mjs` по stdio, читает чаты и историю
сообщений по конфигу (список чатов + дата "с какого числа") и пишет их
в ту же PostgreSQL-базу, что и сам Sammaryhelper — через его же
`DatabaseHandler.cache_dialogs`/`cache_messages`, а не отдельным
конкурирующим путём записи.
"""
