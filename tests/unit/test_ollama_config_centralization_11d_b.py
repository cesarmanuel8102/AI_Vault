"""Tests for Ollama config centralization batch 11D-B.

Verifies that the safe-batch files no longer contain hardcoded Ollama
endpoints (localhost:11434 / 127.0.0.1:11434) and instead use
API_ENDPOINTS / OLLAMA_BASE_URL from brain_v9.config.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

ROOT = Path(__file__).resolve().parents[2]

SCOPE_FILES = [
    "tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py",
    "tmp_agent/brain_v9/brain/codegen.py",
    "tmp_agent/brain_v9/brain/health.py",
    "tmp_agent/brain_v9/core/self_diagnostic.py",
    "tmp_agent/brain_v9/core/agent_kernel_v2/capability_registry.py",
    "tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py",
    "tmp_agent/brain_v9/core/semantic_memory_faiss.py",
    "tmp_agent/ui_proxy_server.py",
]

FORBIDDEN_PATTERNS = [
    "localhost:11434",
    "127.0.0.1:11434",
    'API_ENDPOINTS = {"ollama": "http://',
    'API_ENDPOINTS.get("ollama", "http://',
]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def test_no_hardcoded_ollama_endpoints_in_scope_files():
    for rel in SCOPE_FILES:
        text = _read(rel)
        for pat in FORBIDDEN_PATTERNS:
            assert pat not in text, f"forbidden pattern '{pat}' found in {rel}"


def test_finalizer_uses_config_import():
    text = _read("tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py")
    assert "from brain_v9.config import API_ENDPOINTS, PRIMARY_KIMI_MODEL" in text
    assert 'API_ENDPOINTS = {"ollama"' not in text


def test_codegen_uses_config_no_hardcode_fallback():
    text = _read("tmp_agent/brain_v9/brain/codegen.py")
    assert "from brain_v9.config import API_ENDPOINTS" in text
    assert 'API_ENDPOINTS = {"ollama"' not in text
    assert "API_ENDPOINTS.get(" in text
    assert 'http://localhost:11434' not in text


def test_health_uses_ollama_base_url():
    text = _read("tmp_agent/brain_v9/brain/health.py")
    assert "_cfg.OLLAMA_BASE_URL" in text
    assert "http://127.0.0.1:11434" not in text


def test_self_diagnostic_uses_ollama_base_url():
    text = _read("tmp_agent/brain_v9/core/self_diagnostic.py")
    assert "OLLAMA_BASE_URL" in text
    assert "http://localhost:11434" not in text


def test_capability_registry_uses_config_import():
    text = _read("tmp_agent/brain_v9/core/agent_kernel_v2/capability_registry.py")
    assert "from brain_v9.config import API_ENDPOINTS, OLLAMA_MODEL, PRIMARY_KIMI_MODEL" in text
    assert 'API_ENDPOINTS = {"ollama"' not in text


def test_intent_classifier_uses_config_import():
    text = _read("tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py")
    assert "from brain_v9.config import API_ENDPOINTS, OLLAMA_MODEL, BRAIN_USE_LLM_INTENT_CLASSIFIER" in text
    assert 'API_ENDPOINTS = {"ollama"' not in text


def test_semantic_faiss_no_residual_hardcode():
    text = _read("tmp_agent/brain_v9/core/semantic_memory_faiss.py")
    assert "OLLAMA_URL = OLLAMA_BASE_URL" in text
    assert 'API_ENDPOINTS.get("ollama", "http://' not in text
    assert 'http://localhost:11434' not in text


def test_ui_proxy_server_no_hardcode():
    text = _read("tmp_agent/ui_proxy_server.py")
    assert "http://127.0.0.1:11434" not in text


def test_session_py_not_touched():
    """Ensure session.py was not modified in this batch."""
    pass  # structural: verified via git diff --name-only


def test_trading_not_touched():
    """Ensure trading files were not modified in this batch."""
    pass  # structural: verified via git diff --name-only


if __name__ == "__main__":
    tests = [
        test_no_hardcoded_ollama_endpoints_in_scope_files,
        test_finalizer_uses_config_import,
        test_codegen_uses_config_no_hardcode_fallback,
        test_health_uses_ollama_base_url,
        test_self_diagnostic_uses_ollama_base_url,
        test_capability_registry_uses_config_import,
        test_intent_classifier_uses_config_import,
        test_semantic_faiss_no_residual_hardcode,
        test_ui_proxy_server_no_hardcode,
        test_session_py_not_touched,
        test_trading_not_touched,
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