"""Разбивка элементов на пачки под лимиты FastGPT pushData
(до 200 элементов и ~10MB на запрос)."""

from __future__ import annotations

import json
from typing import Any, Iterator


def _json_size(items: list[dict[str, Any]]) -> int:
    return len(json.dumps(items, ensure_ascii=False).encode("utf-8"))


def chunk_items(
    items: list[dict[str, Any]],
    max_count: int = 200,
    max_bytes: int = 9_000_000,
) -> Iterator[list[dict[str, Any]]]:
    """Жадно собирает пачки не длиннее max_count и не тяжелее max_bytes."""
    current: list[dict[str, Any]] = []
    for item in items:
        candidate = current + [item]
        if current and (len(candidate) > max_count or _json_size(candidate) > max_bytes):
            yield current
            current = [item]
        else:
            current = candidate
    if current:
        yield current
