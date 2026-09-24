import datetime
import json

from fastgpt_exporter.mapping import build_item, build_items


def _row(**overrides):
    base = {
        "id": 100,
        "name": "Тестовый чат",
        "type": "Чат",
        "folder_id": 1,
        "account_id": "+7999",
        "data": json.dumps({"folder": {"id": 1, "title": "Работа"}}),
        "updated_at": datetime.datetime(2026, 9, 15, 19, 31, 9),
        "messages_count": 2,
        "oldest": datetime.datetime(2026, 9, 15, 18, 31, 9),
        "newest": datetime.datetime(2026, 9, 15, 19, 31, 9),
    }
    base.update(overrides)
    return base


def test_channel_with_folder():
    item = build_item(_row(type="Канал"))
    assert 'Чат: "Тестовый чат"' in item["q"]
    assert "Тип: канал (Канал)" in item["q"]
    assert "Папка: Работа" in item["q"]
    assert "Сообщений в архиве: 2" in item["q"]
    assert "2026-09-15T18:31:09 — 2026-09-15T19:31:09" in item["q"]
    assert item["a"] == ""
    assert item["metadata"]["dialog_id"] == 100


def test_group_without_folder():
    item = build_item(_row(type="Чат", data=json.dumps({"folder": None})))
    assert "Тип: группа/чат (Чат)" in item["q"]
    assert "Папка: без папки" in item["q"]


def test_private_dialog_no_messages():
    item = build_item(_row(type="Личка", messages_count=0, oldest=None, newest=None))
    assert "Тип: личный диалог (Личка)" in item["q"]
    assert "Сообщений в архиве: 0" in item["q"]
    assert "сообщений нет" in item["q"]


def test_unparseable_data_defaults_to_no_folder():
    item = build_item(_row(data="not json"))
    assert "Папка: без папки" in item["q"]


def test_build_items_maps_all_rows():
    items = build_items([_row(id=1), _row(id=2)])
    assert len(items) == 2
    assert items[0]["metadata"]["dialog_id"] == 1
    assert items[1]["metadata"]["dialog_id"] == 2
