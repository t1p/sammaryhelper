import datetime

import pytest

from lazgram_sync.config import SyncJobConfig


def test_requires_account_id():
    with pytest.raises(ValueError, match="account_id"):
        SyncJobConfig.from_dict({"chats": [{"chat_id": 1}]})


def test_requires_nonempty_chats():
    with pytest.raises(ValueError, match="chats"):
        SyncJobConfig.from_dict({"account_id": "+79990001122", "chats": []})


def test_global_since_applied_to_chats_without_override():
    job = SyncJobConfig.from_dict(
        {
            "account_id": "+79990001122",
            "since": "2026-09-01T00:00:00",
            "chats": [{"chat_id": 1}, {"chat_id": 2, "since": "2026-09-10T00:00:00"}],
        }
    )
    assert job.chats[0].since == datetime.datetime(2026, 9, 1)
    assert job.chats[1].since == datetime.datetime(2026, 9, 10)


def test_default_max_pages():
    job = SyncJobConfig.from_dict({"account_id": "x", "chats": [{"username": "foo"}]})
    assert job.max_pages == 200
    assert job.chats[0].username == "foo"
    assert job.chats[0].chat_id is None


def test_load_file(tmp_path):
    import json

    path = tmp_path / "chats.json"
    path.write_text(json.dumps({"account_id": "+7999", "chats": [{"chat_id": 42}]}), encoding="utf-8")
    job = SyncJobConfig.load_file(str(path))
    assert job.account_id == "+7999"
    assert job.chats[0].chat_id == 42
