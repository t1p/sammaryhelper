"""Сквозные сценарии: временный Postgres + стаб LazGram MCP-сервера."""

from __future__ import annotations

import asyncio
import datetime
import json
import sys

import asyncpg
import pytest

from lazgram_sync.config import ChatTarget, LazgramConfig, SyncJobConfig
from lazgram_sync.sync import run_sync
from mcp_archive_server.db import ArchiveConfig

BASE_DATE = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def _messages(chat_id: int, count: int) -> list[dict]:
    """id растёт вместе с датой; список отдаём в порядке newest-first, как LazGram."""
    msgs = [
        {
            "id": i,
            "chatId": chat_id,
            "senderId": 1000 + (i % 3),
            "date": int((BASE_DATE + datetime.timedelta(minutes=i)).timestamp()),
            "text": f"message {i}",
        }
        for i in range(1, count + 1)
    ]
    return sorted(msgs, key=lambda m: m["id"], reverse=True)


DEFAULT_FIXTURE = {
    "chats": [
        {"id": 100, "type": "supergroup", "title": "Тестовая супергруппа", "username": "test_sg"},
        {"id": 200, "type": "private", "title": "Личка User"},
    ],
    "messages_by_chat": {
        "100": _messages(100, 250),
        "200": _messages(200, 5),
        "300": _messages(300, 10),  # чат отсутствует в списке chats -> placeholder-диалог
    },
}


def _lazgram_config(stub_mcp_script) -> LazgramConfig:
    return LazgramConfig(node_bin=sys.executable, mcp_script=stub_mcp_script, account="test")


async def _fetch_dialog(db_conf: dict, dialog_id: int):
    conn = await asyncpg.connect(**db_conf)
    try:
        row = await conn.fetchrow("SELECT * FROM dialogs WHERE id = $1", dialog_id)
        return dict(row) if row else None
    finally:
        await conn.close()


async def _count_messages(db_conf: dict, dialog_id: int) -> int:
    conn = await asyncpg.connect(**db_conf)
    try:
        return await conn.fetchval("SELECT COUNT(*) FROM messages WHERE dialog_id = $1", dialog_id)
    finally:
        await conn.close()


async def _insert_dialog(db_conf: dict, dialog_id: int, account_id: str, folder: dict | None):
    conn = await asyncpg.connect(**db_conf)
    try:
        data = {"id": dialog_id, "name": "Старое имя", "type": "Чат", "folder": folder, "unread_count": 0}
        await conn.execute(
            "INSERT INTO dialogs (id, name, type, folder_id, account_id, data) VALUES ($1,$2,$3,$4,$5,$6)",
            dialog_id, "Старое имя", "Чат", folder.get("id") if folder else None, account_id, json.dumps(data),
        )
    finally:
        await conn.close()


@pytest.fixture()
def db_config(temp_postgres):
    return ArchiveConfig(**temp_postgres)


@pytest.fixture()
def fixture_env(lazgram_fixture_file):
    path = lazgram_fixture_file(DEFAULT_FIXTURE)
    return {"LAZGRAM_STUB_FIXTURE_FILE": path}


@pytest.fixture(autouse=True)
def _clean_tables(temp_postgres):
    """temp_postgres — на весь сеанс тестов; чистим таблицы перед каждым тестом,
    чтобы они не зависели друг от друга (id диалогов/чатов повторяются)."""

    async def _truncate():
        conn = await asyncpg.connect(**temp_postgres)
        try:
            await conn.execute("TRUNCATE dialogs, messages")
        finally:
            await conn.close()

    asyncio.run(_truncate())
    yield


def test_sync_basic_and_since_filter(temp_postgres, db_config, stub_mcp_script, fixture_env):
    since = BASE_DATE + datetime.timedelta(minutes=200)
    job = SyncJobConfig(account_id="+79990001122", since=None, chats=[ChatTarget(chat_id=100, since=since)])
    lazgram_config = _lazgram_config(stub_mcp_script)

    summary = asyncio.run(run_sync(job, lazgram_config, db_config=db_config, lazgram_extra_env=fixture_env))

    result = summary.results[0]
    assert result.error is None
    assert result.chat_id == 100
    assert result.dialog_found_in_chats_list is True
    # id 1..250, минута=id; since на 200-й минуте -> остаются id 200..250 = 51 сообщение
    assert result.messages_fetched == 51

    dialog = asyncio.run(_fetch_dialog(temp_postgres, 100))
    assert dialog is not None
    assert dialog["name"] == "Тестовая супергруппа"
    assert dialog["type"] == "Канал"  # supergroup -> Канал по конвенции Sammaryhelper

    msg_count = asyncio.run(_count_messages(temp_postgres, 100))
    assert msg_count == 51


def test_sync_preserves_existing_folder(temp_postgres, db_config, stub_mcp_script, fixture_env):
    asyncio.run(_insert_dialog(temp_postgres, 100, "+79990001122", {"id": 9, "title": "Preserved"}))

    job = SyncJobConfig(account_id="+79990001122", since=None, chats=[ChatTarget(chat_id=100)])
    summary = asyncio.run(
        run_sync(job, _lazgram_config(stub_mcp_script), db_config=db_config, lazgram_extra_env=fixture_env)
    )

    assert summary.results[0].error is None
    dialog = asyncio.run(_fetch_dialog(temp_postgres, 100))
    data = json.loads(dialog["data"])
    assert data["folder"] == {"id": 9, "title": "Preserved"}
    assert dialog["name"] == "Тестовая супергруппа"  # имя всё равно обновилось из LazGram


def test_sync_placeholder_dialog_when_chat_not_in_list(temp_postgres, db_config, stub_mcp_script, fixture_env):
    job = SyncJobConfig(account_id="+79990001122", since=None, chats=[ChatTarget(chat_id=300)])
    summary = asyncio.run(
        run_sync(job, _lazgram_config(stub_mcp_script), db_config=db_config, lazgram_extra_env=fixture_env)
    )

    result = summary.results[0]
    assert result.dialog_found_in_chats_list is False
    dialog = asyncio.run(_fetch_dialog(temp_postgres, 300))
    assert dialog["name"] == "Chat 300"
    assert asyncio.run(_count_messages(temp_postgres, 300)) == 10


def test_sync_hits_max_pages_safety_cap(temp_postgres, db_config, stub_mcp_script, fixture_env):
    # 250 сообщений, лимит страницы 100 -> нужно 3 страницы на полную историю;
    # ограничиваем 2 страницами без since, чтобы точно упереться в потолок.
    job = SyncJobConfig(account_id="+79990001122", since=None, max_pages=2, chats=[ChatTarget(chat_id=100)])
    summary = asyncio.run(
        run_sync(job, _lazgram_config(stub_mcp_script), db_config=db_config, lazgram_extra_env=fixture_env)
    )

    result = summary.results[0]
    assert result.hit_max_pages is True
    assert result.messages_fetched == 200  # 2 страницы по 100


def test_sync_account_id_mismatch_warns(temp_postgres, db_config, stub_mcp_script, fixture_env):
    asyncio.run(_insert_dialog(temp_postgres, 999, "+70000000000", None))

    job = SyncJobConfig(account_id="+79990001122", since=None, chats=[ChatTarget(chat_id=200)])
    summary = asyncio.run(
        run_sync(job, _lazgram_config(stub_mcp_script), db_config=db_config, lazgram_extra_env=fixture_env)
    )

    assert summary.account_id_warning is not None
    assert "+79990001122" in summary.account_id_warning


def test_dry_run_does_not_write(temp_postgres, db_config, stub_mcp_script, fixture_env):
    job = SyncJobConfig(account_id="+79990001122", since=None, chats=[ChatTarget(chat_id=200)])
    summary = asyncio.run(
        run_sync(job, _lazgram_config(stub_mcp_script), dry_run=True, db_config=db_config, lazgram_extra_env=fixture_env)
    )

    assert summary.results[0].messages_fetched == 5  # посчитано, но не записано
    assert asyncio.run(_fetch_dialog(temp_postgres, 200)) is None
    assert asyncio.run(_count_messages(temp_postgres, 200)) == 0
