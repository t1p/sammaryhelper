"""Tests for mcp_archive_server/db.py"""

import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_archive_server.db import ArchiveConfig, ArchiveDB
from utils.cache_flags import parse_lazgram_cache_enabled


def test_parse_lazgram_cache_enabled_true_variants():
    assert parse_lazgram_cache_enabled("true") is True
    assert parse_lazgram_cache_enabled("True") is True
    assert parse_lazgram_cache_enabled("1") is True
    assert parse_lazgram_cache_enabled("yes") is True


def test_parse_lazgram_cache_enabled_false_variants():
    assert parse_lazgram_cache_enabled("false") is False
    assert parse_lazgram_cache_enabled("False") is False
    assert parse_lazgram_cache_enabled("0") is False
    assert parse_lazgram_cache_enabled("no") is False


def test_parse_lazgram_cache_enabled_default():
    assert parse_lazgram_cache_enabled(None) is True
    assert parse_lazgram_cache_enabled("") is True


def test_parse_lazgram_cache_enabled_unknown_defaults_to_false():
    assert parse_lazgram_cache_enabled("maybe") is False
    assert parse_lazgram_cache_enabled("invalid") is False


def test_archive_config_default_cache_enabled():
    config = ArchiveConfig()
    assert config.lazgram_cache_enabled is True


def test_archive_config_from_bool():
    config = ArchiveConfig(lazgram_cache_enabled=False)
    assert config.lazgram_cache_enabled is False

    config = ArchiveConfig(lazgram_cache_enabled=True)
    assert config.lazgram_cache_enabled is True


# ===== Тесты cache-hit path (с mock asyncpg) =====


@pytest.mark.asyncio
async def test_get_cached_messages_returns_rows_when_enabled():
    """Проверить, что get_cached_messages возвращает строки из кэша."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    # Mock pool.acquire() контекст
    mock_conn = AsyncMock()
    now = datetime.datetime.now(datetime.timezone.utc)
    mock_rows = [
        {"message_id": 1, "chat_id": 100, "sender_id": 200, "text": "msg1", "sent_at": now, "raw_json": {}, "cached_at": now},
        {"message_id": 2, "chat_id": 100, "sender_id": 200, "text": "msg2", "sent_at": now, "raw_json": {}, "cached_at": now},
    ]
    mock_conn.fetch = AsyncMock(return_value=mock_rows)

    db.pool = MagicMock()
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await db.get_cached_messages(chat_id=100, limit=20)
    assert result["has_cached"] is True
    assert len(result["messages"]) == 2
    assert result["messages"][0]["message_id"] == 1


@pytest.mark.asyncio
async def test_get_cached_messages_disabled():
    """Проверить, что get_cached_messages возвращает пусто при cache_enabled=false."""
    config = ArchiveConfig(lazgram_cache_enabled=False)
    db = ArchiveDB(config=config)

    result = await db.get_cached_messages(chat_id=100, limit=20)
    assert result["has_cached"] is False
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_get_recent_messages_cache_hit():
    """Проверить, что get_recent_messages возвращает coverage='cached' при наличии кэша."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    # Mock cache hit
    mock_conn = AsyncMock()
    cached_msg = {
        "id": 1,
        "message_id": 1,
        "chat_id": 100,
        "sender_id": 200,
        "text": "cached message",
        "sent_at": datetime.datetime.now(datetime.timezone.utc),
        "raw_json": {},
        "cached_at": datetime.datetime.now(datetime.timezone.utc),
    }
    mock_conn.fetch = AsyncMock(return_value=[cached_msg])

    db.pool = MagicMock()
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await db.get_recent_messages(dialog_id=100)
    assert result["coverage"] == "cached"
    assert len(result["messages"]) == 1
    assert "cached_at" in result


@pytest.mark.asyncio
async def test_get_recent_messages_fallback_to_archive():
    """Проверить, что get_recent_messages падает на public.messages когда кэш пуст."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    # Mock: кэш пуст, но архив есть
    mock_conn = AsyncMock()

    # First call: get_cached_messages returns empty
    cache_result = []
    # Second call: search_messages returns archive data
    archive_result = [
        {"id": 1, "sender_id": 200, "sender_name": "200", "text": "archive message", "date": datetime.datetime.now()}
    ]

    mock_conn.fetch = AsyncMock(side_effect=[cache_result, archive_result])
    mock_conn.fetchval = AsyncMock(return_value=True)  # EXISTS returns True

    db.pool = MagicMock()
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await db.get_recent_messages(dialog_id=100)
    assert result["coverage"] == "archive"
    assert "hint" in result  # Hint about cache not having data


@pytest.mark.asyncio
async def test_get_recent_messages_flag_false_only_public():
    """Проверить, что при cache_enabled=false используется только public.messages."""
    config = ArchiveConfig(lazgram_cache_enabled=False)
    db = ArchiveDB(config=config)

    mock_conn = AsyncMock()
    archive_result = [
        {"id": 1, "sender_id": 200, "sender_name": "200", "text": "message", "date": datetime.datetime.now()}
    ]
    mock_conn.fetch = AsyncMock(return_value=archive_result)

    db.pool = MagicMock()
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await db.get_recent_messages(dialog_id=100)
    # Should not call tg_map.message_cache, only public.messages
    assert result["coverage"] == "archive"
    assert result["source"] == "archive"
    assert len(result["messages"]) == 1


# ===== Тесты 3-level fallback с LazGram =====


@pytest.mark.asyncio
async def test_get_recent_messages_with_source_field():
    """Проверить, что ответ содержит поле source."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    mock_conn = AsyncMock()
    cached_msg = {
        "id": 1,
        "message_id": 1,
        "chat_id": 100,
        "sender_id": 200,
        "text": "cached",
        "sent_at": datetime.datetime.now(datetime.timezone.utc),
        "raw_json": {},
        "cached_at": datetime.datetime.now(datetime.timezone.utc),
    }
    mock_conn.fetch = AsyncMock(return_value=[cached_msg])

    db.pool = MagicMock()
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await db.get_recent_messages(dialog_id=100)
    assert result["source"] == "cache"
    assert result["coverage"] == "cached"


@pytest.mark.asyncio
async def test_get_recent_messages_archive_with_source():
    """Проверить source='archive' для данных из public.messages."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    mock_conn = AsyncMock()
    # Кэш пуст
    cache_result = []
    # Архив есть
    archive_result = [
        {"id": 1, "sender_id": 200, "sender_name": "200", "text": "archive msg", "date": datetime.datetime.now()}
    ]

    mock_conn.fetch = AsyncMock(side_effect=[cache_result, archive_result])

    db.pool = MagicMock()
    db.pool.acquire = MagicMock()
    db.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    db.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    result = await db.get_recent_messages(dialog_id=100)
    assert result["source"] == "archive"
    assert result["coverage"] == "archive"


@pytest.mark.asyncio
async def test_try_lazgram_fallback_success(monkeypatch):
    """Проверить успешный вызов LazGram fallback и кэширование."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    # Mock LazgramClient
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    # Моделируем ответ LazGram
    mock_client.history = AsyncMock(
        return_value={
            "chatId": 100,
            "messages": [
                {
                    "id": 1,
                    "senderId": 200,
                    "text": "Hello from LazGram",
                    "date": 1700000000,
                    "isOutgoing": False,
                }
            ],
        }
    )

    # Mock LazgramClient конструктор
    def mock_lazgram_client_init(config):
        return mock_client

    monkeypatch.setattr("mcp_archive_server.db.LazgramClient", mock_lazgram_client_init)

    # Mock LazgramConfig.load
    mock_config = MagicMock()
    mock_config.validate = MagicMock()

    def mock_load():
        return mock_config

    monkeypatch.setattr("mcp_archive_server.db.LazgramConfig.load", mock_load)

    # Mock окружение
    monkeypatch.setenv("LAZGRAM_SYNC_ACCOUNT", "test_account")

    # Mock DB write (should not fail)
    db._write_to_cache = AsyncMock()

    result = await db._try_lazgram_fallback(chat_id=100, limit=20)

    assert result is not None
    assert result["source"] == "lazgram_fallback"
    assert result["coverage"] == "cached"
    assert len(result["messages"]) == 1
    assert result["messages"][0]["text"] == "Hello from LazGram"

    # Проверяем, что попытались записать в кэш
    db._write_to_cache.assert_called_once()


@pytest.mark.asyncio
async def test_try_lazgram_fallback_unavailable(monkeypatch):
    """Проверить graceful handling при недоступности LazGram."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    # Mock LazgramClient с ошибкой
    from mcp_archive_server.db import LazgramError

    def mock_lazgram_client_init(config):
        raise LazgramError("Connection refused")

    monkeypatch.setattr("mcp_archive_server.db.LazgramClient", mock_lazgram_client_init)

    # Mock LazgramConfig.load
    mock_config = MagicMock()
    mock_config.validate = MagicMock()

    def mock_load():
        return mock_config

    monkeypatch.setattr("mcp_archive_server.db.LazgramConfig.load", mock_load)

    # Mock окружение
    monkeypatch.setenv("LAZGRAM_SYNC_ACCOUNT", "test_account")

    result = await db._try_lazgram_fallback(chat_id=100, limit=20)

    # Should return None gracefully, not raise
    assert result is None


@pytest.mark.asyncio
async def test_try_lazgram_fallback_empty_response(monkeypatch):
    """Проверить handling пустого ответа от LazGram."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    # Mock LazgramClient
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.history = AsyncMock(return_value={"chatId": 100, "messages": []})

    def mock_lazgram_client_init(config):
        return mock_client

    monkeypatch.setattr("mcp_archive_server.db.LazgramClient", mock_lazgram_client_init)

    # Mock LazgramConfig.load
    mock_config = MagicMock()
    mock_config.validate = MagicMock()

    def mock_load():
        return mock_config

    monkeypatch.setattr("mcp_archive_server.db.LazgramConfig.load", mock_load)

    # Mock окружение
    monkeypatch.setenv("LAZGRAM_SYNC_ACCOUNT", "test_account")

    result = await db._try_lazgram_fallback(chat_id=100, limit=20)

    assert result is not None
    assert result["source"] == "lazgram_fallback"
    assert result["coverage"] == "none"
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_try_lazgram_fallback_timeout(monkeypatch):
    """Если LazGram подвис (не ответил вовсе), fallback не должен блокировать
    запрос агента — должен вернуть None по таймауту (graceful MISS), а не
    висеть бесконечно."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)

    async def hanging_fetch(lazgram_config, chat_id, limit):
        await asyncio.sleep(10)  # дольше таймаута теста
        return {"messages": []}

    monkeypatch.setattr(db, "_fetch_lazgram_history", hanging_fetch)

    mock_config = MagicMock()
    mock_config.validate = MagicMock()
    monkeypatch.setattr("mcp_archive_server.db.LazgramConfig.load", lambda: mock_config)
    monkeypatch.setenv("LAZGRAM_SYNC_ACCOUNT", "test_account")
    monkeypatch.setenv("LAZGRAM_FALLBACK_TIMEOUT_S", "0.05")

    result = await asyncio.wait_for(db._try_lazgram_fallback(chat_id=100, limit=20), timeout=2)

    assert result is None


@pytest.mark.asyncio
async def test_write_to_cache_on_conflict_updates_existing_row():
    """Повторная запись того же (account_key, chat_id, message_id) должна
    обновлять text/sender_id/raw_json/cached_at (ON CONFLICT DO UPDATE), а не
    молча игнорировать изменения — так же, как это делает batch-синк
    (lazgram_sync/sync.py)."""
    config = ArchiveConfig(lazgram_cache_enabled=True)
    db = ArchiveDB(config=config)
    db._get_write_password = MagicMock(return_value="")

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.close = AsyncMock()

    with patch("mcp_archive_server.db.asyncpg.connect", AsyncMock(return_value=mock_conn)):
        await db._write_to_cache([
            {
                "account_key": "igor",
                "chat_id": 100,
                "message_id": 1,
                "sender_id": 200,
                "text": "edited text",
                "sent_at": datetime.datetime.now(datetime.timezone.utc),
                "raw_json": "{}",
            }
        ])

    mock_conn.execute.assert_called_once()
    sql = mock_conn.execute.call_args[0][0]
    assert "ON CONFLICT (account_key, chat_id, message_id) DO UPDATE" in sql
    assert "SET text = EXCLUDED.text" in sql
