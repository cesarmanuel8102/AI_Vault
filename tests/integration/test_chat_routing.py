"""Unit tests for CHAT-STABILITY-01 routing patch.

No runtime, no FastAPI TestClient — pure static / unit assertions.
We test the REAL BrainSession._should_use_agent by importing it directly.
"""
import pytest
import ast
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tmp_agent"))


# ---------------------------------------------------------------------------
# Real-method setup (lightweight, no side effects)
# ---------------------------------------------------------------------------
class DummyLogger:
    def info(self, *a, **kw): pass
    def debug(self, *a, **kw): pass
    def warning(self, *a, **kw): pass


class DummyMemory:
    def get_context(self):
        return []
    def save(self, *_a, **_kw):
        pass


def _make_session():
    """Build a valid BrainSession stub just heavy enough to call _should_use_agent."""
    from brain_v9.core.session import BrainSession
    obj = object.__new__(BrainSession)
    object.__setattr__(obj, "logger", DummyLogger())
    # _should_use_agent also references self._prefers_no_tool_analysis and
    # self._has_explicit_tool_target. Both are plain methods that need no extra
    # state, and work fine through the class binding on the instance.
    return obj


# ---------------------------------------------------------------------------
# Tests — real method assertions
# ---------------------------------------------------------------------------

class TestShouldUseAgentReal:
    """Covers LLM-first rules via the real BrainSession._should_use_agent."""

    def test_ping_conversation(self):
        session = _make_session()
        assert session._should_use_agent("ping", "CONVERSATION", 0.9) is False

    def test_explanatory_question_command(self):
        session = _make_session()
        assert session._should_use_agent(
            "explicame que falta para que el chat responda mejor",
            "COMMAND",
            0.9,
        ) is False

    def test_trading_conceptual_question(self):
        session = _make_session()
        assert session._should_use_agent(
            "que es una estrategia de mean reversion en trading?",
            "TRADING",
            0.9,
        ) is False

    def test_operational_logs(self):
        session = _make_session()
        assert session._should_use_agent(
            "revisa los logs mas recientes del sistema",
            "ANALYSIS",
            0.9,
        ) is True

    def test_operational_tests(self):
        session = _make_session()
        assert session._should_use_agent(
            "ejecuta los tests del repo",
            "COMMAND",
            0.9,
        ) is True

    def test_operational_patch(self):
        session = _make_session()
        assert session._should_use_agent(
            "aplica el patch en tmp_agent/brain_v9/core/session.py",
            "COMMAND",
            0.9,
        ) is True

    def test_analysis_without_target_returns_false(self):
        session = _make_session()
        assert session._should_use_agent(
            "analiza la situacion actual del mercado",
            "ANALYSIS",
            0.9,
        ) is False

    def test_trading_operational_with_target(self):
        session = _make_session()
        assert session._should_use_agent(
            "revisa el backtest de mean reversion en QC",
            "TRADING",
            0.9,
        ) is True

    def test_query_intent_always_false(self):
        session = _make_session()
        assert session._should_use_agent("que tan lejos esta la luna", "QUERY", 0.9) is False

    def test_creative_intent_always_false(self):
        session = _make_session()
        assert session._should_use_agent("escribe un poema sobre trading", "CREATIVE", 0.9) is False

    def test_memory_intent_always_false(self):
        session = _make_session()
        assert session._should_use_agent("recuerdas lo que te dije ayer", "MEMORY", 0.9) is False

    def test_conceptual_starts_with_que_es(self):
        session = _make_session()
        assert session._should_use_agent("que es un spread", "COMMAND", 0.9) is False

    def test_conceptual_starts_with_como_funciona(self):
        session = _make_session()
        assert session._should_use_agent("como funciona el order book", "ANALYSIS", 0.9) is False

    def test_operational_low_confidence(self):
        # Even with low confidence, explicit operational target + keyword wins
        session = _make_session()
        assert session._should_use_agent(
            "verifica la conexion con el endpoint de trading",
            "COMMAND",
            0.3,
        ) is True

    def test_no_tool_preference_without_target(self):
        session = _make_session()
        assert session._should_use_agent(
            "solo explicame lo que sabes sin usar herramientas",
            "COMMAND",
            0.9,
        ) is False

    def test_ping_trading_misclass(self):
        session = _make_session()
        assert session._should_use_agent("ping", "TRADING", 0.9) is False

    def test_pong(self):
        session = _make_session()
        assert session._should_use_agent("pong", "TRADING", 0.9) is False

    def test_hola(self):
        session = _make_session()
        assert session._should_use_agent("hola", "CONVERSATION", 0.9) is False

    def test_ok_short(self):
        session = _make_session()
        assert session._should_use_agent("ok", "COMMAND", 0.9) is False

    def test_gracias_short(self):
        session = _make_session()
        assert session._should_use_agent("gracias", "COMMAND", 0.9) is False

    def test_operational_short_with_target(self):
        session = _make_session()
        assert session._should_use_agent("revisa logs", "ANALYSIS", 0.9) is True

    def test_operational_short_with_target_2(self):
        session = _make_session()
        assert session._should_use_agent("ejecuta tests", "COMMAND", 0.9) is True



# ---------------------------------------------------------------------------
# AST-based guard-order validation
# ---------------------------------------------------------------------------

class _GuardOrderHelper:
    """Internal helper to extract and compare statement order in _should_use_agent."""
    _SOURCE = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")

    @classmethod
    def _line_index(cls, pattern: str) -> int:
        lines = cls._SOURCE.splitlines()
        for idx, line in enumerate(lines, 1):
            if pattern in line:
                return idx
        return -1


class TestGuardOrderStatic:
    """Verifies via line search that the new guards appear BEFORE the _AGENT_PATTERNS keyword match."""

    @classmethod
    def _before(cls, guard: str, keyword_line: str) -> None:
        g_idx = _GuardOrderHelper._line_index(guard)
        k_idx = _GuardOrderHelper._line_index(keyword_line)
        assert g_idx != -1, f"Guard '{guard}' not found in source"
        assert k_idx != -1, f"Keyword line '{keyword_line}' not found in source"
        assert g_idx < k_idx, (
            f"Guard '{guard}' (line {g_idx}) must be BEFORE "
            f"keyword match '{keyword_line}' (line {k_idx})"
        )

    def test_conceptual_guard_before_agent_patterns(self):
        # keyword anchor is the _AGENT_PATTERNS *use* inside _should_use_agent, not the global var definition
        self._before(
            "is_conceptual_question",
            "for p in _AGENT_PATTERNS):",
        )

    def test_query_intent_guard_before_agent_patterns(self):
        self._before(
            '{"QUERY"',
            "for p in _AGENT_PATTERNS):",
        )

    def test_trading_conceptual_guard_before_agent_patterns(self):
        self._before(
            '"TRADING"',
            "for p in _AGENT_PATTERNS):",
        )

    def test_analysis_operational_guard_before_agent_patterns(self):
        self._before(
            '"ANALYSIS" and not (has_operational_verb',
            "for p in _AGENT_PATTERNS):",
        )

    def test_never_agent_exact_before_agent_patterns(self):
        self._before(
            "never_agent_exact",
            "for p in _AGENT_PATTERNS):",
        )


class TestPatchPresence:
    """Static assertions that the source file actually contains the new rules."""

    def test_conceptual_question_starters_present(self):
        src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")
        assert 'conceptual_question_starters = (' in src
        assert '"que es "' in src
        assert '"explica "' in src

    def test_operational_targets_present(self):
        src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")
        assert 'operational_targets = (' in src
        assert '"logs"' in src
        assert '".py"' in src

    def test_trading_guard_present(self):
        src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")
        assert 'if intent == "TRADING" and is_conceptual_question:' in src

    def test_analysis_guard_present(self):
        src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")
        assert 'if intent == "ANALYSIS" and not (has_operational_verb and has_operational_target):' in src

    def test_query_intent_guard_present(self):
        src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")
        assert 'if intent in {"QUERY", "CONVERSATION", "CREATIVE", "MEMORY"}:' in src

    def test_never_agent_exact_present(self):
        src = (REPO_ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py").read_text(encoding="utf-8")
        assert "never_agent_exact" in src
        assert '"ping"' in src


if __name__ == "__main__":
    pytest.main([__file__, "-q", "--tb=short"])
