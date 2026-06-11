import json
import os
import pytest
from unittest.mock import patch
import config as cfgmod  # aliased: several tests use a local var named `config` (the config dict)
from config import load_history, save_history


class TestLoadHistory:
    """History file loading - resilience and correctness."""

    def test_returns_empty_list_when_file_absent(self, history_file):
        cfgmod.HISTORY_FILE = history_file + "_nonexistent"
        assert load_history() == []

    def test_returns_empty_list_on_corrupt_json(self, history_file):
        with open(history_file, "w") as f:
            f.write("not valid json {{{{")
        cfgmod.HISTORY_FILE = history_file
        assert load_history() == []

    def test_returns_empty_list_on_empty_json_array(self, history_file):
        with open(history_file, "w") as f:
            json.dump([], f)
        cfgmod.HISTORY_FILE = history_file
        assert load_history() == []

    def test_returns_correct_data_from_valid_file(self, history_file):
        data = [{"id": "abc123", "fingerprint": "title|company", "date": "2026-05-18"}]
        with open(history_file, "w") as f:
            json.dump(data, f)
        cfgmod.HISTORY_FILE = history_file
        result = load_history()
        assert result == data
        assert result[0]["id"] == "abc123"

    def test_returns_empty_list_on_oserror(self, history_file):
        cfgmod.HISTORY_FILE = history_file
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            with patch("os.path.exists", return_value=True):
                result = load_history()
        assert result == []

    def teardown_method(self):
        cfgmod.HISTORY_FILE = "job_history.json"


class TestSaveHistory:
    """History persistence - capping and data integrity."""

    def test_saves_history_correctly(self, history_file, save_config):
        cfgmod.HISTORY_FILE = history_file
        data = [{"id": f"id{i}", "fingerprint": f"fp{i}", "date": "2026-05-18"} for i in range(5)]
        save_history(data, save_config)
        with open(history_file) as f:
            result = json.load(f)
        assert result == data

    def test_trims_to_max_history_limit(self, history_file):
        cfgmod.HISTORY_FILE = history_file
        config = {"search": {"max_history": 3}}
        data = [{"id": f"id{i}", "fingerprint": f"fp{i}", "date": "2026-05-18"} for i in range(10)]
        save_history(data, config)
        with open(history_file) as f:
            result = json.load(f)
        assert len(result) == 3

    def test_keeps_newest_entries_when_trimming(self, history_file):
        cfgmod.HISTORY_FILE = history_file
        config = {"search": {"max_history": 3}}
        data = [{"id": f"id{i}", "fingerprint": f"fp{i}", "date": "2026-05-18"} for i in range(10)]
        save_history(data, config)
        with open(history_file) as f:
            result = json.load(f)
        # Should keep the LAST 3 (newest), not the first 3
        assert result[0]["id"] == "id7"
        assert result[-1]["id"] == "id9"

    def test_default_max_history_is_2000(self, history_file):
        cfgmod.HISTORY_FILE = history_file
        config = {"search": {}}  # no max_history key
        data = [{"id": f"id{i}", "fingerprint": f"fp{i}", "date": "2026-05-18"} for i in range(10)]
        save_history(data, config)
        with open(history_file) as f:
            result = json.load(f)
        assert len(result) == 10  # under 2000, all preserved

    def teardown_method(self):
        cfgmod.HISTORY_FILE = "job_history.json"
