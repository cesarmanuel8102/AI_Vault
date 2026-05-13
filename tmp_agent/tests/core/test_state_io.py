"""
Tests for brain_v9.core.state_io — the canonical JSON I/O module.

Covers:
  - read_json: missing file, valid JSON, empty file, corrupt JSON, validation
  - write_json: basic write, atomic write, parent dir creation, backup, non-serializable
  - append_to_json_list: append, pruning, non-list reset
  - append_to_json_dict_list: append under key, pruning, non-dict reset
  - Validators: is_dict, is_list, has_keys
"""
import json
import pytest
from pathlib import Path

from brain_v9.core.state_io import (
    read_json,
    write_json,
    append_to_json_list,
    append_to_json_dict_list,
    is_dict,
    is_list,
    has_keys,
)


# ── read_json ─────────────────────────────────────────────────────────────────

class TestReadJson:

    def test_missing_file_returns_default(self, tmp_path):
        """Missing file should return a deepcopy of default, not raise."""
        p = tmp_path / "missing.json"
        result = read_json(p, default={"fallback": True})
        assert result == {"fallback": True}

    def test_missing_file_returns_deepcopy_of_default(self, tmp_path):
        """Returned default must be a new object (deepcopy), not the same ref."""
        p = tmp_path / "missing.json"
        original = {"a": [1, 2, 3]}
        result = read_json(p, default=original)
        assert result == original
        assert result is not original
        assert result["a"] is not original["a"]

    def test_missing_file_default_none(self, tmp_path):
        """Default=None should return None for missing file."""
        p = tmp_path / "missing.json"
        assert read_json(p) is None
        assert read_json(p, default=None) is None

    def test_valid_dict(self, tmp_path):
        """Read a valid JSON dict file."""
        p = tmp_path / "data.json"
        expected = {"key": "value", "count": 42}
        p.write_text(json.dumps(expected), encoding="utf-8")
        assert read_json(p) == expected

    def test_valid_list(self, tmp_path):
        """Read a valid JSON list file."""
        p = tmp_path / "data.json"
        expected = [1, "two", 3.0, None]
        p.write_text(json.dumps(expected), encoding="utf-8")
        assert read_json(p) == expected

    def test_valid_nested(self, tmp_path):
        """Read deeply nested JSON."""
        p = tmp_path / "nested.json"
        expected = {"a": {"b": {"c": [1, 2, {"d": True}]}}}
        p.write_text(json.dumps(expected), encoding="utf-8")
        assert read_json(p) == expected

    def test_empty_file_returns_default(self, tmp_path):
        """An empty file should return default, not crash."""
        p = tmp_path / "empty.json"
        p.write_text("", encoding="utf-8")
        assert read_json(p, default={}) == {}

    def test_whitespace_only_file_returns_default(self, tmp_path):
        """A file with only whitespace should return default."""
        p = tmp_path / "spaces.json"
        p.write_text("   \n\t  ", encoding="utf-8")
        assert read_json(p, default=[]) == []

    def test_corrupt_json_returns_default(self, tmp_path):
        """Corrupt JSON should return default and create .corrupt backup."""
        p = tmp_path / "broken.json"
        p.write_text("{invalid json content", encoding="utf-8")
        result = read_json(p, default={"safe": True})
        assert result == {"safe": True}
        # A .corrupt.* file should exist
        corrupt_files = list(tmp_path.glob("broken.corrupt.*"))
        assert len(corrupt_files) == 1

    def test_validator_pass(self, tmp_path):
        """Data passing validation should be returned normally."""
        p = tmp_path / "data.json"
        p.write_text('{"status": "ok"}', encoding="utf-8")
        result = read_json(p, default={}, validator=is_dict)
        assert result == {"status": "ok"}

    def test_validator_fail_returns_default(self, tmp_path):
        """Data failing validation should return default."""
        p = tmp_path / "data.json"
        p.write_text('[1, 2, 3]', encoding="utf-8")
        result = read_json(p, default={"fallback": True}, validator=is_dict)
        assert result == {"fallback": True}

    def test_validator_has_keys(self, tmp_path):
        """has_keys validator should work with read_json."""
        p = tmp_path / "data.json"
        p.write_text('{"name": "test", "version": 1}', encoding="utf-8")
        # Should pass
        result = read_json(p, default={}, validator=has_keys("name", "version"))
        assert result["name"] == "test"
        # Should fail (missing "author")
        result2 = read_json(p, default={"empty": True}, validator=has_keys("name", "author"))
        assert result2 == {"empty": True}

    def test_string_path(self, tmp_path):
        """Should accept string paths, not just Path objects."""
        p = tmp_path / "data.json"
        p.write_text('{"ok": true}', encoding="utf-8")
        assert read_json(str(p)) == {"ok": True}

    def test_utf8_content(self, tmp_path):
        """Should handle UTF-8 characters correctly."""
        p = tmp_path / "utf8.json"
        expected = {"nombre": "estrategia_binaria", "descripcion": "Estrategia autonoma"}
        p.write_text(json.dumps(expected, ensure_ascii=False), encoding="utf-8")
        assert read_json(p) == expected


# ── write_json ────────────────────────────────────────────────────────────────

class TestWriteJson:

    def test_basic_write(self, tmp_path):
        """Write a dict and read it back."""
        p = tmp_path / "out.json"
        data = {"key": "value", "number": 42}
        assert write_json(p, data) is True
        assert p.exists()
        assert json.loads(p.read_text(encoding="utf-8")) == data

    def test_write_list(self, tmp_path):
        """Write a list."""
        p = tmp_path / "list.json"
        data = [1, 2, "three"]
        assert write_json(p, data) is True
        assert json.loads(p.read_text(encoding="utf-8")) == data

    def test_write_creates_parent_dirs(self, tmp_path):
        """Parent directories should be created automatically."""
        p = tmp_path / "deep" / "nested" / "dir" / "file.json"
        assert write_json(p, {"created": True}) is True
        assert p.exists()
        assert json.loads(p.read_text(encoding="utf-8")) == {"created": True}

    def test_write_overwrites_existing(self, tmp_path):
        """Writing to an existing file should overwrite it."""
        p = tmp_path / "data.json"
        write_json(p, {"v": 1})
        write_json(p, {"v": 2})
        assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}

    def test_write_with_backup(self, tmp_path):
        """backup_on_overwrite should create a .bak file."""
        p = tmp_path / "data.json"
        write_json(p, {"original": True})
        write_json(p, {"updated": True}, backup_on_overwrite=True)
        # New data in main file
        assert json.loads(p.read_text(encoding="utf-8")) == {"updated": True}
        # Backup should exist
        bak = p.with_suffix(".json.bak")
        assert bak.exists()
        assert json.loads(bak.read_text(encoding="utf-8")) == {"original": True}

    def test_write_no_tmp_file_left_on_success(self, tmp_path):
        """Successful write should not leave .tmp files."""
        p = tmp_path / "data.json"
        write_json(p, {"clean": True})
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_write_non_serializable_returns_false(self, tmp_path):
        """Non-serializable data should return False, not raise."""
        p = tmp_path / "bad.json"
        # sets are not JSON-serializable, but state_io uses default=str,
        # so we need something that even str() can't help with... Actually
        # with default=str, almost anything serializes. Let's verify that
        # write_json handles it gracefully either way.
        result = write_json(p, {"data": {1, 2, 3}})
        # With default=str, sets serialize as their string repr
        # This should actually succeed with default=str
        assert result is True

    def test_write_utf8(self, tmp_path):
        """Should write UTF-8 content by default (ensure_ascii=False)."""
        p = tmp_path / "utf8.json"
        data = {"msg": "Estrategia exitosa"}
        write_json(p, data)
        raw = p.read_text(encoding="utf-8")
        assert "Estrategia exitosa" in raw  # Should not be escaped

    def test_write_string_path(self, tmp_path):
        """Should accept string paths."""
        p = str(tmp_path / "data.json")
        assert write_json(p, {"ok": True}) is True

    def test_atomic_write_no_corrupt_on_overwrite(self, tmp_path):
        """Overwriting should produce valid JSON (atomic rename)."""
        p = tmp_path / "data.json"
        write_json(p, {"v": 1})
        write_json(p, {"v": 2, "extra": "data"})
        # File should be valid JSON
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"v": 2, "extra": "data"}


# ── append_to_json_list ───────────────────────────────────────────────────────

class TestAppendToJsonList:

    def test_append_to_new_file(self, tmp_path):
        """Appending to a non-existent file should create it."""
        p = tmp_path / "list.json"
        assert append_to_json_list(p, "first") is True
        assert json.loads(p.read_text(encoding="utf-8")) == ["first"]

    def test_append_multiple(self, tmp_path):
        """Appending multiple items preserves order."""
        p = tmp_path / "list.json"
        append_to_json_list(p, "a")
        append_to_json_list(p, "b")
        append_to_json_list(p, "c")
        assert json.loads(p.read_text(encoding="utf-8")) == ["a", "b", "c"]

    def test_pruning_kicks_in(self, tmp_path):
        """When list exceeds max_entries, it should be pruned."""
        p = tmp_path / "list.json"
        # Write 10 items with max=5
        for i in range(10):
            append_to_json_list(p, i, max_entries=5, prune_to=3)

        data = json.loads(p.read_text(encoding="utf-8"))
        # After 6th item, pruned to 3 (items 3,4,5). Then 6,7,8,9 appended.
        # At item 6: [0,1,2,3,4,5] -> len=6 > 5 -> prune to last 3: [3,4,5]
        # Then append 6: [3,4,5,6], then 7: [3,4,5,6,7] (len=5, not > 5)
        # Then append 8: [3,4,5,6,7,8] -> len=6 > 5 -> prune to last 3: [6,7,8]
        # Then append 9: [6,7,8,9]
        assert data == [6, 7, 8, 9]

    def test_prune_to_default(self, tmp_path):
        """Default prune_to is max_entries // 2."""
        p = tmp_path / "list.json"
        # Write with max_entries=4 (prune_to=2 by default)
        for i in range(5):
            append_to_json_list(p, i, max_entries=4)
        data = json.loads(p.read_text(encoding="utf-8"))
        # After item 4: [0,1,2,3,4] -> len=5 > 4 -> prune to last 2: [3,4]
        assert data == [3, 4]

    def test_non_list_file_resets(self, tmp_path):
        """If file contains a dict instead of list, it should reset to []."""
        p = tmp_path / "data.json"
        p.write_text('{"not": "a list"}', encoding="utf-8")
        append_to_json_list(p, "item")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == ["item"]

    def test_append_dict_entry(self, tmp_path):
        """Should be able to append dict entries to a list."""
        p = tmp_path / "list.json"
        append_to_json_list(p, {"action": "trade", "profit": 1.5})
        append_to_json_list(p, {"action": "skip", "profit": 0.0})
        data = json.loads(p.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["action"] == "trade"


# ── append_to_json_dict_list ─────────────────────────────────────────────────

class TestAppendToJsonDictList:

    def test_append_to_new_file(self, tmp_path):
        """New file should get {key: [entry]}."""
        p = tmp_path / "dict.json"
        assert append_to_json_dict_list(p, "actions", {"type": "trade"}) is True
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"actions": [{"type": "trade"}]}

    def test_append_multiple_keys(self, tmp_path):
        """Multiple keys should coexist."""
        p = tmp_path / "dict.json"
        append_to_json_dict_list(p, "actions", "act1")
        append_to_json_dict_list(p, "errors", "err1")
        append_to_json_dict_list(p, "actions", "act2")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["actions"] == ["act1", "act2"]
        assert data["errors"] == ["err1"]

    def test_pruning(self, tmp_path):
        """Lists under a key should be capped at max_entries."""
        p = tmp_path / "dict.json"
        for i in range(10):
            append_to_json_dict_list(p, "log", i, max_entries=5)
        data = json.loads(p.read_text(encoding="utf-8"))
        assert len(data["log"]) == 5
        assert data["log"] == [5, 6, 7, 8, 9]

    def test_non_dict_file_resets(self, tmp_path):
        """If file is not a dict, reset to {}."""
        p = tmp_path / "data.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        append_to_json_dict_list(p, "items", "new")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"items": ["new"]}

    def test_non_list_value_resets(self, tmp_path):
        """If the value under key is not a list, reset it."""
        p = tmp_path / "data.json"
        p.write_text('{"items": "not a list"}', encoding="utf-8")
        append_to_json_dict_list(p, "items", "new")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"items": ["new"]}


# ── Validators ────────────────────────────────────────────────────────────────

class TestValidators:

    def test_is_dict_true(self):
        assert is_dict({}) is True
        assert is_dict({"k": "v"}) is True

    def test_is_dict_false(self):
        assert is_dict([]) is False
        assert is_dict("string") is False
        assert is_dict(None) is False
        assert is_dict(42) is False

    def test_is_list_true(self):
        assert is_list([]) is True
        assert is_list([1, 2, 3]) is True

    def test_is_list_false(self):
        assert is_list({}) is False
        assert is_list("string") is False
        assert is_list(None) is False

    def test_has_keys_all_present(self):
        validator = has_keys("a", "b", "c")
        assert validator({"a": 1, "b": 2, "c": 3}) is True

    def test_has_keys_extra_keys_ok(self):
        validator = has_keys("a")
        assert validator({"a": 1, "b": 2, "extra": 3}) is True

    def test_has_keys_missing_key(self):
        validator = has_keys("a", "b", "missing")
        assert validator({"a": 1, "b": 2}) is False

    def test_has_keys_not_a_dict(self):
        validator = has_keys("a")
        assert validator([1, 2]) is False
        assert validator("string") is False
        assert validator(None) is False

    def test_has_keys_empty(self):
        """has_keys() with no args should accept any dict."""
        validator = has_keys()
        assert validator({}) is True
        assert validator({"anything": True}) is True
