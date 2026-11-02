"""MCP-клиент к LazGram (src/interface/mcp/lazgram-mcp.mjs), stdio.

LazGram — stdio JSON-RPC MCP-сервер: каждый tools/call возвращает
{"content": [{"type": "text", "text": "<JSON-строка с результатом>"}]}
(см. lazgram-node/src/interface/mcp/server.mjs:formatResult) — то есть
полезные данные завёрнуты в текстовый блок как JSON-строка, а не как
structured content. Ошибки — isError=true с текстом причины.
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import LazgramConfig


class LazgramError(RuntimeError):
    pass


class LazgramClient:
    def __init__(self, config: LazgramConfig, extra_env: Optional[dict[str, str]] = None):
        """`extra_env` — точка расширения только для тестов (передать
        LAZGRAM_STUB_FIXTURE_FILE стаб-серверу); в проде не используется."""
        self._config = config
        self._extra_env = extra_env or {}
        self._stack = AsyncExitStack()
        self._session: Optional[ClientSession] = None

    async def __aenter__(self) -> "LazgramClient":
        params = StdioServerParameters(
            command=self._config.node_bin,
            args=[self._config.mcp_script],
            env={
                "LAZGRAM_MCP_ACCOUNTS": f"{self._config.account}:read-only",
                "LAZGRAM_MCP_INITIATOR": self._config.initiator,
                "LAZGRAM_MCP_TIMEOUT_MS": str(self._config.timeout_ms),
                **self._extra_env,
            },
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._stack.aclose()

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert self._session is not None, "LazgramClient используется вне `async with`"
        arguments = {"account": self._config.account, **arguments}
        result = await self._session.call_tool(name, arguments)
        text = "".join(getattr(block, "text", "") for block in result.content)
        if result.isError:
            raise LazgramError(f"{name}({arguments}): {text}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LazgramError(f"{name}: не удалось разобрать ответ LazGram как JSON: {text!r}") from e

    async def chats(self, limit: int = 200) -> list[dict[str, Any]]:
        """Список чатов аккаунта (id, type, title, username), максимум 200 (лимит LazGram)."""
        data = await self._call("lazgram_chats", {"limit": limit})
        return data.get("chats", [])

    async def history(
        self,
        chat_id: Optional[int] = None,
        username: Optional[str] = None,
        limit: int = 100,
        from_message_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Одна страница истории (новые сначала). Возвращает {"chatId":..., "messages":[...]}."""
        args: dict[str, Any] = {"limit": limit}
        if chat_id is not None:
            args["chatId"] = chat_id
        if username is not None:
            args["username"] = username
        if from_message_id is not None:
            args["fromMessageId"] = from_message_id
        return await self._call("lazgram_history", args)

    async def status(self) -> dict[str, Any]:
        return await self._call("lazgram_status", {})
