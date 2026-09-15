"""MCP-сервер: справочник архивных чатов/групп/каналов Telegram.

Источник данных — PostgreSQL база, которую заполняет приложение
Sammaryhelper (см. Sammaryhelper/db_handler.py). Сервер только читает.

Как использовать в связке с "живым" Telegram-MCP:
1. Сначала звать инструменты этого сервера (search_chats / get_chat /
   search_messages), чтобы дёшево получить id чата, его тип и контекст
   из архива — без обращения к настоящему Telegram-аккаунту.
2. Если чат не найден в архиве, либо данные слишком старые
   (см. поле `cached_at` / `is_stale` в ответах), точечно обращаться к
   живому Telegram-инструменту (MTProto-коннектор) уже с известным id —
   это и есть экономия на массовых обходах живого аккаунта.
"""

from __future__ import annotations

import datetime
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from mcp.server.fastmcp import Context, FastMCP

from .db import ArchiveDB

# Если архив не обновлялся дольше этого срока, считаем данные устаревшими
# и подсказываем агенту, что стоит перепроверить чат в живом Telegram.
STALE_AFTER_HOURS = float(os.environ.get("TG_ARCHIVE_STALE_AFTER_HOURS", "24"))


def _iso(value: Any) -> Any:
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _iso(v) for k, v in row.items()}


def _freshness(updated_at: Optional[datetime.datetime]) -> dict[str, Any]:
    if updated_at is None:
        return {"cached_at": None, "is_stale": True}
    now = datetime.datetime.now(updated_at.tzinfo) if updated_at.tzinfo else datetime.datetime.now()
    age_hours = (now - updated_at).total_seconds() / 3600
    return {"cached_at": updated_at.isoformat(), "is_stale": age_hours > STALE_AFTER_HOURS}


@dataclass
class AppContext:
    db: ArchiveDB


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    db = ArchiveDB()
    await db.connect()
    try:
        yield AppContext(db=db)
    finally:
        await db.close()


mcp = FastMCP(
    "telegram-archive",
    instructions=(
        "Справочник архивных чатов, групп и каналов Telegram (данные из "
        "Sammaryhelper, могут быть не самыми свежими). Используй эти "
        "инструменты ПЕРВЫМИ при любом запросе про Telegram-чат: найди чат "
        "через search_chats, при необходимости подними контекст через "
        "get_chat / get_recent_messages / search_messages, и только если "
        "чата нет в архиве или данные устарели (is_stale=true) — иди в "
        "живой Telegram-коннектор точечно, уже зная id и тип чата."
    ),
    lifespan=app_lifespan,
)


def _db(ctx: Context) -> ArchiveDB:
    return ctx.request_context.lifespan_context.db


@mcp.tool()
async def list_accounts(ctx: Context) -> list[dict[str, Any]]:
    """Список Telegram-аккаунтов, для которых есть архивные данные, с числом
    закешированных диалогов и датой последней синхронизации."""
    rows = await _db(ctx).list_accounts()
    return [_serialize(r) for r in rows]


@mcp.tool()
async def search_chats(
    ctx: Context,
    query: str,
    chat_type: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Найти в архиве чаты/группы/каналы по подстроке названия.

    Args:
        query: подстрока названия чата (регистр не важен).
        chat_type: опционально — "channel", "group" или "private"
            (принимаются и русские варианты: "Канал", "Чат", "Личка").
        account_id: опционально — ограничить конкретным Telegram-аккаунтом
            (см. list_accounts).
        limit: максимум результатов.
    """
    rows = await _db(ctx).search_dialogs(query, chat_type, account_id, limit)
    return [{**_serialize(r), **_freshness(r.get("updated_at"))} for r in rows]


@mcp.tool()
async def list_chats(
    ctx: Context,
    chat_type: Optional[str] = None,
    account_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Постранично перечислить все чаты/группы/каналы в архиве (по алфавиту).

    Полезно, чтобы просто посмотреть, что вообще есть в справочнике.
    """
    rows = await _db(ctx).list_dialogs(chat_type, account_id, limit, offset)
    return [{**_serialize(r), **_freshness(r.get("updated_at"))} for r in rows]


@mcp.tool()
async def get_chat(
    ctx: Context,
    dialog_id: Optional[int] = None,
    name: Optional[str] = None,
    account_id: Optional[str] = None,
) -> dict[str, Any]:
    """Получить подробную карточку чата из архива по id или точному/частичному
    названию: тип, папка, полные данные и статистика по закешированным
    сообщениям (кол-во, диапазон дат). Нужно передать dialog_id или name.
    """
    db = _db(ctx)
    row = await db.get_dialog(dialog_id, name, account_id)
    if row is None:
        return {"found": False, "reason": "Чат не найден в архиве — стоит поискать в живом Telegram."}

    data = row.get("data")
    if isinstance(data, str):
        data = json.loads(data)

    message_stats = await db.get_message_stats_for_dialog(row["id"], row.get("account_id"))

    result = _serialize(row)
    result["data"] = data
    result.update(_freshness(row.get("updated_at")))
    result["found"] = True
    result["message_stats"] = _serialize(message_stats)
    return result


@mcp.tool()
async def get_recent_messages(
    ctx: Context,
    dialog_id: int,
    account_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Последние закешированные сообщения конкретного чата (для быстрого
    контекста перед точечным запросом в живой Telegram)."""
    rows = await _db(ctx).get_recent_messages(dialog_id, account_id, limit)
    return [_serialize(r) for r in rows]


@mcp.tool()
async def search_messages(
    ctx: Context,
    query: str,
    dialog_id: Optional[int] = None,
    account_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Полнотекстовый (ILIKE) поиск по тексту закешированных сообщений,
    опционально в пределах одного чата (dialog_id) или аккаунта."""
    rows = await _db(ctx).search_messages(query, dialog_id, account_id, limit)
    return [_serialize(r) for r in rows]


@mcp.tool()
async def get_archive_stats(ctx: Context) -> dict[str, Any]:
    """Общая статистика архива: сколько диалогов по типам, сколько сообщений
    закешировано, когда архив в последний раз синхронизировался. Полезно
    вызвать первым, чтобы понять, насколько архиву можно доверять."""
    stats = await _db(ctx).get_stats()
    return _serialize(stats)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
