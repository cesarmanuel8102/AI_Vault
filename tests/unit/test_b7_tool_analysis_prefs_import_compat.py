"""B7-STRANGLER-09: import-compat tests for session_tool_analysis_prefs.

Verifies:

* The new module exports the two public predicates and an explicit ``__all__``.
* ``BrainSession`` keeps both legacy attribute names as ``@staticmethod``
  descriptors (preserving class- and instance-level access semantics).
* The shim methods produce identical results to the standalone functions for
  representative payloads (so external callers of
  ``BrainSession._prefers_no_tool_analysis`` /
  ``BrainSession._has_explicit_tool_target`` keep observing the same outputs).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))

from brain_v9.core import session_tool_analysis_prefs as tap
from brain_v9.core.session import BrainSession


# ── Module-level surface ────────────────────────────────────────────────────


def test_module_importable():
    import brain_v9.core.session_tool_analysis_prefs as m
    assert m is tap


def test_public_callables_exist():
    assert callable(tap.prefers_no_tool_analysis)
    assert callable(tap.has_explicit_tool_target)


def test_all_exports_exact():
    assert set(tap.__all__) == {
        "prefers_no_tool_analysis",
        "has_explicit_tool_target",
    }


# ── BrainSession descriptor compatibility ───────────────────────────────────


def test_brainsession_keeps_prefers_no_tool_analysis_attr():
    assert hasattr(BrainSession, "_prefers_no_tool_analysis")
    assert callable(BrainSession._prefers_no_tool_analysis)


def test_brainsession_keeps_has_explicit_tool_target_attr():
    assert hasattr(BrainSession, "_has_explicit_tool_target")
    assert callable(BrainSession._has_explicit_tool_target)


def test_prefers_no_tool_analysis_is_staticmethod_descriptor():
    raw = BrainSession.__dict__["_prefers_no_tool_analysis"]
    assert isinstance(raw, staticmethod)


def test_has_explicit_tool_target_is_staticmethod_descriptor():
    raw = BrainSession.__dict__["_has_explicit_tool_target"]
    assert isinstance(raw, staticmethod)


def test_class_level_access_returns_callable():
    # BrainSession._prefers_no_tool_analysis(msg) must work without an instance.
    assert BrainSession._prefers_no_tool_analysis("no uses tools") is True
    assert BrainSession._has_explicit_tool_target("revisa /tmp/foo/bar") is True


def test_instance_level_access_returns_callable():
    # Use __new__ to avoid heavy __init__ side effects.
    inst = BrainSession.__new__(BrainSession)
    assert inst._prefers_no_tool_analysis("solo analiza") is True
    assert inst._has_explicit_tool_target("ejecuta servicio brain") is True


# ── Behavioural equivalence: shim == standalone ─────────────────────────────


_PAYLOADS = [
    "",
    "hola",
    "no uses tools",
    "no use tools",
    "sin herramientas",
    "solo analiza el archivo",
    "revisa C:\\AI_VAULT\\tmp_agent\\brain_v9\\core\\session.py",
    "verifica el puerto 8000",
    "ping a 192.168.1.1",
    "ejecuta run_phase207",
    "revisa los logs de ollama",
    "no toques nada en el dashboard",
    None,  # exercises ``message or ""`` fallback
]


def test_shim_matches_standalone_prefers():
    for payload in _PAYLOADS:
        a = BrainSession._prefers_no_tool_analysis(payload)  # type: ignore[arg-type]
        b = tap.prefers_no_tool_analysis(payload)  # type: ignore[arg-type]
        assert a == b, f"mismatch for prefers payload={payload!r}: shim={a} std={b}"


def test_shim_matches_standalone_has_target():
    for payload in _PAYLOADS:
        a = BrainSession._has_explicit_tool_target(payload)  # type: ignore[arg-type]
        b = tap.has_explicit_tool_target(payload)  # type: ignore[arg-type]
        assert a == b, f"mismatch for target payload={payload!r}: shim={a} std={b}"
