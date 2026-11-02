"""Оркестрация одного прогона синка: LazGram -> Sammaryhelper.db_handler.

Алгоритм на чат:
1. Разрешить chatId (через lazgram_history с username — сервис резолвит сам)
   и подтянуть title/type из lazgram_chats (кешируется на весь прогон).
2. Пагинация lazgram_history назад (fromMessageId), пока не упрёмся в
   `since`, в пустую страницу или в max_pages (защита от бесконечного
   ухода в историю на дату, которой не существует).
3. cache_dialogs()/cache_messages() тем же DatabaseHandler, что и сам
   Sammaryhelper — то есть тот же формат данных, тот же upsert.
"""

from __future__ import annotations

import dataclasses
import datetime
import logging
from typing import Any, Optional

from Sammaryhelper.db_handler import DatabaseHandler

from .config import ChatTarget, LazgramConfig, SyncJobConfig
from .lazgram_client import LazgramClient
from .mapping import build_dialog, build_message, build_placeholder_dialog

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ChatSyncResult:
    chat_id: Optional[int]
    label: str
    messages_fetched: int = 0
    pages_fetched: int = 0
    hit_max_pages: bool = False
    error: Optional[str] = None
    dialog_found_in_chats_list: bool = True


@dataclasses.dataclass
class SyncSummary:
    account_id: str
    dry_run: bool = False
    account_id_warning: Optional[str] = None
    results: list[ChatSyncResult] = dataclasses.field(default_factory=list)

    @property
    def total_messages(self) -> int:
        return sum(r.messages_fetched for r in self.results)


def _to_epoch(dt: Optional[datetime.datetime]) -> Optional[float]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.timestamp()
    return dt.replace(tzinfo=datetime.timezone.utc).timestamp()


async def _fetch_since(
    client: LazgramClient,
    target: ChatTarget,
    max_pages: int,
) -> tuple[Optional[int], list[dict[str, Any]], int, bool]:
    since_ts = _to_epoch(target.since)
    messages: list[dict[str, Any]] = []
    chat_id = target.chat_id
    username = target.username
    from_message_id: Optional[int] = None
    pages = 0
    hit_max_pages = False

    for page in range(max_pages):
        pages = page + 1
        resp = await client.history(
            chat_id=chat_id, username=username if chat_id is None else None, from_message_id=from_message_id
        )
        chat_id = resp.get("chatId", chat_id)
        page_messages = resp.get("messages", [])
        if not page_messages:
            break

        stop = False
        for m in page_messages:
            m_date = m.get("date")
            if since_ts is not None and isinstance(m_date, (int, float)) and m_date < since_ts:
                stop = True
                continue
            messages.append(m)

        next_from = page_messages[-1].get("id")
        if stop or next_from is None or next_from == from_message_id:
            break
        from_message_id = next_from
    else:
        hit_max_pages = True

    return chat_id, messages, pages, hit_max_pages


async def sync_chat(
    client: LazgramClient,
    db: DatabaseHandler,
    account_id: str,
    target: ChatTarget,
    chats_by_id: dict[int, dict[str, Any]],
    chats_by_username: dict[str, dict[str, Any]],
    existing_folders: dict[int, Any],
    max_pages: int,
    dry_run: bool,
) -> ChatSyncResult:
    result = ChatSyncResult(chat_id=target.chat_id, label=target.label())
    try:
        chat_id, messages, pages, hit_max_pages = await _fetch_since(client, target, max_pages)
        result.chat_id = chat_id
        result.pages_fetched = pages
        result.hit_max_pages = hit_max_pages
        result.messages_fetched = len(messages)

        if chat_id is None:
            result.error = "LazGram не вернул chatId (чат не найден/не резолвится)"
            return result

        chat_meta = chats_by_id.get(chat_id) or (chats_by_username.get(target.username) if target.username else None)
        if chat_meta:
            dialog = build_dialog(chat_meta, existing_folders.get(chat_id))
        else:
            result.dialog_found_in_chats_list = False
            dialog = build_placeholder_dialog(chat_id, existing_folders.get(chat_id))

        if not dry_run:
            await db.cache_dialogs([dialog], account_id)
            if messages:
                mapped = [build_message(m) for m in messages]
                await db.cache_messages(mapped, chat_id, account_id)

        return result
    except Exception as e:  # noqa: BLE001 — один упавший чат не должен рушить весь прогон
        result.error = str(e)
        logger.warning("Синк чата %s завершился ошибкой: %s", target.label(), e)
        return result


async def run_sync(
    job: SyncJobConfig,
    lazgram_config: Optional[LazgramConfig] = None,
    dry_run: bool = False,
    db_config: Optional[Any] = None,
    lazgram_extra_env: Optional[dict[str, str]] = None,
) -> SyncSummary:
    lazgram_config = lazgram_config or LazgramConfig.load()
    lazgram_config.validate()

    summary = SyncSummary(account_id=job.account_id, dry_run=dry_run)

    db = DatabaseHandler()
    if db_config is None:
        from mcp_archive_server.db import ArchiveConfig  # переиспользуем те же TG_ARCHIVE_DB_* настройки

        db_config = ArchiveConfig.load()
    db.config = dataclasses.asdict(db_config)
    await db.init_connection()

    try:
        existing_accounts = await db.connection_pool.fetch("SELECT DISTINCT account_id FROM dialogs")
        existing_ids = {r["account_id"] for r in existing_accounts}
        if existing_ids and job.account_id not in existing_ids:
            summary.account_id_warning = (
                f"account_id='{job.account_id}' из конфига не встречается среди уже "
                f"закешированных ({sorted(existing_ids)}). Сообщения лягут в отдельный, "
                "не связанный с прежним архивом раздел — проверьте, что account_id в "
                "конфиге синка совпадает с тем, что уже в Postgres для этого Telegram-аккаунта."
            )
            logger.warning(summary.account_id_warning)

        existing_folders: dict[int, Any] = {}
        cached_dialogs = await db.get_cached_dialogs(job.account_id)
        for d in cached_dialogs:
            folder = d.get("folder")
            if folder:
                existing_folders[d["id"]] = folder

        async with LazgramClient(lazgram_config, extra_env=lazgram_extra_env) as client:
            chats_list = await client.chats(limit=200)
            chats_by_id = {c["id"]: c for c in chats_list}
            chats_by_username = {c["username"]: c for c in chats_list if c.get("username")}

            for target in job.chats:
                result = await sync_chat(
                    client,
                    db,
                    job.account_id,
                    target,
                    chats_by_id,
                    chats_by_username,
                    existing_folders,
                    job.max_pages,
                    dry_run,
                )
                summary.results.append(result)

        return summary
    finally:
        await db.close()
