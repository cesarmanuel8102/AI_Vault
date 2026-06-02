"""B7-STRANGLER-08: Behaviour smoke test for session_context_budget.

Verifies behavioural parity between the extracted standalone functions
``session_context_budget.{truncate_message, truncate_to_budget}`` and the
``BrainSession._truncate_message`` / ``BrainSession._truncate_to_budget``
shims, plus end-to-end semantics matching the original BrainSession code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))

from brain_v9.core import session_context_budget as cb  # noqa: E402
from brain_v9.core.session import BrainSession  # noqa: E402


# ── truncate_message ────────────────────────────────────────────────────────

def test_truncate_message_short_unchanged_returns_same_object():
    msg = {"role": "user", "content": "hola"}
    result = cb.truncate_message(msg, 6000)
    # Original semantics: short messages return the SAME object identity.
    assert result is msg
    assert result["content"] == "hola"


def test_truncate_message_long_is_truncated_with_marker():
    msg = {"role": "user", "content": "x" * 10000}
    result = cb.truncate_message(msg, 6000)
    assert len(result["content"]) < 10000
    assert "truncado" in result["content"]
    assert result["content"].startswith("x" * 6000)
    # Original input not mutated
    assert msg["content"] == "x" * 10000


def test_truncate_message_exact_boundary_not_truncated():
    msg = {"role": "user", "content": "x" * 6000}
    result = cb.truncate_message(msg, 6000)
    assert "truncado" not in result["content"]
    assert result["content"] == "x" * 6000


def test_truncate_message_preserves_role_and_extra_fields():
    msg = {
        "role": "assistant",
        "content": "x" * 10000,
        "timestamp": "2026-01-01",
        "tool_call_id": "abc",
    }
    result = cb.truncate_message(msg, 100)
    assert result["role"] == "assistant"
    assert result["timestamp"] == "2026-01-01"
    assert result["tool_call_id"] == "abc"
    assert "truncado" in result["content"]


def test_truncate_message_handles_missing_content_field():
    """Original used ``msg.get("content", "")``; missing key -> treated as ''."""
    msg = {"role": "system"}
    result = cb.truncate_message(msg, 100)
    # Empty content is <= 100 chars -> original returned unchanged.
    assert result is msg


# ── truncate_to_budget ───────────────────────────────────────────────────────

def _msg(content: str, role: str = "user") -> Dict:
    return {"role": role, "content": content}


def test_truncate_to_budget_empty_history_returns_empty():
    result = cb.truncate_to_budget([], budget_tokens=1000)
    assert result == []


def test_truncate_to_budget_small_history_fits_within_budget():
    history: List[Dict] = [
        _msg("hola"),
        _msg("todo bien", role="assistant"),
        _msg("genial"),
    ]
    result = cb.truncate_to_budget(history, budget_tokens=5000)
    assert len(result) == 3


def test_truncate_to_budget_drops_oldest_when_over_budget():
    history = [_msg("a" * 100) for _ in range(20)]
    result = cb.truncate_to_budget(history, budget_tokens=190)
    assert len(result) < 20
    assert len(result) >= 4


def test_truncate_to_budget_preserves_most_recent():
    history = [_msg(f"msg_{i}") for i in range(50)]
    result = cb.truncate_to_budget(history, budget_tokens=100)
    assert len(result) < 50
    assert result[-1]["content"] == "msg_49"


def test_truncate_to_budget_zero_budget_returns_empty():
    history = [_msg("anything")]
    result = cb.truncate_to_budget(history, budget_tokens=0)
    assert result == []


def test_truncate_to_budget_respects_explicit_max_msg_chars():
    history = [_msg("x" * 50000)]
    result = cb.truncate_to_budget(
        history, budget_tokens=3000, max_msg_chars=6000
    )
    assert len(result) == 1
    assert "truncado" in result[0]["content"]
    assert len(result[0]["content"]) < 50000


def test_truncate_to_budget_uses_default_when_max_msg_chars_zero():
    """``max_msg_chars=0`` should fall back to ``max_msg_chars_default``."""
    history = [_msg("x" * 50000)]
    # Default of 6000 -> truncated content ~6030 chars. Budget large enough.
    result = cb.truncate_to_budget(
        history,
        budget_tokens=5000,
        max_msg_chars=0,
        max_msg_chars_default=6000,
    )
    assert len(result) == 1
    assert "truncado" in result[0]["content"]


def test_truncate_to_budget_oversized_dropped_if_still_too_big():
    history = [_msg("x" * 50000)]
    result = cb.truncate_to_budget(
        history, budget_tokens=10, max_msg_chars=6000
    )
    assert result == []


def test_truncate_to_budget_does_not_mutate_input_list():
    history = [_msg("short"), _msg("x" * 50000), _msg("also short")]
    snapshot_len = len(history)
    snapshot_content = history[1]["content"]
    cb.truncate_to_budget(history, budget_tokens=100, max_msg_chars=6000)
    # Original list length / contents preserved
    assert len(history) == snapshot_len
    assert history[1]["content"] == snapshot_content


# ── shim ↔ standalone parity ─────────────────────────────────────────────────

def test_shim_delegates_to_standalone_with_session_default():
    """``BrainSession._truncate_to_budget`` must equal
    ``cb.truncate_to_budget(..., max_msg_chars_default=BrainSession._MAX_MSG_CHARS)``."""
    history = [_msg("a" * 100) for _ in range(20)]
    via_shim = BrainSession._truncate_to_budget(history, budget_tokens=190)
    via_standalone = cb.truncate_to_budget(
        history,
        budget_tokens=190,
        max_msg_chars_default=BrainSession._MAX_MSG_CHARS,
    )
    assert via_shim == via_standalone


def test_shim_truncate_message_matches_standalone_for_long_payload():
    msg = {"role": "user", "content": "y" * 12345}
    a = BrainSession._truncate_message(msg, 100)
    b = cb.truncate_message(msg, 100)
    assert a == b
