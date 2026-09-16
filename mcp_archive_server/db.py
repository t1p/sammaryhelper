"""Доступ на чтение к архивной базе Sammaryhelper (PostgreSQL).

Схема (см. Sammaryhelper/db_handler.py) создаётся и заполняется самим
приложением Sammaryhelper. Этот модуль ничего не создаёт и не изменяет —
только SELECT.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import asyncpg

DEFAULT_DB_ENV_FILE = Path.home() / ".config" / "tg-archive" / "db.env"

logger = logging.getLogger(__name__)


def _read_db_env_file(path: Path) -> dict[str, str]:
    """Читает простой файл вида KEY=VALUE (без экспортов, без кавычек-магии).
    Не падает, если файла нет — это резервный источник пароля, не обязательный."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def parse_accounts(env_value: Optional[str]) -> dict[str, str]:
    """Разбирает TG_ARCHIVE_ACCOUNTS="prod:79253010707,test:..." в словарь
    {lazgram_key: archive_account_id}. Пустая/отсутствующая переменная -> {}."""
    result: dict[str, str] = {}
    if not env_value:
        return result
    for pair in env_value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, sep, archive_id = pair.partition(":")
        if not sep:
            raise ValueError(
                f"Некорректная запись в TG_ARCHIVE_ACCOUNTS: {pair!r} "
                "(ожидается 'lazgram_key:archive_account_id')"
            )
        result[key.strip()] = archive_id.strip()
    return result


def resolve_account_id(value: Optional[str], accounts: dict[str, str]) -> Optional[str]:
    """Переводит алиас аккаунта в нотации Lazgram (например "prod") в
    account_id архива. Числовой account_id пропускается как есть (это и
    есть раскодированное значение). Неизвестный нечисловой алиас — явная
    ошибка, а не пустой список (см. B3 задания)."""
    if not value:
        return None
    if value in accounts:
        return accounts[value]
    if value.isdigit() or value in accounts.values():
        return value
    raise ValueError(
        f"Неизвестный алиас аккаунта {value!r}. Известные: {sorted(accounts) or '(TG_ARCHIVE_ACCOUNTS не задан)'}"
    )

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
    user: str = "tg_archive_ro"
    password: str = ""
    accounts: dict[str, str] = None  # type: ignore[assignment]

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
        3. Значения по умолчанию (без пароля и без user=postgres —
           read-only роль обязана быть указана явно, никакого суперюзерского
           дефолта тут быть не должно).

        Пароль отдельно: TG_ARCHIVE_DB_PASSWORD, иначе ~/.config/tg-archive/db.env
        (TG_ARCHIVE_DB_PASSWORD=...), иначе файл конфигурации Sammaryhelper.
        """
        defaults = cls(accounts={})

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

        db_env_file = _read_db_env_file(DEFAULT_DB_ENV_FILE)
        password = (
            os.environ.get("TG_ARCHIVE_DB_PASSWORD")
            or db_env_file.get("TG_ARCHIVE_DB_PASSWORD")
            or file_settings.get("password")
        )
        if not password:
            raise RuntimeError(
                "Пароль read-only роли не найден: задайте TG_ARCHIVE_DB_PASSWORD, "
                f"или положите его в {DEFAULT_DB_ENV_FILE}, или в конфиг Sammaryhelper."
            )

        return cls(
            host=str(pick("TG_ARCHIVE_DB_HOST", "host", defaults.host)),
            port=int(pick("TG_ARCHIVE_DB_PORT", "port", defaults.port)),
            database=str(pick("TG_ARCHIVE_DB_NAME", "database", defaults.database)),
            user=str(pick("TG_ARCHIVE_DB_USER", "user", defaults.user)),
            password=password,
            accounts=parse_accounts(os.environ.get("TG_ARCHIVE_ACCOUNTS")),
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
        async with self.pool.acquire() as conn:
            ro = await conn.fetchval("SHOW default_transaction_read_only")
        if ro != "on":
            logger.warning(
                "default_transaction_read_only=%s: сервер запущен не под read-only ролью "
                "(ожидалась tg_archive_ro). Продолжаю в read-only режиме на уровне кода, "
                "но физической защиты от записи на уровне БД нет.",
                ro,
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
    ) -> dict[str, Any]:
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

        if rows:
            return {"coverage": "partial", "messages": [dict(r) for r in rows]}

        # Пустой список неоднозначен: чат мог просто не иметь сообщений в
        # выборке, либо для него вообще не выкачивались сообщения (130 из
        # 2010 диалогов имеют покрытие). Различаем явно.
        exists_sql = f"SELECT EXISTS (SELECT 1 FROM messages WHERE {' AND '.join(conditions)})"
        async with self.pool.acquire() as conn:
            has_any = await conn.fetchval(
                exists_sql,
                *([dialog_id, account_id] if account_id else [dialog_id]),
            )
        if has_any:
            return {"coverage": "partial", "messages": []}
        return {
            "coverage": "none",
            "messages": [],
            "hint": "чат есть в архиве, но его сообщения не выкачивались; бери историю через lazgram_history",
        }

    async def resolve_chat(
        self,
        query: str,
        account_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Порядок разрешения: числовой id -> username -> точный lower(alias)
        из tg_map.chat_alias -> ILIKE по title_live/title_archive.
        Останавливается на первом шаге, давшем хоть один результат."""
        async with self.pool.acquire() as conn:
            query_stripped = query.strip()

            # 1. числовой id
            try:
                chat_id = int(query_stripped)
            except ValueError:
                chat_id = None
            if chat_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT v.* FROM tg_map.v_chat v
                    JOIN tg_map.account a ON a.account_key = v.account_key
                    WHERE a.archive_account_id = $1 AND v.chat_id = $2
                    """,
                    account_id,
                    chat_id,
                )
                if rows:
                    return self._chat_candidates(rows, "id")

            # 2. username (точное совпадение, без учёта регистра и "@")
            username = query_stripped.lstrip("@")
            rows = await conn.fetch(
                """
                SELECT v.* FROM tg_map.v_chat v
                JOIN tg_map.account a ON a.account_key = v.account_key
                WHERE a.archive_account_id = $1 AND lower(v.username) = lower($2)
                """,
                account_id,
                username,
            )
            if rows:
                return self._chat_candidates(rows, "username")

            # 3. точный алиас (историческое или текущее название целиком)
            rows = await conn.fetch(
                """
                SELECT v.* FROM tg_map.v_chat v
                JOIN tg_map.account a ON a.account_key = v.account_key
                JOIN tg_map.chat_alias al
                     ON al.account_key = v.account_key AND al.chat_id = v.chat_id
                WHERE a.archive_account_id = $1 AND lower(al.alias) = lower($2)
                """,
                account_id,
                query_stripped,
            )
            if rows:
                return self._chat_candidates(rows, "alias_exact")

            # 4. частичное совпадение по названию (архивному или текущему)
            rows = await conn.fetch(
                """
                SELECT v.* FROM tg_map.v_chat v
                JOIN tg_map.account a ON a.account_key = v.account_key
                WHERE a.archive_account_id = $1
                  AND (v.title_live ILIKE $2 OR v.title_archive ILIKE $2)
                LIMIT $3
                """,
                account_id,
                f"%{query_stripped}%",
                limit,
            )
            return self._chat_candidates(rows, "title_ilike")

    @staticmethod
    def _chat_candidates(rows: list[Any], match_kind: str) -> list[dict[str, Any]]:
        candidates = [{**dict(r), "match_kind": match_kind} for r in rows]
        if len(candidates) == 1:
            candidates[0]["unambiguous"] = True
        return candidates

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
