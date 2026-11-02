"""Конфигурация экспортёра: настройки FastGPT (подключение к БД берётся
из mcp_archive_server.db.ArchiveConfig — не дублируется здесь)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class FastGPTConfig:
    base_url: str = "http://localhost:3000"
    api_key: str = ""
    vector_model_id: Optional[str] = None
    agent_model_id: Optional[str] = None
    vlm_model_id: Optional[str] = None
    dataset_name: str = "Telegram — справочник чатов (Sammaryhelper)"
    dataset_intro: str = (
        "Справочник чатов, групп и каналов Telegram, синхронизированных "
        "приложением Sammaryhelper. Содержит только метаданные (название, "
        "тип, папка, статистика по сообщениям) — текст самих сообщений "
        "сюда не выгружается."
    )
    collection_name: str = "directory"
    parent_id: Optional[str] = None
    state_file: str = ".fastgpt_exporter_state.json"
    request_timeout: float = 30.0
    batch_size: int = 200
    dry_run: bool = False

    def __post_init__(self) -> None:
        self.batch_size = max(1, min(int(self.batch_size), 200))

    @classmethod
    def load(cls, cli_overrides: Optional[dict] = None) -> "FastGPTConfig":
        """Приоритет: CLI-оверрайды > переменные окружения > значения по умолчанию."""
        defaults = cls()
        cli_overrides = cli_overrides or {}

        def pick(cli_key: str, env_var: str, default: Any, cast=str) -> Any:
            cli_value = cli_overrides.get(cli_key)
            if cli_value is not None:
                return cast(cli_value)
            if env_var in os.environ:
                return cast(os.environ[env_var])
            return default

        return cls(
            base_url=pick("base_url", "FASTGPT_BASE_URL", defaults.base_url),
            api_key=pick("api_key", "FASTGPT_API_KEY", defaults.api_key),
            vector_model_id=pick("vector_model_id", "FASTGPT_VECTOR_MODEL_ID", defaults.vector_model_id),
            agent_model_id=pick("agent_model_id", "FASTGPT_AGENT_MODEL_ID", defaults.agent_model_id),
            vlm_model_id=pick("vlm_model_id", "FASTGPT_VLM_MODEL_ID", defaults.vlm_model_id),
            dataset_name=pick("dataset_name", "FASTGPT_DATASET_NAME", defaults.dataset_name),
            dataset_intro=pick("dataset_intro", "FASTGPT_DATASET_INTRO", defaults.dataset_intro),
            collection_name=pick("collection_name", "FASTGPT_COLLECTION_NAME", defaults.collection_name),
            parent_id=pick("parent_id", "FASTGPT_PARENT_ID", defaults.parent_id),
            state_file=pick("state_file", "FASTGPT_STATE_FILE", defaults.state_file),
            request_timeout=pick("request_timeout", "FASTGPT_REQUEST_TIMEOUT", defaults.request_timeout, float),
            batch_size=pick("batch_size", "FASTGPT_PUSH_BATCH_SIZE", defaults.batch_size, int),
            dry_run=pick("dry_run", "FASTGPT_DRY_RUN", defaults.dry_run, _truthy),
        )

    def validate(self) -> None:
        """Проверка обязательных полей перед реальным (не dry-run) запуском."""
        if self.dry_run:
            return
        missing = []
        if not self.api_key:
            missing.append("FASTGPT_API_KEY")
        if not self.vector_model_id:
            missing.append("FASTGPT_VECTOR_MODEL_ID")
        if missing:
            raise ValueError(
                "Не заданы обязательные настройки FastGPT: "
                + ", ".join(missing)
                + ". Используйте --dry-run для проверки без обращения к FastGPT."
            )
