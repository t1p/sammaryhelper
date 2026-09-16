"""MCP-сервер: справочник архивных чатов/групп/каналов Telegram.

Источник данных — read-only роль tg_archive_ro поверх PostgreSQL базы
Sammaryhelper (public.dialogs/messages/topics) и схемы tg_map (маппинг
чатов и алиасов). Сервер физически не может писать (default_transaction_
read_only=on у роли), плюс полностью read-only на уровне кода.

Как использовать в связке с "живым" Telegram-MCP (lazgram):
1. Звать resolve_chat(query, account) — главный вход, принимает id,
   @username, точное/частичное или историческое название — чтобы дёшево
   получить chat_id из архива, без обращения к настоящему аккаунту.
2. С полученным chat_id — точечный вызов lazgram_history/lazgram_chats
   за актуальным названием и свежими сообщениями. Массовые обходы живого
   аккаунта через архив не нужны и опасны (rate-limit).
"""

from __future__ import annotations

import datetime
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from mcp.server.fastmcp import Context, FastMCP

from .db import ArchiveDB, resolve_account_id


def _iso(value: Any) -> Any:
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    return {k: _iso(v) for k, v in row.items()}


def _freshness(updated_at: Optional[datetime.datetime]) -> dict[str, Any]:
    """Честная модель свежести вместо булева is_stale.

    Архиву 14+ месяцев — при пороге в сутки is_stale был бы всегда true,
    и агент научился бы его игнорировать. Вместо этого — конкретные цифры
    и разная уверенность для разных полей: chat_id из архива почти не
    устаревает, название — часто, полнота сообщений — гарантированно
    частичная (сообщения есть только для 130 диалогов из 2010).
    """
    if updated_at is None:
        return {
            "source": "archive",
            "snapshot_date": None,
            "age_days": None,
            "confidence": {"chat_id": "low", "title": "low", "messages": "partial"},
        }
    now = datetime.datetime.now(updated_at.tzinfo) if updated_at.tzinfo else datetime.datetime.now()
    age_days = (now - updated_at).days
    return {
        "source": "archive",
        "snapshot_date": updated_at.date().isoformat(),
        "age_days": age_days,
        "confidence": {
            "chat_id": "high",
            "title": "high" if age_days <= 7 else "low",
            "messages": "partial",
        },
    }


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
        "Архив — снапшот Telegram на 2025 год, один аккаунт. Он надёжен для "
        "chat_id и для ИСТОРИЧЕСКИХ названий чатов; текущие названия и "
        "свежие сообщения бери в lazgram. Порядок работы: resolve_chat "
        "(принимает id, @username, точное или частичное название, старое "
        "название) -> получить chat_id -> точечный вызов "
        "lazgram_history/lazgram_chats с этим id. Массовые обходы живого "
        "аккаунта не нужны и опасны (rate-limit). search_chats/list_chats/"
        "get_chat остаются для точечных запросов, но не первый выбор — "
        "начинай с resolve_chat. Сообщения закешированы только для 130 из "
        "2010 диалогов — coverage:'none' в ответах означает, что для этого "
        "чата в архиве нет сообщений вообще, а не что их не было."
    ),
    lifespan=app_lifespan,
)


def _db(ctx: Context) -> ArchiveDB:
    return ctx.request_context.lifespan_context.db


def _account_id(ctx: Context, account: Optional[str]) -> Optional[str]:
    """Переводит алиас аккаунта в нотации Lazgram (например "prod") в
    account_id архива, если account передан. Неизвестный алиас — явная
    ошибка (см. resolve_account_id), а не молчаливый пустой список."""
    if account is None:
        return None
    accounts = _db(ctx).config.accounts or {}
    return resolve_account_id(account, accounts)


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
    rows = await _db(ctx).search_dialogs(query, chat_type, _account_id(ctx, account_id), limit)
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
    rows = await _db(ctx).list_dialogs(chat_type, _account_id(ctx, account_id), limit, offset)
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
    row = await db.get_dialog(dialog_id, name, _account_id(ctx, account_id))
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
) -> dict[str, Any]:
    """Последние закешированные сообщения конкретного чата (для быстрого
    контекста перед точечным запросом в живой Telegram).

    Возвращает {"coverage": "partial"|"none", "messages": [...], "hint"?: str}.
    coverage:"none" означает, что для чата в архиве нет ни одного сообщения
    (сообщения есть только для 130 из 2010 диалогов) — это не то же самое,
    что "сообщений не было".
    """
    result = await _db(ctx).get_recent_messages(dialog_id, _account_id(ctx, account_id), limit)
    result["messages"] = [_serialize(r) for r in result["messages"]]
    return result


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
    rows = await _db(ctx).search_messages(query, dialog_id, _account_id(ctx, account_id), limit)
    return [_serialize(r) for r in rows]


@mcp.tool()
async def resolve_chat(
    ctx: Context,
    query: str,
    account: str = "prod",
    limit: int = 10,
) -> dict[str, Any]:
    """Главный вход в справочник. Принимает что угодно: числовой id,
    "@username", точное или частичное (в т.ч. старое) название чата.

    Порядок разрешения: числовой id -> username -> точный алиас из
    tg_map.chat_alias -> ILIKE по текущему/архивному названию. Возвращает
    первый непустой набор кандидатов; у каждого — match_kind
    ("id"|"username"|"alias_exact"|"title_ilike") и unambiguous:true, если
    совпадение единственное и точное.

    account — ключ аккаунта в нотации Lazgram (по умолчанию "prod"),
    переводится в account_id архива через TG_ARCHIVE_ACCOUNTS.
    """
    account_id = _account_id(ctx, account)
    candidates = await _db(ctx).resolve_chat(query, account_id, limit)
    return {"candidates": [_serialize(c) for c in candidates]}


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
