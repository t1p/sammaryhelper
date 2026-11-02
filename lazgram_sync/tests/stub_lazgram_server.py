#!/usr/bin/env python3
"""Стаб LazGram MCP-сервера для тестов: те же имена/схемы инструментов,
что и настоящий lazgram-mcp.mjs (lazgram_status/lazgram_chats/
lazgram_history), но данные — из JSON-фикстуры (LAZGRAM_STUB_FIXTURE_FILE),
без TDLib и без Node. Использует тот же mcp SDK, что и mcp_archive_server,
чтобы гарантировать протокольную совместимость с настоящим MCP-клиентом.
"""

import json
import os
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

_fixture_path = os.environ["LAZGRAM_STUB_FIXTURE_FILE"]
with open(_fixture_path, "r", encoding="utf-8") as f:
    _FIXTURE = json.load(f)

_CHATS: list[dict[str, Any]] = _FIXTURE["chats"]
_MESSAGES_BY_CHAT: dict[int, list[dict[str, Any]]] = {
    int(k): v for k, v in _FIXTURE.get("messages_by_chat", {}).items()
}
_USERNAME_TO_CHAT = {c["username"]: c["id"] for c in _CHATS if c.get("username")}

mcp = FastMCP("lazgram-stub")


@mcp.tool()
async def lazgram_status(account: str) -> dict:
    return {"accountId": account, "authorized": True}


@mcp.tool()
async def lazgram_chats(account: str, limit: int = 50) -> dict:
    return {"chats": _CHATS[:limit]}


@mcp.tool()
async def lazgram_history(
    account: str,
    chatId: Optional[int] = None,
    username: Optional[str] = None,
    limit: int = 20,
    fromMessageId: Optional[int] = None,
) -> dict:
    if chatId is None and username is not None:
        chatId = _USERNAME_TO_CHAT.get(username)
    messages = _MESSAGES_BY_CHAT.get(chatId, [])
    if fromMessageId is not None:
        messages = [m for m in messages if m["id"] < fromMessageId]
    return {"chatId": chatId, "messages": messages[:limit]}


if __name__ == "__main__":
    mcp.run()
