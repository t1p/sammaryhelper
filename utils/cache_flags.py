"""Shared utilities for LAZGRAM_CACHE_ENABLED flag parsing."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_lazgram_cache_enabled(value: Optional[str]) -> bool:
    """Разбирает переменную окружения LAZGRAM_CACHE_ENABLED в булево значение.

    Возможные значения: 'true', '1', 'yes' -> True
                        'false', '0', 'no' -> False
    Неизвестные значения -> False (безопасное поведение — кэш выключен)
    None/пусто -> True (default: cache enabled)
    """
    if not value:
        return True  # default: cache enabled
    value_lower = str(value).strip().lower()
    if value_lower in ("true", "1", "yes"):
        return True
    if value_lower in ("false", "0", "no"):
        return False
    # Неизвестное значение — логируем и выключаем кэш
    logger.warning(
        f"Неизвестное значение LAZGRAM_CACHE_ENABLED={value!r}, ожидается "
        "'true'/'false'/'1'/'0'/'yes'/'no'. Устанавливаю в False (кэш выключен)."
    )
    return False
