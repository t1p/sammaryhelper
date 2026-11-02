import datetime

from lazgram_sync.mapping import (
    build_dialog,
    build_message,
    build_placeholder_dialog,
    build_tg_map_chat,
    build_tg_map_chat_alias,
    build_tg_map_message,
    map_chat_type,
)


def test_type_mapping():
    assert map_chat_type("channel") == "Канал"
    assert map_chat_type("supergroup") == "Канал"
    assert map_chat_type("group") == "Чат"
    assert map_chat_type("private") == "Личка"
    assert map_chat_type("unknown_type") == "unknown_type"


def test_build_dialog_without_existing_folder():
    chat = {"id": 100, "type": "channel", "title": "Мой канал", "username": "mychannel"}
    dialog = build_dialog(chat)
    assert dialog["id"] == 100
    assert dialog["name"] == "Мой канал"
    assert dialog["type"] == "Канал"
    assert dialog["folder"] is None
    assert dialog["source"] == "lazgram"


def test_build_dialog_preserves_existing_folder():
    chat = {"id": 100, "type": "group", "title": "Группа"}
    dialog = build_dialog(chat, existing_folder={"id": 1, "title": "Работа"})
    assert dialog["folder"] == {"id": 1, "title": "Работа"}
    assert dialog["type"] == "Чат"


def test_build_dialog_missing_title_falls_back_to_id():
    chat = {"id": 555, "type": "private"}
    dialog = build_dialog(chat)
    assert dialog["name"] == "Chat 555"


def test_build_placeholder_dialog():
    dialog = build_placeholder_dialog(999, existing_folder=None)
    assert dialog["id"] == 999
    assert dialog["incomplete"] is True
    assert dialog["name"] == "Chat 999"


def test_build_message_converts_epoch_date():
    msg = {
        "id": 5,
        "chatId": 100,
        "senderId": 12345,
        "date": 1893456000,  # 2030-01-01T00:00:00Z
        "text": "hello",
        "replyToMessageId": 4,
        "isOutgoing": True,
        "hasAttachment": False,
    }
    mapped = build_message(msg)
    assert mapped["id"] == 5
    assert mapped["sender_id"] == 12345
    assert mapped["sender_name"] == "12345"
    assert mapped["text"] == "hello"
    assert isinstance(mapped["date"], datetime.datetime)
    assert mapped["date"].year == 2030
    assert mapped["message_thread_id"] is None
    assert mapped["reply_to_message_id"] == 4
    assert mapped["is_outgoing"] is True


# ===== Тесты для tg_map маппингов =====


def test_build_tg_map_chat():
    chat = {"id": -1001234567890, "type": "channel", "title": "Новости", "username": "news"}
    row = build_tg_map_chat(chat, account_key="igor")
    assert row["account_key"] == "igor"
    assert row["chat_id"] == -1001234567890
    assert row["chat_type"] == "channel"
    assert row["username"] == "news"
    assert row["title_live"] == "Новости"
    assert row["source"] == "lazgram"
    assert row["is_live"] is True


def test_build_tg_map_chat_alias_with_title_and_username():
    chat = {"id": 100, "type": "group", "title": "Рабочая группа", "username": "workgroup"}
    aliases = build_tg_map_chat_alias(chat, account_key="igor")
    assert len(aliases) == 2
    # Проверяем, что оба алиаса добавлены
    alias_values = {a["alias"] for a in aliases}
    assert "Рабочая группа" in alias_values
    assert "workgroup" in alias_values
    # Все алиасы должны быть для одного чата
    for alias in aliases:
        assert alias["account_key"] == "igor"
        assert alias["chat_id"] == 100
        assert alias["source"] == "lazgram"


def test_build_tg_map_chat_alias_with_title_only():
    chat = {"id": 101, "type": "private", "title": "Личный чат"}
    aliases = build_tg_map_chat_alias(chat, account_key="igor")
    assert len(aliases) == 1
    assert aliases[0]["alias"] == "Личный чат"


def test_build_tg_map_chat_alias_with_username_only():
    chat = {"id": 102, "type": "channel", "username": "testchannel"}
    aliases = build_tg_map_chat_alias(chat, account_key="igor")
    assert len(aliases) == 1
    assert aliases[0]["alias"] == "testchannel"


def test_build_tg_map_chat_alias_empty_when_no_names():
    chat = {"id": 103, "type": "group"}
    aliases = build_tg_map_chat_alias(chat, account_key="igor")
    assert len(aliases) == 0


def test_build_tg_map_message():
    msg = {
        "id": 12345,
        "senderId": 987654,
        "text": "Test message",
        "date": 1893456000,
    }
    row = build_tg_map_message(msg, chat_id=100, account_key="igor")
    assert row["account_key"] == "igor"
    assert row["chat_id"] == 100
    assert row["message_id"] == 12345
    assert row["sender_id"] == 987654
    assert row["text"] == "Test message"
    assert isinstance(row["sent_at"], datetime.datetime)
    assert row["sent_at"].year == 2030
    assert row["raw_json"] == msg
