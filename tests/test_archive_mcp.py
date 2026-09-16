"""Юнит-тесты MCP-сервера tg-archive (фаза B задания tg-archive-mcp).

Тесты normalize_chat_type / parse_accounts / resolve_account_id / resolve_chat
(на фейковом слое БД) работают в любом venv — db.py не зависит от пакета
`mcp`. Тест _freshness импортирует server.py, которому пакет `mcp` нужен —
пропускается, если его нет (в рабочем venv/ Sammaryhelper его нет намеренно,
см. TASK-tg-archive-mcp.md §4).

Интеграционные тесты против живой БД не входят в этот файл — они
отдельным маркером не в дефолтном прогоне (см. TASK-tg-archive-mcp.md B7).
"""

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_archive_server.db import (
    ArchiveDB,
    normalize_chat_type,
    parse_accounts,
    resolve_account_id,
)


# --- normalize_chat_type ---------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        ("channel", "Канал"),
        ("Канал", "Канал"),
        ("group", "Чат"),
        ("chat", "Чат"),
        ("Чат", "Чат"),
        ("private", "Личка"),
        ("dm", "Личка"),
        ("Личка", "Личка"),
        (" Channel ", "Канал"),
        (None, None),
        ("", None),
        ("unknown_type", "unknown_type"),
    ],
)
def test_normalize_chat_type(value, expected):
    assert normalize_chat_type(value) == expected


# --- parse_accounts ---------------------------------------------------------

def test_parse_accounts_single():
    assert parse_accounts("prod:79253010707") == {"prod": "79253010707"}


def test_parse_accounts_multiple():
    assert parse_accounts("prod:79253010707,test:111") == {
        "prod": "79253010707",
        "test": "111",
    }


def test_parse_accounts_empty():
    assert parse_accounts(None) == {}
    assert parse_accounts("") == {}


def test_parse_accounts_whitespace():
    assert parse_accounts(" prod : 79253010707 , test:111 ") == {
        "prod": "79253010707",
        "test": "111",
    }


def test_parse_accounts_invalid_entry():
    with pytest.raises(ValueError):
        parse_accounts("prod-no-colon")


# --- resolve_account_id ------------------------------------------------------

def test_resolve_account_id_known_alias():
    accounts = {"prod": "79253010707"}
    assert resolve_account_id("prod", accounts) == "79253010707"


def test_resolve_account_id_raw_digits_passthrough():
    accounts = {"prod": "79253010707"}
    assert resolve_account_id("79253010707", accounts) == "79253010707"


def test_resolve_account_id_none():
    assert resolve_account_id(None, {}) is None


def test_resolve_account_id_unknown_alias_raises():
    accounts = {"prod": "79253010707"}
    with pytest.raises(ValueError):
        resolve_account_id("staging", accounts)


def test_resolve_account_id_unknown_alias_no_accounts_configured_raises():
    with pytest.raises(ValueError):
        resolve_account_id("prod", {})


# --- ArchiveDB.resolve_chat (порядок разрешения, фейковый пул) --------------

class _FakeConn:
    """Возвращает заранее заданные строки по номеру вызова fetch()."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def fetch(self, *_args, **_kwargs):
        response = self._responses[self.calls] if self.calls < len(self._responses) else []
        self.calls += 1
        return response


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquireCtx(self._conn)


def _db_with_responses(responses):
    db = ArchiveDB.__new__(ArchiveDB)  # без реального connect()
    db.pool = _FakePool(_FakeConn(responses))
    return db


@pytest.mark.asyncio
async def test_resolve_chat_matches_by_id_first():
    row = {"chat_id": -1001372152834, "title": "StoicStrategy"}
    db = _db_with_responses([[row]])  # первый вызов fetch (шаг id) — сразу успех
    candidates = await db.resolve_chat("-1001372152834", "79253010707")
    assert len(candidates) == 1
    assert candidates[0]["match_kind"] == "id"
    assert candidates[0]["unambiguous"] is True


@pytest.mark.asyncio
async def test_resolve_chat_falls_through_to_username():
    row = {"chat_id": 1, "username": "someuser"}
    # шаг id: query не число -> шаг id пропускается кодом без похода в БД,
    # поэтому первый реальный fetch — это шаг username.
    db = _db_with_responses([[row]])
    candidates = await db.resolve_chat("@someuser", "79253010707")
    assert candidates[0]["match_kind"] == "username"


@pytest.mark.asyncio
async def test_resolve_chat_falls_through_to_alias_exact():
    # id -> [] , username -> [] , alias_exact -> [row]
    row = {"chat_id": 2, "title_archive": "Старое имя"}
    db = _db_with_responses([[], [row]])
    candidates = await db.resolve_chat("Старое имя", "79253010707")
    assert candidates[0]["match_kind"] == "alias_exact"


@pytest.mark.asyncio
async def test_resolve_chat_falls_through_to_title_ilike():
    # id -> [], username -> [], alias_exact -> [], title_ilike -> [row]
    row = {"chat_id": 3, "title_archive": "СтоицизмЧат"}
    db = _db_with_responses([[], [], [row]])
    candidates = await db.resolve_chat("стоицизм", "79253010707")
    assert candidates[0]["match_kind"] == "title_ilike"


@pytest.mark.asyncio
async def test_resolve_chat_multiple_candidates_not_unambiguous():
    rows = [{"chat_id": 1}, {"chat_id": 2}]
    db = _db_with_responses([[], [], rows])
    candidates = await db.resolve_chat("чат", "79253010707")
    assert len(candidates) == 2
    assert all("unambiguous" not in c for c in candidates)


# --- get_recent_messages: честное coverage ----------------------------------

@pytest.mark.asyncio
async def test_get_recent_messages_coverage_none_when_dialog_has_no_messages():
    db = ArchiveDB.__new__(ArchiveDB)

    class _Conn:
        async def fetch(self, *_a, **_k):
            return []

        async def fetchval(self, *_a, **_k):
            return False

    db.pool = _FakePool(_Conn())
    result = await db.get_recent_messages(dialog_id=999, account_id=None, limit=20)
    assert result["coverage"] == "none"
    assert result["messages"] == []
    assert "hint" in result


@pytest.mark.asyncio
async def test_get_recent_messages_coverage_partial_when_rows_exist():
    row = {"id": 1, "text": "hi"}
    db = ArchiveDB.__new__(ArchiveDB)

    class _Conn:
        async def fetch(self, *_a, **_k):
            return [row]

    db.pool = _FakePool(_Conn())
    result = await db.get_recent_messages(dialog_id=1, account_id=None, limit=20)
    assert result["coverage"] == "partial"
    assert result["messages"] == [row]


# --- _freshness (server.py, требует пакет mcp) -------------------------------

mcp_pkg = pytest.importorskip(
    "mcp", reason="пакет mcp ставится в отдельный .venv-archive-mcp (фаза C), не в venv/"
)


def test_freshness_honest_model_not_boolean():
    from mcp_archive_server.server import _freshness

    old = datetime.datetime.now() - datetime.timedelta(days=436)
    result = _freshness(old)
    assert "is_stale" not in result
    assert result["source"] == "archive"
    assert result["age_days"] == 436
    assert result["confidence"]["messages"] == "partial"
    assert result["confidence"]["chat_id"] == "high"


def test_freshness_none_updated_at():
    from mcp_archive_server.server import _freshness

    result = _freshness(None)
    assert result["snapshot_date"] is None
    assert result["confidence"]["messages"] == "partial"
