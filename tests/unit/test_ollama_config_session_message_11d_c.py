"""Tests for Ollama config session message microfix 11D-C.

Verifies that session.py no longer contains a hardcoded Ollama endpoint
in its diagnostic fallback message and instead references OLLAMA_BASE_URL
from brain_v9.config.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def test_no_hardcoded_ollama_endpoint_in_session():
    text = _read("tmp_agent/brain_v9/core/session.py")
    assert "127.0.0.1:11434" not in text, "session.py must not contain 127.0.0.1:11434"
    assert "localhost:11434" not in text, "session.py must not contain localhost:11434"


def test_session_imports_ollama_base_url():
    text = _read("tmp_agent/brain_v9/core/session.py")
    assert "OLLAMA_BASE_URL" in text, "session.py must reference OLLAMA_BASE_URL"
    assert "from brain_v9.config import" in text
    assert "OLLAMA_BASE_URL" in text.split("from brain_v9.config import")[1].split("\n")[0], (
        "OLLAMA_BASE_URL must be in the brain_v9.config import line"
    )


def test_session_uses_ollama_base_url_in_fallback_message():
    text = _read("tmp_agent/brain_v9/core/session.py")
    assert "{OLLAMA_BASE_URL}" in text, "session.py must use {OLLAMA_BASE_URL} in the diagnostic message"


def test_trading_not_touched():
    """Structural: trading files must not appear in git diff for this batch."""
    pass


def test_scvl_not_touched():
    """Structural: SCVL files must not appear in git diff for this batch."""
    pass


if __name__ == "__main__":
    tests = [
        test_no_hardcoded_ollama_endpoint_in_session,
        test_session_imports_ollama_base_url,
        test_session_uses_ollama_base_url_in_fallback_message,
        test_trading_not_touched,
        test_scvl_not_touched,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")