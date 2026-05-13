"""
Tests for brain_v9.core.memory — MemoryManager v3 (LLM Summarisation).

Covers:
  - save / get_context round-trip (async)
  - Persistence via state_io (load after re-create)
  - clear short / long / all
  - Long-term cap at MAX_LONG_TERM_ENTRIES
  - Short-term deque cap at MAX_SHORT_TERM
  - Snapshot summary triggered every 20 messages (fallback: no LLM)
  - Snapshot summary with LLM (mocked)
  - _build_summary_prompt formatting
  - LLM failure graceful degradation
  - Malformed data on disk handled gracefully
"""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from brain_v9.core.memory import (
    MemoryManager,
    MAX_SHORT_TERM,
    MAX_LONG_TERM_ENTRIES,
    _SUMMARY_WINDOW,
    _SUMMARY_MSG_MAX_CHARS,
)


# ── Basic save / get_context ──────────────────────────────────────────────────

class TestSaveAndContext:

    @pytest.mark.asyncio
    async def test_save_and_get_context(self, isolated_base_path):
        mm = MemoryManager("test_session")
        await mm.save({"role": "user", "content": "hello"})
        await mm.save({"role": "assistant", "content": "hi there"})

        ctx = mm.get_context()
        assert len(ctx) == 2
        assert ctx[0] == {"role": "user", "content": "hello"}
        assert ctx[1] == {"role": "assistant", "content": "hi there"}

    @pytest.mark.asyncio
    async def test_save_adds_timestamp(self, isolated_base_path):
        mm = MemoryManager("ts_session")
        msg = {"role": "user", "content": "test"}
        await mm.save(msg)
        assert "timestamp" in msg

    @pytest.mark.asyncio
    async def test_save_preserves_existing_timestamp(self, isolated_base_path):
        mm = MemoryManager("ts2")
        msg = {"role": "user", "content": "test", "timestamp": "2026-01-01T00:00:00"}
        await mm.save(msg)
        assert msg["timestamp"] == "2026-01-01T00:00:00"

    def test_get_context_skips_invalid_messages(self, isolated_base_path):
        mm = MemoryManager("skip_test")
        mm.short_term.append({"role": "user", "content": "good"})
        mm.short_term.append({"bad": "no role or content"})
        mm.short_term.append({"role": "assistant", "content": "also good"})

        ctx = mm.get_context()
        assert len(ctx) == 2
        assert ctx[0]["content"] == "good"
        assert ctx[1]["content"] == "also good"

    @pytest.mark.asyncio
    async def test_message_count_increments(self, isolated_base_path):
        mm = MemoryManager("count_test")
        assert mm.message_count == 0
        await mm.save({"role": "user", "content": "1"})
        await mm.save({"role": "user", "content": "2"})
        assert mm.message_count == 2


# ── Persistence ───────────────────────────────────────────────────────────────

class TestPersistence:

    @pytest.mark.asyncio
    async def test_data_persists_across_instances(self, isolated_base_path):
        """Saving in one instance should be loadable in a new instance."""
        mm1 = MemoryManager("persist_test")
        await mm1.save({"role": "user", "content": "remember me"})
        await mm1.save({"role": "assistant", "content": "I will"})

        mm2 = MemoryManager("persist_test")
        ctx = mm2.get_context()
        assert len(ctx) == 2
        assert ctx[0]["content"] == "remember me"
        assert mm2.message_count == 2

    @pytest.mark.asyncio
    async def test_short_term_file_exists(self, isolated_base_path):
        mm = MemoryManager("file_check")
        await mm.save({"role": "user", "content": "test"})
        p = mm._path("short_term")
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "messages" in data
        assert data["count"] == 1


# ── Clear ─────────────────────────────────────────────────────────────────────

class TestClear:

    @pytest.mark.asyncio
    async def test_clear_short(self, isolated_base_path):
        mm = MemoryManager("clear_s")
        await mm.save({"role": "user", "content": "msg"})
        mm.long_term.append({"note": "keep me"})
        mm.clear("short")

        assert len(mm.short_term) == 0
        assert mm.message_count == 0
        assert len(mm.long_term) == 1  # untouched

    @pytest.mark.asyncio
    async def test_clear_long(self, isolated_base_path):
        mm = MemoryManager("clear_l")
        await mm.save({"role": "user", "content": "msg"})
        mm.long_term.append({"note": "remove me"})
        mm.clear("long")

        assert len(mm.short_term) == 1  # untouched
        assert len(mm.long_term) == 0

    @pytest.mark.asyncio
    async def test_clear_all(self, isolated_base_path):
        mm = MemoryManager("clear_a")
        await mm.save({"role": "user", "content": "msg"})
        mm.long_term.append({"note": "bye"})
        mm.clear("all")

        assert len(mm.short_term) == 0
        assert len(mm.long_term) == 0
        assert mm.message_count == 0

    @pytest.mark.asyncio
    async def test_clear_persists(self, isolated_base_path):
        """After clear, a new instance should also be empty."""
        mm1 = MemoryManager("clear_persist")
        await mm1.save({"role": "user", "content": "msg"})
        mm1.clear("all")

        mm2 = MemoryManager("clear_persist")
        assert len(mm2.short_term) == 0
        assert mm2.message_count == 0


# ── Short-term deque cap ─────────────────────────────────────────────────────

class TestShortTermCap:

    @pytest.mark.asyncio
    async def test_short_term_capped_at_max(self, isolated_base_path):
        mm = MemoryManager("cap_test")
        for i in range(MAX_SHORT_TERM + 20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        assert len(mm.short_term) == MAX_SHORT_TERM
        # Oldest messages dropped, newest retained
        ctx = mm.get_context()
        assert ctx[-1]["content"] == f"msg-{MAX_SHORT_TERM + 19}"


# ── Long-term cap ────────────────────────────────────────────────────────────

class TestLongTermCap:

    def test_long_term_capped_on_load(self, isolated_base_path):
        """If long_term.json has > MAX entries, loading caps it."""
        mm = MemoryManager("lt_cap")
        # Manually write too many entries
        from brain_v9.core.state_io import write_json
        big_list = [{"n": i} for i in range(MAX_LONG_TERM_ENTRIES + 30)]
        write_json(mm._path("long_term"), big_list)

        mm2 = MemoryManager("lt_cap")
        assert len(mm2.long_term) == MAX_LONG_TERM_ENTRIES


# ── Snapshot summary (no LLM — fallback) ─────────────────────────────────────

class TestSnapshotSummaryFallback:

    @pytest.mark.asyncio
    async def test_snapshot_triggered_at_20_messages(self, isolated_base_path):
        mm = MemoryManager("snap_test")
        assert len(mm.long_term) == 0

        for i in range(20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        # After 20 messages, one snapshot should have been created
        assert len(mm.long_term) == 1
        snap = mm.long_term[0]
        assert "timestamp" in snap
        assert snap["message_count"] == 20
        assert snap["source"] == "fallback"
        assert "note" in snap

    @pytest.mark.asyncio
    async def test_snapshot_resets_counter(self, isolated_base_path):
        mm = MemoryManager("snap_reset")
        for i in range(20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        assert mm.messages_since_summary == 0

    @pytest.mark.asyncio
    async def test_multiple_snapshots(self, isolated_base_path):
        mm = MemoryManager("snap_multi")
        for i in range(45):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        # 45 messages = 2 snapshots (at 20 and 40), counter at 5
        assert len(mm.long_term) == 2
        assert mm.messages_since_summary == 5


# ── Snapshot summary (with LLM) ──────────────────────────────────────────────

class TestSnapshotSummaryLLM:

    @pytest.mark.asyncio
    async def test_llm_summary_stored_when_available(self, isolated_base_path):
        """When LLM returns a summary, it should be stored with source='llm'."""
        mm = MemoryManager("llm_snap")
        mock_llm = MagicMock()
        mock_llm.query = AsyncMock(return_value={
            "success": True,
            "content": "User discussed trading strategies and dashboard setup.",
        })
        mm.set_llm(mock_llm)

        for i in range(20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        assert len(mm.long_term) == 1
        snap = mm.long_term[0]
        assert snap["source"] == "llm"
        assert snap["summary"] == "User discussed trading strategies and dashboard setup."
        assert "note" not in snap  # no fallback note

    @pytest.mark.asyncio
    async def test_llm_called_with_chat_priority(self, isolated_base_path):
        """LLM query should use the 'chat' model priority for summarization."""
        mm = MemoryManager("llm_priority")
        mock_llm = MagicMock()
        mock_llm.query = AsyncMock(return_value={
            "success": True,
            "content": "Summary of conversation.",
        })
        mm.set_llm(mock_llm)

        for i in range(20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        mock_llm.query.assert_called_once()
        call_kwargs = mock_llm.query.call_args
        assert call_kwargs[1]["model_priority"] == "chat"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_metadata(self, isolated_base_path):
        """When LLM fails, should produce a fallback metadata-only snapshot."""
        mm = MemoryManager("llm_fail")
        mock_llm = MagicMock()
        mock_llm.query = AsyncMock(return_value={
            "success": False,
            "content": None,
        })
        mm.set_llm(mock_llm)

        for i in range(20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        assert len(mm.long_term) == 1
        snap = mm.long_term[0]
        assert snap["source"] == "fallback"
        assert "note" in snap
        assert "summary" not in snap

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back_gracefully(self, isolated_base_path):
        """If LLM raises an exception, should degrade to fallback."""
        mm = MemoryManager("llm_exc")
        mock_llm = MagicMock()
        mock_llm.query = AsyncMock(side_effect=ConnectionError("Ollama down"))
        mm.set_llm(mock_llm)

        for i in range(20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        assert len(mm.long_term) == 1
        snap = mm.long_term[0]
        assert snap["source"] == "fallback"

    @pytest.mark.asyncio
    async def test_llm_empty_response_falls_back(self, isolated_base_path):
        """Short/empty LLM responses should be treated as failure."""
        mm = MemoryManager("llm_empty")
        mock_llm = MagicMock()
        mock_llm.query = AsyncMock(return_value={
            "success": True,
            "content": "OK",  # too short (<10 chars)
        })
        mm.set_llm(mock_llm)

        for i in range(20):
            await mm.save({"role": "user", "content": f"msg-{i}"})

        snap = mm.long_term[0]
        assert snap["source"] == "fallback"


# ── _build_summary_prompt ────────────────────────────────────────────────────

class TestBuildSummaryPrompt:

    def test_basic_prompt_format(self):
        messages = [
            {"role": "user", "content": "What is my U score?"},
            {"role": "assistant", "content": "Your current U score is 0.42."},
        ]
        prompt = MemoryManager._build_summary_prompt(messages)
        assert "Summarise" in prompt
        assert "[user] What is my U score?" in prompt
        assert "[assistant] Your current U score is 0.42." in prompt
        assert "SUMMARY:" in prompt

    def test_long_messages_truncated(self):
        long_content = "x" * 1000
        messages = [{"role": "user", "content": long_content}]
        prompt = MemoryManager._build_summary_prompt(messages)
        assert "..." in prompt
        # Should not contain full 1000 chars
        assert long_content not in prompt
        # Should contain truncated portion
        assert "x" * _SUMMARY_MSG_MAX_CHARS in prompt

    def test_window_limits_messages(self):
        """Only last _SUMMARY_WINDOW messages should appear in prompt."""
        messages = [
            {"role": "user", "content": f"msg-{i}"}
            for i in range(30)
        ]
        prompt = MemoryManager._build_summary_prompt(messages)
        # First messages should NOT be in prompt (outside window)
        assert "msg-0" not in prompt
        assert "msg-9" not in prompt
        # Last messages should be in prompt
        assert "msg-29" in prompt
        assert f"msg-{30 - _SUMMARY_WINDOW}" in prompt

    def test_missing_role_uses_question_mark(self):
        messages = [{"content": "no role here"}]
        prompt = MemoryManager._build_summary_prompt(messages)
        assert "[?]" in prompt

    def test_empty_messages_returns_prompt_shell(self):
        prompt = MemoryManager._build_summary_prompt([])
        assert "Summarise" in prompt
        assert "SUMMARY:" in prompt


# ── set_llm ──────────────────────────────────────────────────────────────────

class TestSetLlm:

    def test_set_llm_stores_reference(self, isolated_base_path):
        mm = MemoryManager("llm_ref")
        mock_llm = MagicMock()
        mm.set_llm(mock_llm)
        assert mm._llm is mock_llm

    def test_no_llm_by_default(self, isolated_base_path):
        mm = MemoryManager("no_llm")
        assert mm._llm is None


# ── Malformed data on disk ────────────────────────────────────────────────────

class TestMalformedData:

    def test_corrupt_short_term_json(self, isolated_base_path):
        """Corrupt short_term.json should not crash, just start empty."""
        mm = MemoryManager("corrupt_test")
        p = mm._path("short_term")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("NOT VALID JSON {{{{", encoding="utf-8")

        mm2 = MemoryManager("corrupt_test")
        assert len(mm2.short_term) == 0
        assert mm2.message_count == 0

    def test_short_term_is_not_dict(self, isolated_base_path):
        """If short_term.json is a list instead of dict, start empty."""
        mm = MemoryManager("wrong_type")
        p = mm._path("short_term")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        mm2 = MemoryManager("wrong_type")
        assert len(mm2.short_term) == 0

    def test_long_term_is_not_list(self, isolated_base_path):
        """If long_term.json is a dict instead of list, start empty."""
        mm = MemoryManager("lt_wrong")
        p = mm._path("long_term")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"wrong": "type"}), encoding="utf-8")

        mm2 = MemoryManager("lt_wrong")
        assert len(mm2.long_term) == 0
