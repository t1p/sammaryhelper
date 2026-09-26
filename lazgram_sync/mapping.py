"""Преобразование Chat/Message из LazGram в формат, который ждут
Sammaryhelper.db_handler.DatabaseHandler.cache_dialogs()/cache_messages().

Важные ограничения (см. README):
- LazGram не резолвит имена отправителей — sender_name всегда = str(senderId).
- LazGram не отдаёт папки (Telegram chat folders) — folder дополняется из
  уже закешированной ранее записи, если она есть, иначе None.
- Маппинг типа чата нарочно повторяет соглашение, которое уже использует
  сам Sammaryhelper (Sammaryhelper/telegram_client_dialogs.py): любой канал
  ИЛИ супергруппа -> "Канал", обычная (не супергруппа) группа -> "Чат",
  личка -> "Личка" — иначе один и тот же чат получил бы разные типы в
  зависимости от того, кто его синхронизировал.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

_TYPE_MAP = {
    "channel": "Канал",
    "supergroup": "Канал",
    "group": "Чат",
    "private": "Личка",
}


def map_chat_type(lazgram_type: str) -> str:
    return _TYPE_MAP.get(lazgram_type, lazgram_type)


def build_dialog(chat: dict[str, Any], existing_folder: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """LazGram Chat ({id,type,title,username}) -> словарь для cache_dialogs()."""
    return {
        "id": chat["id"],
        "name": chat.get("title") or f"Chat {chat['id']}",
        "type": map_chat_type(chat.get("type", "")),
        "folder": existing_folder,
        "unread_count": 0,
        "username": chat.get("username"),
        "source": "lazgram",
    }


def build_placeholder_dialog(chat_id: int, existing_folder: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Когда чат не нашёлся в lazgram_chats (лимит 200 / архивирован) — минимальная карточка,
    чтобы сообщения всё равно можно было закешировать с валидной ссылкой на dialog_id."""
    return {
        "id": chat_id,
        "name": f"Chat {chat_id}",
        "type": "Чат",
        "folder": existing_folder,
        "unread_count": 0,
        "source": "lazgram",
        "incomplete": True,
    }


def build_message(message: dict[str, Any]) -> dict[str, Any]:
    """LazGram Message -> словарь для cache_messages()."""
    date = message.get("date")
    if isinstance(date, (int, float)):
        date = datetime.datetime.utcfromtimestamp(date)

    return {
        "id": message["id"],
        "sender_id": message.get("senderId"),
        "sender_name": str(message.get("senderId")),
        "text": message.get("text", ""),
        "date": date,
        "message_thread_id": None,
        "reply_to_message_id": message.get("replyToMessageId"),
        "is_outgoing": message.get("isOutgoing", False),
        "has_attachment": message.get("hasAttachment", False),
        "source": "lazgram",
    }
