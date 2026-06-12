import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))

SEMANTIC = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
FAISS_IDS = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"
FAISS_INDEX = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"
OPENAI_COMPAT = ROOT / "tmp_agent" / "brain_v9" / "api" / "openai_compat.py"
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
DIRECT_CLIENT = ROOT / "tmp_agent" / "brain_v9" / "evolution" / "direct_brain_client.py"
DIALOGUE_PROBE = ROOT / "tmp_agent" / "brain_v9" / "evolution" / "codex_brain_dialogue_probe.py"


def _git_staged_names():
    cp = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line.strip().replace("\\", "/") for line in cp.stdout.splitlines() if line.strip()]


def _client(monkeypatch):
    from fastapi.testclient import TestClient
    import brain_v9.api.openai_compat as compat

    async def fake_handle_user_message(message, room="default", context=None, dry_run=False):
        return {
            "content": f"echo: {message}",
            "response": f"echo: {message}",
            "intent": "QUERY",
            "route": "test_router_entrypoint",
            "governance_applied": True,
            "no_cot_leak": True,
            "canonical_path": "C:\\AI_VAULT_CANONICAL",
            "latency_ms": 1.0,
            "errors": [],
            "success": True,
            "model": "fake-router",
        }

    monkeypatch.setattr(compat, "handle_user_message", fake_handle_user_message)
    from brain_v9.main import app
    return TestClient(app)


def test_01_semantic_memory_lines_1715():
    assert sum(1 for _ in SEMANTIC.open(encoding="utf-8")) == 1715


def test_02_faiss_ids_1616():
    assert len(json.load(FAISS_IDS.open(encoding="utf-8"))) == 1616


def test_03_faiss_ntotal_1616_if_readable():
    try:
        import faiss
    except Exception:
        return
    assert faiss.read_index(str(FAISS_INDEX)).ntotal == 1616


def test_04_base_path_canonical():
    from brain_v9.config import BASE_PATH
    assert str(BASE_PATH) == "C:\\AI_VAULT_CANONICAL"


def test_05_openai_compat_exists():
    assert OPENAI_COMPAT.exists()


def test_06_router_registered_in_main_py():
    text = MAIN.read_text(encoding="utf-8")
    assert "openai_compat_router" in text
    assert "app.include_router(openai_compat_router)" in text


def test_07_openai_compat_imports_handle_user_message():
    text = OPENAI_COMPAT.read_text(encoding="utf-8")
    assert "from brain_v9.core.router_entrypoint import handle_user_message" in text
    assert "handle_user_message(" in text


def test_08_openai_compat_does_not_contain_llmmanager_query():
    text = OPENAI_COMPAT.read_text(encoding="utf-8")
    assert "LLMManager.query" not in text
    assert ".llm.query" not in text


def test_09_openai_compat_does_not_contain_direct_faiss_write():
    text = OPENAI_COMPAT.read_text(encoding="utf-8")
    assert "faiss.write_index" not in text
    assert "semantic_memory.append" not in text
    assert "open(...semantic_memory" not in text


def test_10_direct_brain_client_exists():
    assert DIRECT_CLIENT.exists()


def test_11_codex_brain_dialogue_probe_exists():
    assert DIALOGUE_PROBE.exists()


def test_12_app_import_succeeds(monkeypatch):
    assert _client(monkeypatch) is not None


def test_13_get_v1_models_returns_200(monkeypatch):
    response = _client(monkeypatch).get("/v1/models")
    assert response.status_code == 200


def test_14_v1_models_includes_brain_v9_local(monkeypatch):
    data = _client(monkeypatch).get("/v1/models").json()
    assert any(item["id"] == "brain-v9-local" for item in data["data"])


def test_15_post_chat_completions_stream_false_returns_200(monkeypatch):
    response = _client(monkeypatch).post("/v1/chat/completions", json={"model": "brain-v9-local", "messages": [{"role": "user", "content": "hola"}], "stream": False})
    assert response.status_code == 200


def test_16_response_object_chat_completion(monkeypatch):
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    assert data["object"] == "chat.completion"


def test_17_response_message_content_exists(monkeypatch):
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    assert data["choices"][0]["message"]["content"]


def test_18_response_includes_brain_intent(monkeypatch):
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    assert data["brain"]["intent"] == "QUERY"


def test_19_response_includes_brain_route(monkeypatch):
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    assert data["brain"]["route"] == "test_router_entrypoint"


def test_20_response_includes_governance_true(monkeypatch):
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    assert data["brain"]["governance_applied"] is True


def test_21_response_includes_no_cot_true(monkeypatch):
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    assert data["brain"]["no_cot_leak"] is True


def test_22_stream_true_returns_safe_unsupported(monkeypatch):
    response = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}], "stream": True})
    assert response.status_code in {400, 501}
    assert "streaming_not_supported_yet" in response.text


def test_23_empty_messages_returns_400(monkeypatch):
    response = _client(monkeypatch).post("/v1/chat/completions", json={"messages": []})
    assert response.status_code == 400


def test_24_response_no_raw_chain_of_thought(monkeypatch):
    text = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).text
    assert "raw_chain_of_thought" not in text


def test_25_response_no_private_reasoning(monkeypatch):
    text = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).text
    assert "private_reasoning" not in text


def test_26_direct_client_validate_openai_response(monkeypatch):
    from brain_v9.evolution.direct_brain_client import validate_openai_response
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    assert validate_openai_response(data) is True


def test_27_direct_client_extract_brain_metadata(monkeypatch):
    from brain_v9.evolution.direct_brain_client import extract_brain_metadata
    data = _client(monkeypatch).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hola"}]}).json()
    meta = extract_brain_metadata(data)
    assert meta["intent"] == "QUERY"
    assert meta["route"] == "test_router_entrypoint"
    assert meta["governance_applied"] is True


def test_28_no_memory_semantic_staged():
    assert not any(p.startswith("memory/semantic/") for p in _git_staged_names())


def test_29_no_trading_staged():
    assert not any(p == "trading" or p.startswith("trading/") for p in _git_staged_names())


def test_30_no_b8_staged():
    assert not any(p == "B8" or p.startswith("B8/") for p in _git_staged_names())


def test_31_no_tmp_agent_strategies_staged():
    assert not any(p.startswith("tmp_agent/strategies/") for p in _git_staged_names())


def test_32_no_env_staged():
    assert not any(p == ".env" or p.endswith("/.env") for p in _git_staged_names())


def test_33_roadmap_status_json_valid():
    with (ROOT / "ROADMAP_STATUS.json").open(encoding="utf-8") as fh:
        assert isinstance(json.load(fh), dict)


def test_34_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
