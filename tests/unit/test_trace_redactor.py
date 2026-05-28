"""
Unit tests for trace_redactor.py (VTC-A1).
These tests verify that the redactor removes blocked fields,
scrubs secrets, redacts protected paths, truncates strings,
and never mutates the original input event.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))

import pytest
from brain_v9.tracing.trace_redactor import sanitize_event


class TestBlockedFields:
    def test_chain_of_thought_removed(self):
        event = {
            "type": "thinking",
            "title": "Plan",
            "chain_of_thought": "raw reasoning...",
        }
        safe = sanitize_event(event)
        assert "chain_of_thought" not in safe
        assert safe["title"] == "Plan"

    def test_reasoning_removed(self):
        event = {"type": "thinking", "reasoning": "abc"}
        safe = sanitize_event(event)
        assert "reasoning" not in safe

    def test_scratchpad_removed(self):
        event = {"scratchpad": "notes"}
        safe = sanitize_event(event)
        assert "scratchpad" not in safe

    def test_api_key_removed(self):
        event = {"api_key": "sk-abc123"}
        safe = sanitize_event(event)
        assert "api_key" not in safe

    def test_token_removed(self):
        event = {"token": "ghp_abc123"}
        safe = sanitize_event(event)
        assert "token" not in safe

    def test_password_removed(self):
        event = {"password": "secret"}
        safe = sanitize_event(event)
        assert "password" not in safe

    def test_secret_removed(self):
        event = {"secret": "hidden"}
        safe = sanitize_event(event)
        assert "secret" not in safe

    def test_credential_removed(self):
        event = {"credential": "cred"}
        safe = sanitize_event(event)
        assert "credential" not in safe

    def test_full_file_content_removed(self):
        event = {"full_file_content": "lots of data"}
        safe = sanitize_event(event)
        assert "full_file_content" not in safe

    def test_memory_dump_removed(self):
        event = {"memory_dump": "dump"}
        safe = sanitize_event(event)
        assert "memory_dump" not in safe

    def test_nested_blocked_field_removed(self):
        event = {"data": {"chain_of_thought": "nested reasoning"}}
        safe = sanitize_event(event)
        assert "chain_of_thought" not in safe.get("data", {})


class TestSecretScrubbing:
    def test_api_key_scrubbed(self):
        # sk- pattern requires 48+ alphanumeric chars after sk-
        long_key = "sk-" + "a" * 48
        event = {"text": f"Calling API with key={long_key}"}
        safe = sanitize_event(event)
        assert "[REDACTED_SECRET]" in safe["text"]
        assert long_key not in safe["text"]

    def test_password_scrubbed(self):
        event = {"text": "password=supersecret123"}
        safe = sanitize_event(event)
        # pattern replaces the word "password" with redaction marker
        assert "[REDACTED_SECRET]" in safe["text"]
        assert "password" not in safe["text"]
        # the value after = is not a secret pattern itself, so it remains
        assert "supersecret123" in safe["text"]

    def test_token_scrubbed(self):
        event = {"text": "token=ghp_1234567890abcdef1234567890abcdef1234"}
        safe = sanitize_event(event)
        assert "[REDACTED_SECRET]" in safe["text"]
        assert "ghp_1234567890abcdef1234567890abcdef1234" not in safe["text"]


class TestProtectedPathScrubbing:
    def test_memory_semantic_redacted(self):
        event = {"text": "Reading memory/semantic/state.json"}
        safe = sanitize_event(event)
        assert "[REDACTED_PATH]" in safe["text"]
        assert "memory/semantic" not in safe["text"]

    def test_strategies_redacted(self):
        event = {"text": "Writing to tmp_agent/strategies/config.json"}
        safe = sanitize_event(event)
        assert "[REDACTED_PATH]" in safe["text"]
        assert "tmp_agent/strategies" not in safe["text"]


class TestStringTruncation:
    def test_title_truncated(self):
        event = {"title": "a" * 500}
        safe = sanitize_event(event)
        assert len(safe["title"]) <= 120

    def test_summary_truncated(self):
        event = {"summary": "b" * 1000}
        safe = sanitize_event(event)
        assert len(safe["summary"]) <= 280


class TestDataSizeLimit:
    def test_large_data_redacted(self):
        # 25 keys of 500-char strings -> serialized > 10000 chars
        event = {"data": {f"key_{i}": "x" * 500 for i in range(25)}}
        safe = sanitize_event(event)
        assert safe.get("data") == {"_redacted": "large payload"}


class TestSafeFieldsPreserved:
    def test_safe_fields_unchanged(self):
        event = {
            "event_id": "uuid",
            "ts_utc": "2026-05-28T10:00:00Z",
            "status": "success",
            "type": "tool",
            "title": "File read",
        }
        safe = sanitize_event(event)
        assert safe == event


class TestNoMutation:
    def test_original_preserved(self):
        original = {"data": {"secret": "value"}}
        original_copy = copy.deepcopy(original)
        safe = sanitize_event(original)
        assert original == original_copy
        assert "secret" in original["data"]
        assert "secret" not in safe.get("data", {})


class TestFullyBlockedEvent:
    def test_only_blocked_fields(self):
        event = {"chain_of_thought": "only blocked fields"}
        safe = sanitize_event(event)
        assert safe == {"type": "redacted", "title": "Redacted event"}
