"""Конфигурация синка: как запускать lazgram-mcp.mjs, и что синхронизировать."""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class LazgramConfig:
    """Как достучаться до LazGram MCP-сервера (stdio)."""

    node_bin: str = "node"
    mcp_script: str = ""
    account: str = ""
    initiator: str = "sammaryhelper-sync"
    timeout_ms: int = 30000

    @classmethod
    def load(cls, cli_overrides: Optional[dict] = None) -> "LazgramConfig":
        defaults = cls()
        cli_overrides = cli_overrides or {}

        def pick(cli_key: str, env_var: str, default: Any, cast=str) -> Any:
            if cli_overrides.get(cli_key) is not None:
                return cast(cli_overrides[cli_key])
            if env_var in os.environ:
                return cast(os.environ[env_var])
            return default

        return cls(
            node_bin=pick("node_bin", "LAZGRAM_SYNC_NODE_BIN", defaults.node_bin),
            mcp_script=pick("mcp_script", "LAZGRAM_SYNC_MCP_SCRIPT", defaults.mcp_script),
            account=pick("account", "LAZGRAM_SYNC_ACCOUNT", defaults.account),
            initiator=pick("initiator", "LAZGRAM_SYNC_INITIATOR", defaults.initiator),
            timeout_ms=pick("timeout_ms", "LAZGRAM_SYNC_TIMEOUT_MS", defaults.timeout_ms, int),
        )

    def validate(self) -> None:
        missing = []
        if not self.mcp_script:
            missing.append("LAZGRAM_SYNC_MCP_SCRIPT (путь до src/interface/mcp/lazgram-mcp.mjs)")
        if not self.account:
            missing.append("LAZGRAM_SYNC_ACCOUNT (id аккаунта LazGram, напр. 'prod')")
        if missing:
            raise ValueError("Не заданы обязательные настройки LazGram: " + ", ".join(missing))


@dataclass
class ChatTarget:
    chat_id: Optional[int] = None
    username: Optional[str] = None
    since: Optional[datetime.datetime] = None

    def label(self) -> str:
        return f"chat_id={self.chat_id}" if self.chat_id is not None else f"@{self.username}"


@dataclass
class SyncJobConfig:
    """Что синхронизировать — из JSON-файла конфига (см. chats.example.json)."""

    account_id: str
    since: Optional[datetime.datetime]
    chats: list[ChatTarget] = field(default_factory=list)
    max_pages: int = 200

    @classmethod
    def load_file(cls, path: str) -> "SyncJobConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SyncJobConfig":
        account_id = raw.get("account_id")
        if not account_id:
            raise ValueError(
                "В конфиге синка обязателен 'account_id' — тот же account_id, "
                "что уже используется в архиве Postgres для этого Telegram-аккаунта "
                "(см. list_accounts у mcp_archive_server или SELECT DISTINCT account_id FROM dialogs)."
            )

        default_since = _parse_dt(raw.get("since"))
        chats = []
        for entry in raw.get("chats", []):
            chats.append(
                ChatTarget(
                    chat_id=entry.get("chat_id"),
                    username=entry.get("username"),
                    since=_parse_dt(entry.get("since")) or default_since,
                )
            )
        if not chats:
            raise ValueError("В конфиге синка список 'chats' пуст — синхронизировать нечего.")

        return cls(
            account_id=str(account_id),
            since=default_since,
            chats=chats,
            max_pages=int(raw.get("max_pages", 200)),
        )


def _parse_dt(value: Any) -> Optional[datetime.datetime]:
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.fromisoformat(str(value))
