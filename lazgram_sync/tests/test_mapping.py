import datetime

from lazgram_sync.mapping import build_dialog, build_message, build_placeholder_dialog, map_chat_type


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
