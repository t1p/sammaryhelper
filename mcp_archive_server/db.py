"""Доступ на чтение к архивной базе Sammaryhelper (PostgreSQL).

Схема (см. Sammaryhelper/db_handler.py) создаётся и заполняется самим
приложением Sammaryhelper. Этот модуль ничего не создаёт и не изменяет —
только SELECT.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Any, Optional

import asyncpg

# Типы диалогов, которые Sammaryhelper пишет в столбец dialogs.type.
_TYPE_ALIASES = {
    "channel": "Канал",
    "канал": "Канал",
    "group": "Чат",
    "chat": "Чат",
    "чат": "Чат",
    "group_chat": "Чат",
    "private": "Личка",
    "dm": "Личка",
    "личка": "Личка",
}


def normalize_chat_type(chat_type: Optional[str]) -> Optional[str]:
    """Приводит удобный для агента тип чата ("channel"/"group"/"private" и
    их русские аналоги) к значению, реально хранящемуся в БД."""
    if not chat_type:
        return None
    return _TYPE_ALIASES.get(chat_type.strip().lower(), chat_type)


@dataclass
class ArchiveConfig:
    host: str = "localhost"
    port: int = 5432
    database: str = "telegram_summarizer"
    user: str = "postgres"
    password: str = ""

    @classmethod
    def load(cls) -> "ArchiveConfig":
        """Строит конфиг подключения.

        Приоритет:
        1. Переменные окружения TG_ARCHIVE_DB_* (рекомендуемый способ для
           отдельно запускаемого MCP-сервера).
        2. Файл конфигурации Sammaryhelper (Sammaryhelper/configs/<name>.py
           с переменной db_settings), путь к которому задан в
           TG_ARCHIVE_DB_CONFIG_FILE — удобно, если сервер разворачивается
           на той же машине (x200), где уже настроен сам Sammaryhelper.
        3. Значения по умолчанию, совпадающие с db_handler.py.
        """
        defaults = cls()

        config_file = os.environ.get("TG_ARCHIVE_DB_CONFIG_FILE")
        file_settings: dict[str, Any] = {}
        if config_file and os.path.exists(config_file):
            spec = importlib.util.spec_from_file_location("sammaryhelper_db_config", config_file)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            file_settings = getattr(module, "db_settings", {}) or {}

        def pick(env_var: str, file_key: str, default: Any) -> Any:
            if env_var in os.environ:
                return os.environ[env_var]
            return file_settings.get(file_key, default)

        return cls(
            host=str(pick("TG_ARCHIVE_DB_HOST", "host", defaults.host)),
            port=int(pick("TG_ARCHIVE_DB_PORT", "port", defaults.port)),
            database=str(pick("TG_ARCHIVE_DB_NAME", "database", defaults.database)),
            user=str(pick("TG_ARCHIVE_DB_USER", "user", defaults.user)),
            password=str(pick("TG_ARCHIVE_DB_PASSWORD", "password", defaults.password)),
        )


class ArchiveDB:
    """Read-only обёртка над архивной БД Sammaryhelper."""

    def __init__(self, config: Optional[ArchiveConfig] = None):
        self.config = config or ArchiveConfig.load()
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
            min_size=1,
            max_size=5,
        )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def list_accounts(self) -> list[dict[str, Any]]:
        query = """
            SELECT account_id,
                   COUNT(*) AS dialogs_count,
                   MAX(updated_at) AS last_synced
            FROM dialogs
            GROUP BY account_id
            ORDER BY dialogs_count DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        return [dict(r) for r in rows]

    async def search_dialogs(
        self,
        query: Optional[str],
        chat_type: Optional[str] = None,
        account_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []

        if query:
            params.append(f"%{query}%")
            conditions.append(f"name ILIKE ${len(params)}")
        if chat_type:
            params.append(normalize_chat_type(chat_type))
            conditions.append(f"type = ${len(params)}")
        if account_id:
            params.append(account_id)
            conditions.append(f"account_id = ${len(params)}")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        sql = f"""
            SELECT id, name, type, folder_id, account_id, updated_at
            FROM dialogs
            {where}
            ORDER BY updated_at DESC
            LIMIT ${len(params)}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def list_dialogs(
        self,
        chat_type: Optional[str] = None,
        account_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []

        if chat_type:
            params.append(normalize_chat_type(chat_type))
            conditions.append(f"type = ${len(params)}")
        if account_id:
            params.append(account_id)
            conditions.append(f"account_id = ${len(params)}")

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        sql = f"""
            SELECT id, name, type, folder_id, account_id, updated_at
            FROM dialogs
            {where}
            ORDER BY name
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def get_dialog(
        self,
        dialog_id: Optional[int] = None,
        name: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        conditions = []
        params: list[Any] = []

        if dialog_id is not None:
            params.append(dialog_id)
            conditions.append(f"id = ${len(params)}")
        elif name:
            params.append(f"%{name}%")
            conditions.append(f"name ILIKE ${len(params)}")
        else:
            return None

        if account_id:
            params.append(account_id)
            conditions.append(f"account_id = ${len(params)}")

        sql = f"""
            SELECT id, name, type, folder_id, account_id, data, created_at, updated_at
            FROM dialogs
            WHERE {' AND '.join(conditions)}
            ORDER BY updated_at DESC
            LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return dict(row) if row else None

    async def get_message_stats_for_dialog(self, dialog_id: int, account_id: Optional[str] = None) -> dict[str, Any]:
        conditions = ["dialog_id = $1"]
        params: list[Any] = [dialog_id]
        if account_id:
            params.append(account_id)
            conditions.append(f"account_id = ${len(params)}")
        sql = f"""
            SELECT COUNT(*) AS messages_count, MIN(date) AS oldest, MAX(date) AS newest
            FROM messages
            WHERE {' AND '.join(conditions)}
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        return dict(row) if row else {"messages_count": 0, "oldest": None, "newest": None}

    async def get_recent_messages(
        self,
        dialog_id: int,
        account_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        conditions = ["dialog_id = $1"]
        params: list[Any] = [dialog_id]
        if account_id:
            params.append(account_id)
            conditions.append(f"account_id = ${len(params)}")
        params.append(limit)
        sql = f"""
            SELECT id, sender_id, sender_name, text, date
            FROM messages
            WHERE {' AND '.join(conditions)}
            ORDER BY date DESC
            LIMIT ${len(params)}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def search_messages(
        self,
        query: str,
        dialog_id: Optional[int] = None,
        account_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        conditions = ["m.text ILIKE $1"]
        params: list[Any] = [f"%{query}%"]
        if dialog_id is not None:
            params.append(dialog_id)
            conditions.append(f"m.dialog_id = ${len(params)}")
        if account_id:
            params.append(account_id)
            conditions.append(f"m.account_id = ${len(params)}")
        params.append(limit)
        sql = f"""
            SELECT m.id, m.dialog_id, d.name AS dialog_name, m.sender_id,
                   m.sender_name, m.text, m.date
            FROM messages m
            LEFT JOIN dialogs d ON d.id = m.dialog_id AND d.account_id = m.account_id
            WHERE {' AND '.join(conditions)}
            ORDER BY m.date DESC
            LIMIT ${len(params)}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(r) for r in rows]

    async def get_stats(self) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            dialogs_by_type = await conn.fetch(
                "SELECT type, COUNT(*) AS count FROM dialogs GROUP BY type ORDER BY count DESC"
            )
            totals = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM dialogs) AS dialogs_count,
                    (SELECT COUNT(*) FROM messages) AS messages_count,
                    (SELECT MAX(updated_at) FROM dialogs) AS dialogs_last_synced,
                    (SELECT MAX(date) FROM messages) AS newest_message_date,
                    (SELECT MIN(date) FROM messages) AS oldest_message_date
                """
            )
        return {
            "dialogs_by_type": [dict(r) for r in dialogs_by_type],
            **dict(totals),
        }
