import json
import os

from fastgpt_exporter.state import ExportState, load_state, save_state


def test_missing_file_returns_empty_state(tmp_path):
    state = load_state(str(tmp_path / "does_not_exist.json"))
    assert state == ExportState()


def test_round_trip(tmp_path):
    path = str(tmp_path / "state.json")
    original = ExportState(dataset_id="ds1", collection_id="col1", last_item_count=5)
    save_state(path, original)
    loaded = load_state(path)
    assert loaded == original


def test_corrupted_file_returns_empty_state_not_crash(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not valid json", encoding="utf-8")
    state = load_state(str(path))
    assert state == ExportState()


def test_atomic_write_leaves_no_tmp_file(tmp_path):
    path = str(tmp_path / "state.json")
    save_state(path, ExportState(dataset_id="ds1"))
    assert os.path.exists(path)
    assert not os.path.exists(f"{path}.tmp")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["dataset_id"] == "ds1"
