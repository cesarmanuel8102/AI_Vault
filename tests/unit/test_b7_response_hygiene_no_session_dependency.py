"""B7-STRANGLER-05: sanitizer module must be importable WITHOUT importing session."""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"


def test_no_session_dependency_in_subprocess():
    """In a fresh subprocess, importing session_response_hygiene must NOT pull in
    brain_v9.core.session (would imply a circular/heavy dependency)."""
    code = (
        "import sys;"
        f"sys.path.insert(0, r'{_TMP_AGENT}');"
        "import brain_v9.core.session_response_hygiene as m;"
        "assert callable(m.sanitize_llm_chat_response);"
        "assert 'brain_v9.core.session' not in sys.modules, "
        "    sorted(k for k in sys.modules if k.startswith('brain_v9'));"
        "print('OK')"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode == 0, f"stdout={res.stdout!r} stderr={res.stderr!r}"
    assert "OK" in res.stdout


def test_module_only_imports_re_and_stdlib():
    """Ensure the new module is stateless and stdlib-only."""
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    mod = importlib.import_module("brain_v9.core.session_response_hygiene")
    # Must expose the function
    assert hasattr(mod, "sanitize_llm_chat_response")
    assert callable(mod.sanitize_llm_chat_response)
    # __all__ should advertise the public API
    assert "sanitize_llm_chat_response" in getattr(mod, "__all__", [])


def test_function_is_stateless_pure():
    """Same input → same output across multiple invocations."""
    if str(_TMP_AGENT) not in sys.path:
        sys.path.insert(0, str(_TMP_AGENT))
    from brain_v9.core.session_response_hygiene import sanitize_llm_chat_response
    inputs = [
        "",
        "hola",
        "[OBSERVE]: x\n[ACT]: y",
        "respuesta plana",
    ]
    for inp in inputs:
        a = sanitize_llm_chat_response(inp)
        b = sanitize_llm_chat_response(inp)
        assert a == b, f"non-deterministic for {inp!r}: {a!r} vs {b!r}"
