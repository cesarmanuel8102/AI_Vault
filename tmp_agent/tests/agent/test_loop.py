"""
Tests for brain_v9.agent.loop — Phase 2.4 (Hybrid Agent Tool Calling).

Covers:
  - _extract_json: direct parse, markdown fences, brace-matching, invalid input
  - _parse_reasoning: valid JSON, partial JSON, garbage input
  - _get_model_limits: known chains, unknown chains, default fallback
  - ToolExecutor.get_compact_catalog: grouping by category, empty executor
  - ToolExecutor basic operations: register, list_tools, execute, descriptions
  - _verify: enhanced heuristic verification (P3-07)
"""
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock

from brain_v9.agent.loop import AgentLoop, ToolExecutor, ReasoningResult, ActionResult


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_executor(*tools) -> ToolExecutor:
    """Create a ToolExecutor with the given (name, description, category) tuples."""
    ex = ToolExecutor()
    for name, desc, cat in tools:
        ex.register(name, lambda: None, desc, cat)
    return ex


# ═══════════════════════════════════════════════════════════════════════════════
# _extract_json
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractJson:
    """Tests for AgentLoop._extract_json static method."""

    def test_direct_parse_dict(self):
        text = '{"thought": "hello", "plan": []}'
        result = AgentLoop._extract_json(text)
        assert result == {"thought": "hello", "plan": []}

    def test_direct_parse_nested(self):
        text = '{"tool_calls": [{"tool": "check_port", "args": {"port": 8090}}]}'
        result = AgentLoop._extract_json(text)
        assert result["tool_calls"][0]["tool"] == "check_port"

    def test_markdown_json_fence(self):
        text = '```json\n{"thought": "analyzing", "plan": ["step1"]}\n```'
        result = AgentLoop._extract_json(text)
        assert result is not None
        assert result["thought"] == "analyzing"

    def test_markdown_plain_fence(self):
        text = '```\n{"thought": "test"}\n```'
        result = AgentLoop._extract_json(text)
        assert result is not None
        assert result["thought"] == "test"

    def test_text_before_json(self):
        text = 'Let me think about this...\n{"thought": "done", "plan": []}'
        result = AgentLoop._extract_json(text)
        assert result is not None
        assert result["thought"] == "done"

    def test_text_after_json(self):
        text = '{"thought": "answer", "plan": []}\nHope that helps!'
        result = AgentLoop._extract_json(text)
        assert result is not None
        assert result["thought"] == "answer"

    def test_brace_matching_with_nested_braces(self):
        text = 'Preamble {"a": {"b": {"c": 1}}, "d": 2} epilogue'
        result = AgentLoop._extract_json(text)
        assert result is not None
        assert result["a"]["b"]["c"] == 1
        assert result["d"] == 2

    def test_no_json_returns_none(self):
        result = AgentLoop._extract_json("No JSON here, just plain text")
        assert result is None

    def test_empty_string_returns_none(self):
        result = AgentLoop._extract_json("")
        assert result is None

    def test_invalid_json_in_braces_returns_none(self):
        result = AgentLoop._extract_json("{this is not valid json at all}")
        assert result is None

    def test_whitespace_around_json(self):
        text = '   \n  {"key": "value"}  \n  '
        result = AgentLoop._extract_json(text)
        assert result == {"key": "value"}

    def test_multiple_fences_picks_json_one(self):
        text = '```python\nprint("hi")\n```\n```json\n{"found": true}\n```'
        result = AgentLoop._extract_json(text)
        assert result is not None
        assert result["found"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_reasoning
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseReasoning:
    """Tests for AgentLoop._parse_reasoning instance method."""

    def setup_method(self):
        llm_mock = MagicMock()
        self.loop = AgentLoop(llm=llm_mock, tools=ToolExecutor())

    def test_valid_json_full_fields(self):
        content = json.dumps({
            "thought": "Need to check port",
            "plan": ["step1", "step2"],
            "tool_calls": [{"tool": "check_port", "args": {"port": 8090}}],
            "confidence": 0.9,
            "needs_clarification": False,
        })
        result = self.loop._parse_reasoning(content)
        assert isinstance(result, ReasoningResult)
        assert result.thought == "Need to check port"
        assert len(result.plan) == 2
        assert len(result.tool_calls) == 1
        assert result.confidence == 0.9
        assert result.needs_clarification is False

    def test_partial_json_uses_defaults(self):
        content = '{"thought": "just thinking"}'
        result = self.loop._parse_reasoning(content)
        assert result.thought == "just thinking"
        assert result.plan == []
        assert result.tool_calls == []
        assert result.confidence == 0.7  # default
        assert result.needs_clarification is False

    def test_garbage_input_fallback(self):
        content = "I can't generate proper JSON right now, sorry about that."
        result = self.loop._parse_reasoning(content)
        assert result.confidence == 0.3  # low-confidence fallback
        assert result.tool_calls == []
        assert result.plan == []
        assert len(result.thought) > 0  # contains the raw text

    def test_markdown_wrapped_json(self):
        content = '```json\n{"thought": "via markdown", "confidence": 0.8}\n```'
        result = self.loop._parse_reasoning(content)
        assert result.thought == "via markdown"
        assert result.confidence == 0.8

    def test_needs_clarification_true(self):
        content = json.dumps({
            "thought": "Not enough info",
            "plan": [],
            "tool_calls": [],
            "confidence": 0.2,
            "needs_clarification": True,
        })
        result = self.loop._parse_reasoning(content)
        assert result.needs_clarification is True

    def test_confidence_coerced_to_float(self):
        content = '{"thought": "test", "confidence": "0.85"}'
        result = self.loop._parse_reasoning(content)
        assert result.confidence == 0.85
        assert isinstance(result.confidence, float)


# ═══════════════════════════════════════════════════════════════════════════════
# _get_model_limits
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetModelLimits:
    """Tests for AgentLoop._get_model_limits static method."""

    def test_agent_chain_returns_deepseek_limits(self):
        limits = AgentLoop._get_model_limits("agent")
        # agent chain first ollama model is llama8b -> llama3.1:8b (reordered for 6GB VRAM)
        assert limits["max_num_ctx"] == 16384
        assert limits["num_predict"] == 4096

    def test_chat_chain_returns_llama_limits(self):
        limits = AgentLoop._get_model_limits("chat")
        # chat chain first ollama model is llama8b -> llama3.1:8b
        assert limits["max_num_ctx"] == 16384
        assert limits["num_predict"] == 4096

    def test_code_chain_returns_coder_limits(self):
        limits = AgentLoop._get_model_limits("code")
        # code chain first ollama model is coder14b -> qwen2.5-coder:14b
        assert limits["max_num_ctx"] == 8192
        assert limits["num_predict"] == 2048

    def test_unknown_chain_uses_default(self):
        limits = AgentLoop._get_model_limits("nonexistent_chain")
        # falls back to CHAINS["ollama"] -> llama8b
        assert limits["max_num_ctx"] == 16384  # llama8b limits

    def test_returns_dict_with_required_keys(self):
        limits = AgentLoop._get_model_limits("agent")
        assert "num_predict" in limits
        assert "num_ctx" in limits
        assert "max_num_ctx" in limits


# ═══════════════════════════════════════════════════════════════════════════════
# ToolExecutor.get_compact_catalog
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetCompactCatalog:
    """Tests for ToolExecutor.get_compact_catalog method."""

    def test_empty_executor_returns_empty(self):
        ex = ToolExecutor()
        assert ex.get_compact_catalog() == ""

    def test_single_category(self):
        ex = _make_executor(
            ("read_file", "Read a file", "filesystem"),
            ("write_file", "Write a file", "filesystem"),
        )
        catalog = ex.get_compact_catalog()
        assert "[FILESYSTEM]" in catalog
        assert "read_file" in catalog
        assert "write_file" in catalog
        # New format: header line + one line per tool (with signature)
        assert "read_file(" in catalog and "Read a file" in catalog
        assert "write_file(" in catalog and "Write a file" in catalog

    def test_multiple_categories_sorted(self):
        ex = _make_executor(
            ("check_port", "Check port", "system"),
            ("read_file", "Read file", "filesystem"),
            ("analyze_python", "Analyze Python", "code"),
        )
        catalog = ex.get_compact_catalog()
        lines = catalog.strip().split("\n")
        # 3 categories x (1 header + 1 tool each) = 6 lines
        assert len(lines) == 6
        # Categories should be sorted alphabetically
        assert lines[0].startswith("[CODE]")
        assert lines[2].startswith("[FILESYSTEM]")
        assert lines[4].startswith("[SYSTEM]")

    def test_descriptions_included_in_compact(self):
        ex = _make_executor(
            ("read_file", "Read a file from disk with encoding support", "filesystem"),
        )
        catalog = ex.get_compact_catalog()
        # New format includes short descriptions with signatures
        assert "read_file(" in catalog and "Read a file from disk with encoding support" in catalog

    def test_compact_vs_for_llm_is_shorter(self):
        ex = _make_executor(
            ("read_file", "Read a file from disk", "filesystem"),
            ("write_file", "Write content to a file", "filesystem"),
            ("check_port", "Check what process uses a port", "system"),
        )
        compact = ex.get_compact_catalog()
        full = ex.get_for_llm()
        # compact includes signatures now, for_llm is the simpler format
        # Both formats should contain the tool names
        assert "read_file" in compact and "read_file" in full


# ═══════════════════════════════════════════════════════════════════════════════
# ToolExecutor basics
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolExecutorBasics:
    """Tests for ToolExecutor register, execute, list_tools, descriptions."""

    def test_register_and_list(self):
        ex = ToolExecutor()
        ex.register("my_tool", lambda: "ok", "Does stuff", "general")
        assert "my_tool" in ex.list_tools()

    def test_descriptions(self):
        ex = ToolExecutor()
        ex.register("t1", lambda: None, "Desc one", "cat_a")
        ex.register("t2", lambda: None, "Desc two", "cat_b")
        descs = ex.descriptions()
        assert descs["t1"] == "Desc one"
        assert descs["t2"] == "Desc two"

    @pytest.mark.asyncio
    async def test_execute_sync_function(self):
        ex = ToolExecutor()
        ex.register("add", lambda a, b: a + b, "Add two numbers", "math")
        result = await ex.execute("add", a=3, b=4)
        assert result == 7

    @pytest.mark.asyncio
    async def test_execute_async_function(self):
        async def async_double(value: int) -> int:
            return value * 2

        ex = ToolExecutor()
        ex.register("double", async_double, "Double a number", "math")
        result = await ex.execute("double", value=5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_raises(self):
        ex = ToolExecutor()
        with pytest.raises(ValueError, match="Tool desconocida"):
            await ex.execute("nonexistent")

    def test_get_for_llm_format(self):
        ex = _make_executor(
            ("t1", "Tool one", "alpha"),
            ("t2", "Tool two", "beta"),
        )
        output = ex.get_for_llm()
        assert "[ALPHA]" in output
        assert "[BETA]" in output
        assert "t1: Tool one" in output


# ═══════════════════════════════════════════════════════════════════════════════
# _verify — Enhanced heuristic verification (P3-07)
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerify:
    """Tests for AgentLoop._verify enhanced heuristics."""

    @pytest.fixture
    def loop(self):
        llm = MagicMock()
        return AgentLoop(llm)

    @pytest.fixture
    def reasoning(self):
        return ReasoningResult(
            thought="test", plan=[], tool_calls=[], confidence=0.8
        )

    @pytest.mark.asyncio
    async def test_no_actions_returns_done(self, loop, reasoning):
        result = await loop._verify("task", [], reasoning)
        assert result.verified is True
        assert result.score == 1.0
        assert result.next_action == "done"

    @pytest.mark.asyncio
    async def test_all_success_with_output(self, loop, reasoning):
        actions = [
            ActionResult(tool="t1", success=True, output="data found"),
            ActionResult(tool="t2", success=True, output="port 8070 open"),
        ]
        result = await loop._verify("task", actions, reasoning)
        assert result.verified is True
        assert result.score == 1.0
        assert result.next_action == "done"

    @pytest.mark.asyncio
    async def test_all_failed(self, loop, reasoning):
        actions = [
            ActionResult(tool="t1", success=False, output=None, error="timeout"),
            ActionResult(tool="t2", success=False, output=None, error="not found"),
        ]
        result = await loop._verify("task", actions, reasoning)
        assert result.verified is False
        assert result.score == 0.0
        assert result.next_action == "escalate"
        assert len(result.issues) == 2

    @pytest.mark.asyncio
    async def test_empty_output_downgraded(self, loop, reasoning):
        """Success with empty output should be flagged as an issue."""
        actions = [
            ActionResult(tool="t1", success=True, output=None),
        ]
        result = await loop._verify("task", actions, reasoning)
        assert result.verified is False
        assert result.score == 0.0
        assert any("empty output" in i for i in result.issues)

    @pytest.mark.asyncio
    async def test_empty_string_output_downgraded(self, loop, reasoning):
        """Success with empty string output should be flagged."""
        actions = [
            ActionResult(tool="t1", success=True, output="   "),
        ]
        result = await loop._verify("task", actions, reasoning)
        assert result.verified is False
        assert any("empty output" in i for i in result.issues)

    @pytest.mark.asyncio
    async def test_error_indicator_in_output(self, loop, reasoning):
        """Output containing error text gets partial credit (0.5)."""
        actions = [
            ActionResult(tool="t1", success=True, output="Traceback (most recent call last):\n  File..."),
        ]
        result = await loop._verify("task", actions, reasoning)
        assert any("error indicator" in i for i in result.issues)
        # 0.5 / 1 = 0.5 → still enough for retry but not done
        assert result.score == 0.5

    @pytest.mark.asyncio
    async def test_error_indicator_partial_credit(self, loop, reasoning):
        """Error indicator output + good output = partial verified."""
        actions = [
            ActionResult(tool="t1", success=True, output="Exception: something broke"),
            ActionResult(tool="t2", success=True, output="dashboard is running"),
        ]
        result = await loop._verify("task", actions, reasoning)
        # (0.5 + 1.0) / 2 = 0.75 → verified=True (>= 0.6)
        assert result.verified is True
        assert result.score == 0.75

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self, loop, reasoning):
        """Mix of real success and failure."""
        actions = [
            ActionResult(tool="t1", success=True, output="ok"),
            ActionResult(tool="t2", success=False, output=None, error="timeout"),
        ]
        result = await loop._verify("task", actions, reasoning)
        # 1 / 2 = 0.5 → retry range
        assert result.score == 0.5
        assert result.next_action == "retry"

    @pytest.mark.asyncio
    async def test_mostly_good_still_done(self, loop, reasoning):
        """Two good + one empty = 2/3 = 0.67 → done."""
        actions = [
            ActionResult(tool="t1", success=True, output="data"),
            ActionResult(tool="t2", success=True, output="more data"),
            ActionResult(tool="t3", success=True, output=None),
        ]
        result = await loop._verify("task", actions, reasoning)
        assert result.verified is True
        assert result.score == pytest.approx(0.67, abs=0.01)
        assert result.next_action == "done"
