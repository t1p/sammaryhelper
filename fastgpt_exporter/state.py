"""Локальный JSON-стейт: id датасета/коллекции FastGPT между запусками.

Хранится рядом с точкой запуска (см. FASTGPT_STATE_FILE). Содержит
специфичные для окружения id — не должен коммититься в git.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExportState:
    dataset_id: Optional[str] = None
    collection_id: Optional[str] = None
    dataset_created_at: Optional[str] = None
    last_export_at: Optional[str] = None
    last_item_count: Optional[int] = None


def load_state(path: str) -> ExportState:
    if not os.path.exists(path):
        return ExportState()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return ExportState(**{k: raw.get(k) for k in ExportState.__dataclass_fields__})
    except (json.JSONDecodeError, OSError, TypeError) as e:
        logger.warning("Не удалось прочитать стейт-файл %s (%s) — начинаем с пустого состояния", path, e)
        return ExportState()


def save_state(path: str, state: ExportState) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(asdict(state), f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
