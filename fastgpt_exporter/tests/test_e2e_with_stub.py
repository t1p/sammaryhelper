"""Сквозные сценарии: реальный (временный) Postgres + локальный стаб FastGPT."""

from __future__ import annotations

import asyncio
import os

import pytest

from mcp_archive_server.db import ArchiveConfig
from fastgpt_exporter.config import FastGPTConfig
from fastgpt_exporter.exporter import run_export


def _db_config(temp_postgres) -> ArchiveConfig:
    return ArchiveConfig(**temp_postgres)


def _fastgpt_config(stub_fastgpt, state_file, **overrides) -> FastGPTConfig:
    base = dict(
        base_url=stub_fastgpt.base_url,
        api_key="test-key",
        vector_model_id="text-embedding-3-small",
        state_file=str(state_file),
    )
    base.update(overrides)
    return FastGPTConfig(**base)


def test_dry_run_makes_zero_http_calls(temp_postgres, stub_fastgpt, tmp_path):
    fastgpt_config = _fastgpt_config(stub_fastgpt, tmp_path / "state.json", dry_run=True)
    summary = asyncio.run(run_export(_db_config(temp_postgres), fastgpt_config))

    assert stub_fastgpt.calls == []
    assert summary.total_dialogs == 4
    assert summary.by_type == {"Чат": 2, "Канал": 1, "Личка": 1}
    assert summary.dry_run is True


def test_first_run_creates_dataset_and_collection(temp_postgres, stub_fastgpt, tmp_path):
    state_file = tmp_path / "state.json"
    fastgpt_config = _fastgpt_config(stub_fastgpt, state_file)
    summary = asyncio.run(run_export(_db_config(temp_postgres), fastgpt_config))

    assert len(stub_fastgpt.calls_to("/api/core/dataset/create")) == 1
    assert len(stub_fastgpt.calls_to("/api/core/dataset/collection/create")) == 1
    assert not any(c["method"] == "DELETE" for c in stub_fastgpt.calls)
    push_calls = stub_fastgpt.calls_to("/api/core/dataset/data/pushData")
    assert len(push_calls) == 1
    assert len(push_calls[0]["body"]["data"]) == 4
    assert summary.pushed == 4
    assert os.path.exists(state_file)


def test_second_run_reuses_dataset_and_recreates_collection(temp_postgres, stub_fastgpt, tmp_path):
    state_file = tmp_path / "state.json"
    fastgpt_config = _fastgpt_config(stub_fastgpt, state_file)

    first = asyncio.run(run_export(_db_config(temp_postgres), fastgpt_config))
    second = asyncio.run(run_export(_db_config(temp_postgres), fastgpt_config))

    assert len(stub_fastgpt.calls_to("/api/core/dataset/create")) == 1  # не вызывается повторно
    assert len(stub_fastgpt.calls_to("/api/core/dataset/collection/create")) == 2
    delete_calls = [c for c in stub_fastgpt.calls if c["method"] == "DELETE"]
    assert len(delete_calls) == 1
    assert delete_calls[0]["query"]["id"] == [first.collection_id]
    assert second.dataset_id == first.dataset_id
    assert second.collection_id != first.collection_id


def test_delete_failure_is_graceful(temp_postgres, stub_fastgpt, tmp_path):
    state_file = tmp_path / "state.json"
    fastgpt_config = _fastgpt_config(stub_fastgpt, state_file)

    asyncio.run(run_export(_db_config(temp_postgres), fastgpt_config))
    stub_fastgpt.fail_delete = True
    second = asyncio.run(run_export(_db_config(temp_postgres), fastgpt_config))

    assert second.collection_id is not None
    assert second.pushed == 4


def test_batching_across_many_dialogs(temp_postgres, stub_fastgpt, tmp_path):
    db_config = _db_config(temp_postgres)

    async def seed_many():
        from mcp_archive_server.db import ArchiveDB

        db = ArchiveDB(db_config)
        await db.connect()
        async with db.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO dialogs (id, name, type, account_id, data)
                VALUES ($1, $2, 'Чат', '+79990001122', '{}')
                """,
                [(1000 + i, f"Синтетический чат {i}", ) for i in range(450)],
            )
        await db.close()

    asyncio.run(seed_many())

    fastgpt_config = _fastgpt_config(stub_fastgpt, tmp_path / "state.json")
    summary = asyncio.run(run_export(db_config, fastgpt_config))

    push_calls = stub_fastgpt.calls_to("/api/core/dataset/data/pushData")
    assert [len(c["body"]["data"]) for c in push_calls] == [200, 200, 54]
    assert summary.pushed == 454


def test_account_filter(temp_postgres, stub_fastgpt, tmp_path):
    fastgpt_config = _fastgpt_config(stub_fastgpt, tmp_path / "state.json")
    summary = asyncio.run(
        run_export(_db_config(temp_postgres), fastgpt_config, account_id="+70001112233")
    )

    assert summary.total_dialogs == 1
    push_calls = stub_fastgpt.calls_to("/api/core/dataset/data/pushData")
    assert len(push_calls[0]["body"]["data"]) == 1
    assert 'Второй аккаунт чат' in push_calls[0]["body"]["data"][0]["q"]
