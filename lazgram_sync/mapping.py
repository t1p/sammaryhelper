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
import json
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
        date = datetime.datetime.fromtimestamp(date, tz=datetime.timezone.utc)

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


# ===== Маппинг для схемы tg_map =====


def build_tg_map_chat(
    chat: dict[str, Any],
    account_key: str = "igor",
) -> dict[str, Any]:
    """LazGram Chat -> строка для tg_map.chat."""
    return {
        "account_key": account_key,
        "chat_id": chat["id"],
        "chat_type": chat.get("type", ""),
        "username": chat.get("username"),
        "title_live": chat.get("title"),
        "source": "lazgram",
        "is_live": True,  # Свежие данные от LazGram
    }


def build_tg_map_chat_alias(
    chat: dict[str, Any],
    account_key: str = "igor",
) -> dict[str, Any]:
    """LazGram Chat -> строка для tg_map.chat_alias (если есть title/username)."""
    aliases = []

    # Добавляем title как алиас
    if chat.get("title"):
        aliases.append(
            {
                "account_key": account_key,
                "chat_id": chat["id"],
                "alias": chat["title"],
                "source": "lazgram",
            }
        )

    # Добавляем username как алиас (если есть и не совпадает с title)
    if chat.get("username") and chat.get("username") != chat.get("title"):
        aliases.append(
            {
                "account_key": account_key,
                "chat_id": chat["id"],
                "alias": chat["username"],
                "source": "lazgram",
            }
        )

    return aliases


def build_tg_map_message(
    message: dict[str, Any],
    chat_id: int,
    account_key: str = "igor",
) -> dict[str, Any]:
    """LazGram Message -> строка для tg_map.message_cache."""
    date = message.get("date")
    if isinstance(date, (int, float)):
        date = datetime.datetime.fromtimestamp(date, tz=datetime.timezone.utc)
    elif not isinstance(date, datetime.datetime):
        date = datetime.datetime.now(datetime.timezone.utc)

    return {
        "account_key": account_key,
        "chat_id": chat_id,
        "message_id": message["id"],
        "sender_id": message.get("senderId"),
        "text": message.get("text", ""),
        "sent_at": date if date.tzinfo else date.replace(tzinfo=datetime.timezone.utc),
        "raw_json": json.dumps(message, ensure_ascii=False, default=str),  # JSONB/TEXT expects a string
    }
