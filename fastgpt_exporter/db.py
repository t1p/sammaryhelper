"""Bulk-запрос справочника диалогов поверх ArchiveDB.

Не изменяет и не дублирует mcp_archive_server — только использует его
уже открытый пул соединений (ArchiveDB.pool), чтобы одним запросом
получить всё нужное (включая folder.title из JSONB `data`, которого нет
как отдельной колонки) без N+1 обращений к БД на каждый диалог.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp_archive_server.db import ArchiveDB


async def fetch_directory(db: ArchiveDB, account_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Список диалогов с агрегированной статистикой по сообщениям, одним запросом."""
    conditions: list[str] = []
    params: list[Any] = []

    if account_id:
        params.append(account_id)
        conditions.append(f"d.account_id = ${len(params)}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT d.id, d.name, d.type, d.folder_id, d.account_id, d.data, d.updated_at,
               COALESCE(m.messages_count, 0) AS messages_count,
               m.oldest, m.newest
        FROM dialogs d
        LEFT JOIN (
            SELECT dialog_id, COUNT(*) AS messages_count, MIN(date) AS oldest, MAX(date) AS newest
            FROM messages
            GROUP BY dialog_id
        ) m ON m.dialog_id = d.id
        {where}
        ORDER BY d.name
    """
    assert db.pool is not None, "ArchiveDB.connect() должен быть вызван перед fetch_directory"
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]
