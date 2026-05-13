"""
Tests for brain_v9.core.llm — LLMManager v3.

Covers:
  - Token estimation (estimate_tokens, estimate_messages_tokens)
  - _fmt_tools helper
  - _update_latency running average
  - get_metrics (returns copy)
  - __init__ defaults
  - _ollama: dynamic num_ctx, message formatting, error handling
  - query: fallback chain traversal, skip cloud without internet, metrics
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from aiohttp import ClientConnectorError

from brain_v9.core.llm import LLMManager, CHAINS, MODELS


# ── Token Estimation ──────────────────────────────────────────────────────────

class TestEstimateTokens:

    def test_empty_string_returns_zero(self):
        assert LLMManager.estimate_tokens("") == 0

    def test_none_returns_zero(self):
        assert LLMManager.estimate_tokens(None) == 0

    def test_short_string(self):
        # "hello" = 5 chars -> int(5/3.0)+1 = 2
        assert LLMManager.estimate_tokens("hello") == 2

    def test_longer_string(self):
        text = "a" * 300
        result = LLMManager.estimate_tokens(text)
        # int(300/3.0)+1 = 101
        assert result == 101

    def test_scales_with_length(self):
        short = LLMManager.estimate_tokens("abc")
        long = LLMManager.estimate_tokens("abc" * 100)
        assert long > short

    def test_always_positive_for_nonempty(self):
        # Even a single char: int(1/3.0)+1 = 1
        assert LLMManager.estimate_tokens("x") >= 1

    def test_uses_chars_per_token_constant(self):
        text = "a" * 30
        expected = int(30 / LLMManager.CHARS_PER_TOKEN) + 1
        assert LLMManager.estimate_tokens(text) == expected


class TestEstimateMessagesTokens:

    def test_empty_list_returns_zero(self):
        assert LLMManager.estimate_messages_tokens([]) == 0

    def test_single_message_includes_overhead(self):
        msgs = [{"role": "user", "content": "hi"}]
        result = LLMManager.estimate_messages_tokens(msgs)
        content_tokens = LLMManager.estimate_tokens("hi")
        assert result == 4 + content_tokens

    def test_multiple_messages_accumulate(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        result = LLMManager.estimate_messages_tokens(msgs)
        expected = (4 + LLMManager.estimate_tokens("hello")) + \
                   (4 + LLMManager.estimate_tokens("world"))
        assert result == expected

    def test_missing_content_uses_empty(self):
        msgs = [{"role": "user"}]
        result = LLMManager.estimate_messages_tokens(msgs)
        # 4 overhead + estimate_tokens("") = 4 + 0 = 4
        assert result == 4

    def test_empty_content_still_counts_overhead(self):
        msgs = [{"role": "user", "content": ""}]
        result = LLMManager.estimate_messages_tokens(msgs)
        assert result == 4


# ── _fmt_tools ────────────────────────────────────────────────────────────────

class TestFmtTools:

    def setup_method(self):
        self.llm = LLMManager()

    def test_none_returns_empty(self):
        assert self.llm._fmt_tools(None) == ""

    def test_empty_dict_returns_empty(self):
        assert self.llm._fmt_tools({}) == ""

    def test_empty_tools_list(self):
        ctx = {"available_tools": []}
        result = self.llm._fmt_tools(ctx)
        assert "HERRAMIENTAS:" in result

    def test_single_tool(self):
        ctx = {"available_tools": [
            {"name": "read_file", "description": "Read a file from disk"}
        ]}
        result = self.llm._fmt_tools(ctx)
        assert "HERRAMIENTAS:" in result
        assert "read_file" in result
        assert "Read a file from disk" in result

    def test_multiple_tools(self):
        ctx = {"available_tools": [
            {"name": "tool_a", "description": "Desc A"},
            {"name": "tool_b", "description": "Desc B"},
        ]}
        result = self.llm._fmt_tools(ctx)
        assert "tool_a" in result
        assert "tool_b" in result

    def test_tool_missing_description(self):
        ctx = {"available_tools": [
            {"name": "no_desc_tool"}
        ]}
        result = self.llm._fmt_tools(ctx)
        assert "no_desc_tool" in result


# ── _update_latency ───────────────────────────────────────────────────────────

class TestUpdateLatency:

    def setup_method(self):
        self.llm = LLMManager()

    def test_first_call_sets_directly(self):
        self.llm.metrics["success"] = 1
        self.llm._update_latency(2.5)
        assert self.llm.metrics["avg_latency"] == 2.5

    def test_running_average_second_call(self):
        self.llm.metrics["success"] = 1
        self.llm._update_latency(2.0)
        self.llm.metrics["success"] = 2
        self.llm._update_latency(4.0)
        # avg = (2.0 * 1 + 4.0) / 2 = 3.0
        assert self.llm.metrics["avg_latency"] == pytest.approx(3.0)

    def test_running_average_three_calls(self):
        self.llm.metrics["success"] = 1
        self.llm._update_latency(1.0)
        self.llm.metrics["success"] = 2
        self.llm._update_latency(2.0)
        self.llm.metrics["success"] = 3
        self.llm._update_latency(3.0)
        # After 3: avg = (1.5 * 2 + 3.0) / 3 = 6.0/3 = 2.0
        assert self.llm.metrics["avg_latency"] == pytest.approx(2.0)


# ── get_metrics ───────────────────────────────────────────────────────────────

class TestGetMetrics:

    def test_returns_copy(self):
        llm = LLMManager()
        m = llm.get_metrics()
        m["total"] = 999
        assert llm.metrics["total"] == 0  # original unchanged

    def test_has_all_keys(self):
        llm = LLMManager()
        m = llm.get_metrics()
        for key in ("total", "success", "failed", "fallbacks", "avg_latency"):
            assert key in m


# ── __init__ defaults ─────────────────────────────────────────────────────────

class TestInit:

    def test_session_starts_none(self):
        llm = LLMManager()
        assert llm.session is None

    def test_internet_starts_none(self):
        llm = LLMManager()
        assert llm._internet is None

    def test_metrics_all_zero(self):
        llm = LLMManager()
        assert llm.metrics["total"] == 0
        assert llm.metrics["success"] == 0
        assert llm.metrics["failed"] == 0
        assert llm.metrics["fallbacks"] == 0
        assert llm.metrics["avg_latency"] == 0.0


# ── _OLLAMA_LIMITS ────────────────────────────────────────────────────────────

class TestOllamaLimits:

    def test_known_models_have_limits(self):
        for model_name in ("llama3.1:8b", "deepseek-r1:14b", "qwen2.5-coder:14b"):
            lim = LLMManager._OLLAMA_LIMITS[model_name]
            assert "num_predict" in lim
            assert "num_ctx" in lim
            assert "max_num_ctx" in lim

    def test_max_num_ctx_gte_num_ctx(self):
        for model_name, lim in LLMManager._OLLAMA_LIMITS.items():
            assert lim["max_num_ctx"] >= lim["num_ctx"], f"{model_name}"

    def test_default_limits_exist(self):
        d = LLMManager._OLLAMA_LIMITS_DEFAULT
        assert d["num_predict"] > 0
        assert d["num_ctx"] > 0
        assert d["max_num_ctx"] >= d["num_ctx"]


# ── _ollama: message formatting + dynamic num_ctx ─────────────────────────────

class TestOllamaMethod:

    @pytest.fixture
    def llm(self):
        return LLMManager()

    def _make_mock_response(self, content="test response", status=200):
        """Create a mock aiohttp response for /api/chat."""
        resp = AsyncMock()
        resp.status = status
        resp.json = AsyncMock(return_value={
            "message": {"role": "assistant", "content": content}
        })
        resp.text = AsyncMock(return_value="error text")
        # Support async context manager
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    def _make_mock_session(self, mock_response):
        """Create a mock aiohttp ClientSession that returns mock_response on post."""
        session = MagicMock()
        session.post = MagicMock(return_value=mock_response)
        session.closed = False
        return session

    @pytest.mark.asyncio
    async def test_system_message_prepended(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], None)

        # Inspect the JSON payload
        call_args = mock_session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        messages = payload["messages"]
        assert messages[0]["role"] == "system"
        assert "Brain V9" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_user_messages_forwarded(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        await llm._ollama(
            "llama3.1:8b", 30,
            [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}],
            None,
        )

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        messages = payload["messages"]
        # system + user + assistant = 3
        assert len(messages) == 3
        assert messages[1] == {"role": "user", "content": "hello"}
        assert messages[2] == {"role": "assistant", "content": "world"}

    @pytest.mark.asyncio
    async def test_invalid_roles_filtered_out(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        await llm._ollama(
            "llama3.1:8b", 30,
            [
                {"role": "user", "content": "a"},
                {"role": "tool", "content": "b"},      # invalid
                {"role": "function", "content": "c"},   # invalid
                {"role": "assistant", "content": "d"},
            ],
            None,
        )

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        messages = payload["messages"]
        roles = [m["role"] for m in messages]
        assert "tool" not in roles
        assert "function" not in roles
        assert len(messages) == 3  # system + user + assistant

    @pytest.mark.asyncio
    async def test_tools_context_injected_in_system(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        tools = {"available_tools": [{"name": "my_tool", "description": "does stuff"}]}
        await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], tools)

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        system_msg = payload["messages"][0]["content"]
        assert "HERRAMIENTAS:" in system_msg
        assert "my_tool" in system_msg

    @pytest.mark.asyncio
    async def test_dynamic_num_ctx_stays_at_base_for_small_prompt(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        # Small prompt: just "hi" — should stay at base_ctx (8192 for llama3.1:8b)
        await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], None)

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        num_ctx = payload["options"]["num_ctx"]
        assert num_ctx == 8192  # base_ctx for llama3.1:8b

    @pytest.mark.asyncio
    async def test_dynamic_num_ctx_expands_for_large_prompt(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        # Huge prompt that should force expansion.
        # llama3.1:8b: num_predict=4096, base_ctx=8192, max_num_ctx=16384
        # Need estimated_input + 4096 + 128 > 8192, so estimated_input > 3968
        # At 3.0 chars/token, need > 3968*3 = 11904 chars
        big_message = "x" * 15000
        await llm._ollama(
            "llama3.1:8b", 30,
            [{"role": "user", "content": big_message}],
            None,
        )

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        num_ctx = payload["options"]["num_ctx"]
        assert num_ctx > 8192  # expanded beyond base
        assert num_ctx <= 16384  # but not beyond max

    @pytest.mark.asyncio
    async def test_dynamic_num_ctx_capped_at_max(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        # Enormous prompt that would need more than max_num_ctx
        # deepseek-r1:14b: num_predict=2048, max_num_ctx=8192
        enormous = "x" * 100000
        await llm._ollama(
            "deepseek-r1:14b", 120,
            [{"role": "user", "content": enormous}],
            None,
        )

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        num_ctx = payload["options"]["num_ctx"]
        assert num_ctx == 8192  # capped at max_num_ctx

    @pytest.mark.asyncio
    async def test_unknown_model_uses_default_limits(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        await llm._ollama("some-unknown-model:7b", 30, [{"role": "user", "content": "hi"}], None)

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        # Default limits: num_ctx=4096, num_predict=2048
        assert payload["options"]["num_ctx"] == LLMManager._OLLAMA_LIMITS_DEFAULT["num_ctx"]
        assert payload["options"]["num_predict"] == LLMManager._OLLAMA_LIMITS_DEFAULT["num_predict"]

    @pytest.mark.asyncio
    async def test_num_predict_in_payload(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], None)

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        assert payload["options"]["num_predict"] == 4096  # llama3.1:8b limit

    @pytest.mark.asyncio
    async def test_stream_is_false(self, llm):
        mock_resp = self._make_mock_response("ok")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], None)

        payload = mock_session.post.call_args.kwargs.get("json") or \
                  mock_session.post.call_args[1].get("json")
        assert payload["stream"] is False

    @pytest.mark.asyncio
    async def test_returns_content_string(self, llm):
        mock_resp = self._make_mock_response("Hello there!")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        result = await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], None)
        assert result == "Hello there!"

    @pytest.mark.asyncio
    async def test_non_200_raises_runtime_error(self, llm):
        mock_resp = self._make_mock_response(status=500)
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        with pytest.raises(RuntimeError, match="Ollama HTTP 500"):
            await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], None)

    @pytest.mark.asyncio
    async def test_empty_response_raises_runtime_error(self, llm):
        mock_resp = self._make_mock_response(content="")
        mock_session = self._make_mock_session(mock_resp)
        llm._get_session = AsyncMock(return_value=mock_session)

        with pytest.raises(RuntimeError, match="vacia"):
            await llm._ollama("llama3.1:8b", 30, [{"role": "user", "content": "hi"}], None)


# ── query: fallback chain ─────────────────────────────────────────────────────

class TestQueryFallback:

    @pytest.fixture
    def llm(self):
        return LLMManager()

    @pytest.mark.asyncio
    async def test_success_on_first_model(self, llm):
        llm._has_internet = AsyncMock(return_value=True)
        llm._query_model = AsyncMock(return_value={
            "success": True, "content": "ok", "response": "ok",
            "model": "llama3.1:8b", "model_used": "llama3.1:8b",
        })

        result = await llm.query([{"role": "user", "content": "hi"}], model_priority="chat")
        assert result["success"] is True
        assert result["fallback"] is False
        assert result["model_key"] == "llama8b"  # first in chat chain
        assert llm.metrics["fallbacks"] == 0

    @pytest.mark.asyncio
    async def test_fallback_increments_on_second_model(self, llm):
        llm._has_internet = AsyncMock(return_value=True)

        call_count = 0
        async def side_effect(cfg, msgs, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return {
                "success": True, "content": "ok", "response": "ok",
                "model": cfg.get("model", ""), "model_used": cfg.get("model", ""),
            }

        llm._query_model = AsyncMock(side_effect=side_effect)

        result = await llm.query([{"role": "user", "content": "hi"}], model_priority="chat")
        assert result["success"] is True
        assert result["fallback"] is True
        assert llm.metrics["fallbacks"] == 1

    @pytest.mark.asyncio
    async def test_skips_cloud_without_internet(self, llm):
        llm._has_internet = AsyncMock(return_value=False)

        models_called = []
        async def track_calls(cfg, msgs, tools):
            models_called.append(cfg.get("model", cfg.get("type", "")))
            return {
                "success": True, "content": "ok", "response": "ok",
                "model": cfg.get("model", ""), "model_used": cfg.get("model", ""),
            }

        llm._query_model = AsyncMock(side_effect=track_calls)

        # "chat" chain: llama8b (local), kimi_cloud (cloud), deepseek14b (local)
        result = await llm.query([{"role": "user", "content": "hi"}], model_priority="chat")
        assert result["success"] is True
        # kimi_cloud should be skipped (not local, no internet)
        for m in models_called:
            assert "kimi" not in m

    @pytest.mark.asyncio
    async def test_all_models_fail_returns_error(self, llm):
        llm._has_internet = AsyncMock(return_value=True)
        llm._query_model = AsyncMock(side_effect=Exception("boom"))

        result = await llm.query([{"role": "user", "content": "hi"}], model_priority="offline")
        assert result["success"] is False
        assert result["content"] is None
        assert llm.metrics["failed"] == 1

    @pytest.mark.asyncio
    async def test_connector_error_triggers_fallback(self, llm):
        llm._has_internet = AsyncMock(return_value=True)

        call_count = 0
        async def side_effect(cfg, msgs, tools):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ClientConnectorError(
                    connection_key=MagicMock(), os_error=OSError("Connection refused")
                )
            return {
                "success": True, "content": "ok", "response": "ok",
                "model": cfg.get("model", ""), "model_used": cfg.get("model", ""),
            }

        llm._query_model = AsyncMock(side_effect=side_effect)

        result = await llm.query([{"role": "user", "content": "hi"}], model_priority="offline")
        assert result["success"] is True
        assert llm.metrics["fallbacks"] >= 1

    @pytest.mark.asyncio
    async def test_unknown_priority_uses_ollama_chain(self, llm):
        llm._has_internet = AsyncMock(return_value=True)

        models_called = []
        async def track_calls(cfg, msgs, tools):
            models_called.append(cfg.get("model", ""))
            return {
                "success": True, "content": "ok", "response": "ok",
                "model": cfg.get("model", ""), "model_used": cfg.get("model", ""),
            }

        llm._query_model = AsyncMock(side_effect=track_calls)

        result = await llm.query(
            [{"role": "user", "content": "hi"}],
            model_priority="nonexistent_chain",
        )
        assert result["success"] is True
        # Should use "ollama" chain (default), first model = llama8b
        assert result["model_key"] == "llama8b"

    @pytest.mark.asyncio
    async def test_metrics_total_increments(self, llm):
        llm._has_internet = AsyncMock(return_value=True)
        llm._query_model = AsyncMock(return_value={
            "success": True, "content": "ok", "response": "ok",
            "model": "test", "model_used": "test",
        })

        assert llm.metrics["total"] == 0
        await llm.query([{"role": "user", "content": "hi"}])
        assert llm.metrics["total"] == 1
        await llm.query([{"role": "user", "content": "bye"}])
        assert llm.metrics["total"] == 2

    @pytest.mark.asyncio
    async def test_success_includes_latency(self, llm):
        llm._has_internet = AsyncMock(return_value=True)
        llm._query_model = AsyncMock(return_value={
            "success": True, "content": "ok", "response": "ok",
            "model": "test", "model_used": "test",
        })

        result = await llm.query([{"role": "user", "content": "hi"}])
        assert "latency" in result
        assert result["latency"] >= 0


# ── CHAINS / MODELS config ───────────────────────────────────────────────────

class TestChainsConfig:

    def test_all_chain_models_exist(self):
        """Every model key in every chain should exist in MODELS."""
        for chain_name, keys in CHAINS.items():
            for key in keys:
                assert key in MODELS, f"{key} in chain '{chain_name}' not in MODELS"

    def test_agent_chain_starts_with_llama(self):
        # Reordered for 6GB VRAM — llama8b is fastest (usually warm)
        assert CHAINS["agent"][0] == "llama8b"
        assert "deepseek14b" in CHAINS["agent"]  # still available as fallback

    def test_chat_chain_starts_with_llama(self):
        assert CHAINS["chat"][0] == "llama8b"

    def test_offline_chain_only_local(self):
        for key in CHAINS["offline"]:
            assert MODELS[key]["local"] is True, f"{key} is not local"

    def test_every_model_has_type(self):
        for key, cfg in MODELS.items():
            assert "type" in cfg, f"{key} missing type"
            assert "timeout" in cfg, f"{key} missing timeout"
            assert "local" in cfg, f"{key} missing local"


# ── close ─────────────────────────────────────────────────────────────────────

class TestClose:

    @pytest.mark.asyncio
    async def test_close_with_no_session(self):
        llm = LLMManager()
        # Should not raise
        await llm.close()

    @pytest.mark.asyncio
    async def test_close_closes_session(self):
        llm = LLMManager()
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        llm.session = mock_session

        await llm.close()
        mock_session.close.assert_awaited_once()
