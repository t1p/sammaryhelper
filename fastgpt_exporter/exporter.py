"""Оркестрация одного прогона экспорта: БД -> элементы -> FastGPT.

Стратегия идемпотентности (см. README для обоснования):
- датасет создаётся один раз, id сохраняется в стейт сразу после успеха;
- коллекция полностью пересоздаётся на каждом прогоне (справочник
  небольшой — full refresh дешевле и надёжнее point-in-time апдейтов,
  которые FastGPT pushData не поддерживает: ответ не содержит id
  созданных элементов).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from mcp_archive_server.db import ArchiveConfig, ArchiveDB

from .batching import chunk_items
from .config import FastGPTConfig
from .db import fetch_directory
from .fastgpt_client import FastGPTClient
from .mapping import build_items
from .state import ExportState, load_state, save_state

logger = logging.getLogger(__name__)


@dataclass
class ExportSummary:
    total_dialogs: int
    by_type: dict[str, int] = field(default_factory=dict)
    batches: int = 0
    pushed: int = 0
    dry_run: bool = False
    dataset_id: Optional[str] = None
    collection_id: Optional[str] = None
    dataset_reused: bool = False
    collection_recreated: bool = False


def _by_type(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        t = row.get("type") or "?"
        counts[t] = counts.get(t, 0) + 1
    return counts


async def run_export(
    db_config: Optional[ArchiveConfig] = None,
    fastgpt_config: Optional[FastGPTConfig] = None,
    account_id: Optional[str] = None,
) -> ExportSummary:
    fastgpt_config = fastgpt_config or FastGPTConfig.load()
    fastgpt_config.validate()

    db = ArchiveDB(db_config)
    await db.connect()
    try:
        rows = await fetch_directory(db, account_id=account_id)
    finally:
        await db.close()

    items = build_items(rows)
    batches = list(chunk_items(items, max_count=fastgpt_config.batch_size))

    summary = ExportSummary(
        total_dialogs=len(rows),
        by_type=_by_type(rows),
        batches=len(batches),
        dry_run=fastgpt_config.dry_run,
    )

    state = load_state(fastgpt_config.state_file)
    summary.dataset_reused = bool(state.dataset_id)
    summary.collection_recreated = bool(state.collection_id)

    if fastgpt_config.dry_run:
        logger.info("Dry-run: пропускаем все обращения к FastGPT")
        return summary

    client = FastGPTClient(fastgpt_config.base_url, fastgpt_config.api_key, fastgpt_config.request_timeout)
    try:
        if not state.dataset_id:
            state.dataset_id = await client.create_dataset(
                name=fastgpt_config.dataset_name,
                intro=fastgpt_config.dataset_intro,
                vector_model_id=fastgpt_config.vector_model_id,
                agent_model_id=fastgpt_config.agent_model_id,
                vlm_model_id=fastgpt_config.vlm_model_id,
                parent_id=fastgpt_config.parent_id,
            )
            state.dataset_created_at = datetime.datetime.now().isoformat()
            save_state(fastgpt_config.state_file, state)
            logger.info("Создан датасет FastGPT: %s", state.dataset_id)

        if state.collection_id:
            await client.delete_collection(state.collection_id)

        state.collection_id = await client.create_collection(
            dataset_id=state.dataset_id,
            name=fastgpt_config.collection_name,
            parent_id=fastgpt_config.parent_id,
        )
        save_state(fastgpt_config.state_file, state)
        logger.info("Создана коллекция FastGPT: %s", state.collection_id)

        pushed = 0
        for i, batch in enumerate(batches, start=1):
            inserted = await client.push_data(state.collection_id, batch)
            pushed += inserted
            logger.info("Пачка %d/%d: отправлено %d элементов", i, len(batches), inserted)

        if pushed != len(items):
            logger.warning(
                "Число подтверждённых вставок (%d) отличается от числа элементов (%d)",
                pushed,
                len(items),
            )

        state.last_export_at = datetime.datetime.now().isoformat()
        state.last_item_count = pushed
        save_state(fastgpt_config.state_file, state)

        summary.pushed = pushed
        summary.dataset_id = state.dataset_id
        summary.collection_id = state.collection_id
        return summary
    finally:
        await client.aclose()


def render_summary(summary: ExportSummary) -> str:
    lines = [
        f"Диалогов в архиве: {summary.total_dialogs}",
        f"По типам: {summary.by_type}",
        f"Пачек для отправки: {summary.batches}",
    ]
    if summary.dry_run:
        lines.append("Режим: dry-run — обращений к FastGPT не было")
        lines.append(f"Датасет будет переиспользован: {summary.dataset_reused}")
        lines.append(f"Коллекция будет пересоздана: {summary.collection_recreated}")
    else:
        lines.append(f"Отправлено элементов: {summary.pushed}")
        lines.append(f"Dataset ID: {summary.dataset_id}")
        lines.append(f"Collection ID: {summary.collection_id}")
    return "\n".join(lines)
