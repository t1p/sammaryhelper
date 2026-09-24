"""Преобразование строки справочника диалогов в элемент для FastGPT pushData.

Только метаданные — текст сообщений сюда никогда не попадает.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

_TYPE_LABELS = {
    "Канал": "канал",
    "Чат": "группа/чат",
    "Личка": "личный диалог",
}


def _iso(value: Any) -> Any:
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    return value


def _folder_title(data: Any) -> str:
    parsed = data
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (TypeError, ValueError):
            parsed = None
    if isinstance(parsed, dict):
        folder = parsed.get("folder")
        if isinstance(folder, dict) and folder.get("title"):
            return str(folder["title"])
    return "без папки"


def build_item(row: dict[str, Any]) -> dict[str, Any]:
    """Одна строка из fetch_directory -> элемент {"q": ..., "metadata": ...} для pushData."""
    raw_type = row.get("type") or ""
    type_label = _TYPE_LABELS.get(raw_type, raw_type or "неизвестно")
    folder_title = _folder_title(row.get("data"))
    messages_count = row.get("messages_count") or 0

    if messages_count:
        period = f"{_iso(row.get('oldest'))} — {_iso(row.get('newest'))}"
    else:
        period = "сообщений нет"

    q = (
        f'Чат: "{row.get("name")}"\n'
        f"Тип: {type_label} ({raw_type})\n"
        f"Telegram ID: {row.get('id')}\n"
        f"Аккаунт: {row.get('account_id')}\n"
        f"Папка: {folder_title}\n"
        f"Сообщений в архиве: {messages_count}\n"
        f"Период сообщений: {period}\n"
        f"Обновлено в архиве: {_iso(row.get('updated_at'))}"
    )

    return {
        "q": q,
        "a": "",
        "metadata": {
            "dialog_id": row.get("id"),
            "account_id": row.get("account_id"),
            "type": raw_type,
            "folder_id": row.get("folder_id"),
        },
    }


def build_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [build_item(row) for row in rows]
