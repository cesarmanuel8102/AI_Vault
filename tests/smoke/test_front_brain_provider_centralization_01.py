from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_primary_kimi_model_is_centralized_in_config():
    config = _read("tmp_agent/brain_v9/config.py")
    finalizer = _read("tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py")
    capability_registry = _read("tmp_agent/brain_v9/core/agent_kernel_v2/capability_registry.py")

    assert "PRIMARY_KIMI_MODEL = os.getenv" in config
    assert "from brain_v9.config import API_ENDPOINTS, PRIMARY_KIMI_MODEL" in finalizer
    assert "PRIMARY_KIMI_MODEL = \"kimi-k2.6:cloud\"" in finalizer  # import-failure fallback only
    assert "from brain_v9.config import API_ENDPOINTS, OLLAMA_MODEL, PRIMARY_KIMI_MODEL" in capability_registry


def test_ollama_chat_endpoint_is_centralized_for_agent_and_codegen():
    finalizer = _read("tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py")
    codegen = _read("tmp_agent/brain_v9/brain/codegen.py")

    assert "API_ENDPOINTS[\"ollama\"]" in finalizer
    assert "API_ENDPOINTS.get(\"ollama\"" in codegen
    assert "OLLAMA_CHAT_URL = \"http://127.0.0.1:11434/api/chat\"" not in finalizer
    assert "OLLAMA_CHAT_URL = \"http://localhost:11434/api/chat\"" not in codegen


def test_agent_v2_runtime_ollama_calls_do_not_use_hardcoded_endpoint_fallbacks():
    paths = [
        "tmp_agent/brain_v9/core/agent_kernel_v2/finalizer.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/intent_adapter.py",
        "tmp_agent/brain_v9/core/agent_kernel_v2/capability_registry.py",
    ]
    for path in paths:
        text = _read(path)
        assert 'API_ENDPOINTS.get("ollama", "http://127.0.0.1:11434/api/chat")' not in text
        assert 'API_ENDPOINTS.get("ollama", "http://localhost:11434/api/chat")' not in text


def test_semantic_embedding_base_url_comes_from_config():
    config = _read("tmp_agent/brain_v9/config.py")
    semantic = _read("tmp_agent/brain_v9/core/semantic_memory_faiss.py")

    assert "OLLAMA_BASE_URL = os.getenv" in config
    assert "from brain_v9.config import API_ENDPOINTS, BASE_PATH, OLLAMA_BASE_URL, STATE_PATH" in semantic
    assert "OLLAMA_URL = OLLAMA_BASE_URL" in semantic
    assert "OLLAMA_URL = \"http://localhost:11434\"" not in semantic
