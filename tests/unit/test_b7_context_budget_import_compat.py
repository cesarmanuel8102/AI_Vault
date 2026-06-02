"""B7-STRANGLER-08: Import-compatibility test for session_context_budget.

Verifies that the extracted module exposes the expected public API and that
``BrainSession`` keeps a fully backward-compatible class-attribute / shim
surface area:

    - ``cb.MAX_MSG_CHARS`` exists, is an ``int``, and equals
      ``BrainSession._MAX_MSG_CHARS``.
    - ``cb.truncate_message`` and ``cb.truncate_to_budget`` are callable.
    - ``BrainSession._truncate_message`` is registered as ``staticmethod``.
    - ``BrainSession._truncate_to_budget`` is registered as ``classmethod``.
    - The shim and the standalone function produce identical output for
      representative payloads.
    - The shim signatures still accept the call patterns used by existing
      tests / internal consumers.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``tmp_agent/`` importable so we can ``import brain_v9.*`` regardless
# of how pytest was launched.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))

from brain_v9.core import session_context_budget as cb  # noqa: E402
from brain_v9.core.session import BrainSession  # noqa: E402


# ── Public API of the extracted module ──────────────────────────────────────

def test_module_exposes_max_msg_chars_int():
    assert hasattr(cb, "MAX_MSG_CHARS")
    assert isinstance(cb.MAX_MSG_CHARS, int)
    assert cb.MAX_MSG_CHARS == 6000


def test_module_exposes_truncate_message_callable():
    assert hasattr(cb, "truncate_message")
    assert callable(cb.truncate_message)


def test_module_exposes_truncate_to_budget_callable():
    assert hasattr(cb, "truncate_to_budget")
    assert callable(cb.truncate_to_budget)


def test_module_all_exports_match():
    assert set(cb.__all__) == {
        "MAX_MSG_CHARS",
        "truncate_message",
        "truncate_to_budget",
    }


# ── BrainSession compatibility surface ───────────────────────────────────────

def test_brain_session_max_msg_chars_class_attr():
    assert hasattr(BrainSession, "_MAX_MSG_CHARS")
    assert BrainSession._MAX_MSG_CHARS == cb.MAX_MSG_CHARS
    assert BrainSession._MAX_MSG_CHARS == 6000


def test_brain_session_truncate_message_callable():
    assert hasattr(BrainSession, "_truncate_message")
    assert callable(BrainSession._truncate_message)


def test_brain_session_truncate_to_budget_callable():
    assert hasattr(BrainSession, "_truncate_to_budget")
    assert callable(BrainSession._truncate_to_budget)


def test_truncate_message_is_staticmethod_descriptor():
    raw = BrainSession.__dict__["_truncate_message"]
    assert isinstance(raw, staticmethod), (
        "BrainSession._truncate_message must remain @staticmethod for shim "
        "compatibility (external tests bind it directly)."
    )


def test_truncate_to_budget_is_classmethod_descriptor():
    raw = BrainSession.__dict__["_truncate_to_budget"]
    assert isinstance(raw, classmethod), (
        "BrainSession._truncate_to_budget must remain @classmethod for shim "
        "compatibility (it relies on cls._MAX_MSG_CHARS for default)."
    )


# ── Behavioural equivalence: shim vs standalone ─────────────────────────────

def test_shim_truncate_message_equals_standalone_short():
    msg = {"role": "user", "content": "hola"}
    a = BrainSession._truncate_message(msg, 100)
    b = cb.truncate_message(msg, 100)
    assert a == b
    assert a["content"] == "hola"


def test_shim_truncate_message_equals_standalone_long():
    msg = {"role": "user", "content": "x" * 10000}
    a = BrainSession._truncate_message(msg, 6000)
    b = cb.truncate_message(msg, 6000)
    assert a == b
    assert "truncado" in a["content"]


def test_shim_truncate_to_budget_equals_standalone_default_chars():
    history = [{"role": "user", "content": f"msg_{i}"} for i in range(5)]
    a = BrainSession._truncate_to_budget(history, budget_tokens=5000)
    b = cb.truncate_to_budget(
        history,
        budget_tokens=5000,
        max_msg_chars_default=BrainSession._MAX_MSG_CHARS,
    )
    assert a == b


def test_shim_truncate_to_budget_equals_standalone_explicit_chars():
    history = [{"role": "user", "content": "x" * 50000}]
    a = BrainSession._truncate_to_budget(
        history, budget_tokens=3000, max_msg_chars=6000
    )
    b = cb.truncate_to_budget(
        history,
        budget_tokens=3000,
        max_msg_chars=6000,
        max_msg_chars_default=BrainSession._MAX_MSG_CHARS,
    )
    assert a == b


# ── Existing-style call patterns still work ──────────────────────────────────

def test_existing_call_pattern_truncate_message():
    msg = {"role": "user", "content": "hello"}
    result = BrainSession._truncate_message(msg, 100)
    assert result["content"] == "hello"


def test_existing_call_pattern_truncate_to_budget_kwarg():
    history = [{"role": "user", "content": "ping"}]
    result = BrainSession._truncate_to_budget(history, budget_tokens=5000)
    assert result == history
