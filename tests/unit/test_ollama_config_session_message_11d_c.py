"""Static tests for Ollama config session-message centralization 11D-C.

The test intentionally builds endpoint tokens by concatenation so this file
itself does not contain the forbidden endpoint literals that it guards against.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SESSION_PATH = ROOT / "tmp_agent" / "brain_v9" / "core" / "session.py"

FORBIDDEN_OLLAMA_ENDPOINT_TOKENS = (
    "127" + ".0." + "0.1" + ":11" + "434",
    "local" + "host:11" + "434",
    "http://" + "127" + ".0." + "0.1" + ":11" + "434",
    "http://" + "local" + "host:11" + "434",
)


def _session_source() -> str:
    return SESSION_PATH.read_text(encoding="utf-8", errors="ignore")


def test_no_hardcoded_ollama_endpoint_in_session() -> None:
    text = _session_source()
    for token in FORBIDDEN_OLLAMA_ENDPOINT_TOKENS:
        assert token not in text, (
            "session.py must not contain a hardcoded Ollama endpoint token: "
            f"{token}"
        )


def test_session_imports_ollama_base_url() -> None:
    text = _session_source()
    assert "OLLAMA_BASE_URL" in text, "session.py must reference OLLAMA_BASE_URL"
    assert "from brain_v9.config import" in text


def test_session_uses_ollama_base_url_in_fallback_message() -> None:
    text = _session_source()
    assert "{OLLAMA_BASE_URL}" in text, (
        "session.py must use OLLAMA_BASE_URL in the diagnostic message"
    )


def test_trading_not_touched_by_scope() -> None:
    text = _session_source()
    assert "tmp_agent/brain_v9/trading" not in text


def test_scvl_not_touched_by_scope() -> None:
    text = _session_source()
    assert "session_scvl_gate.py" not in text
    assert "scvl_promotion_gate.py" not in text


if __name__ == "__main__":
    tests = [
        test_no_hardcoded_ollama_endpoint_in_session,
        test_session_imports_ollama_base_url,
        test_session_uses_ollama_base_url_in_fallback_message,
        test_trading_not_touched_by_scope,
        test_scvl_not_touched_by_scope,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {test.__name__}: {exc}")
    passed = len(tests) - failed
    print(f"\n{passed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
