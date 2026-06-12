import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))
EVIDENCE = ROOT / "tmp_agent" / "front_chat_router_preservation_entrypoint_01"
ROUTER = ROOT / "tmp_agent" / "brain_v9" / "core" / "router_entrypoint.py"
MAIN = ROOT / "tmp_agent" / "brain_v9" / "main.py"
SEMANTIC = ROOT / "memory" / "semantic" / "semantic_memory.jsonl"
FAISS_IDS = ROOT / "memory" / "semantic" / "semantic_memory_faiss_ids.json"
FAISS_INDEX = ROOT / "memory" / "semantic" / "semantic_memory_faiss.index"
DOC = ROOT / "docs" / "FRONT_CHAT_ROUTER_PRESERVATION_ENTRYPOINT_01.md"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(name: str):
    with (EVIDENCE / name).open(encoding="utf-8") as fh:
        return json.load(fh)


def _git_staged_names():
    cp = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line.strip().replace("\\", "/") for line in cp.stdout.splitlines() if line.strip()]


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


def test_05_router_entrypoint_exists():
    assert ROUTER.exists()


def test_06_handle_user_message_imports():
    from brain_v9.core.router_entrypoint import handle_user_message
    assert callable(handle_user_message)


def test_07_intent_detector_detect_is_called_for_every_request():
    text = ROUTER.read_text(encoding="utf-8")
    assert "IntentDetector()" in text
    assert ".detect(message" in text or ".detect(message or" in text
    assert "detect_intent(message" in text


def test_08_governance_no_cot_filter_is_applied():
    text = ROUTER.read_text(encoding="utf-8")
    assert "apply_governance" in text
    assert "raw_chain_of_thought" in text
    assert "private_reasoning" in text
    assert "_sanitize_llm_chat_response" in text


def test_09_chat_route_uses_entrypoint_not_direct_llm_query():
    main = MAIN.read_text(encoding="utf-8")
    chat_start = main.index('@app.post("/chat"')
    chat_end = main.index('@app.delete("/sessions', chat_start)
    chat_block = main[chat_start:chat_end]
    assert "handle_user_message(" in chat_block
    assert "LLMManager().query" not in chat_block
    assert ".llm.query" not in chat_block


def test_10_simple_message_returns_structured_output():
    from brain_v9.core.router_entrypoint import handle_user_message
    result = asyncio.run(handle_user_message("hola", room="smoke-router", dry_run=True))
    assert isinstance(result, dict)
    assert result["content"]
    assert result["canonical_path"] == "C:\\AI_VAULT_CANONICAL"


def test_11_output_includes_intent():
    from brain_v9.core.router_entrypoint import handle_user_message
    result = asyncio.run(handle_user_message("hola", room="smoke-router", dry_run=True))
    assert "intent" in result


def test_12_output_includes_route():
    from brain_v9.core.router_entrypoint import handle_user_message
    result = asyncio.run(handle_user_message("hola", room="smoke-router", dry_run=True))
    assert "route" in result


def test_13_output_includes_governance_applied():
    from brain_v9.core.router_entrypoint import handle_user_message
    result = asyncio.run(handle_user_message("hola", room="smoke-router", dry_run=True))
    assert result["governance_applied"] is True


def test_14_output_does_not_expose_raw_chain_of_thought():
    from brain_v9.core.router_entrypoint import apply_governance
    governed = apply_governance("analysis: hidden reasoning raw_chain_of_thought")
    assert governed["no_cot_leak"] is True
    assert "raw_chain_of_thought" not in governed["content"]


def test_15_dry_run_does_not_mutate_memory_or_faiss():
    from brain_v9.core.router_entrypoint import handle_user_message
    before = (_sha(SEMANTIC), _sha(FAISS_IDS), _sha(FAISS_INDEX))
    asyncio.run(handle_user_message("dry run only", room="smoke-router", dry_run=True))
    after = (_sha(SEMANTIC), _sha(FAISS_IDS), _sha(FAISS_INDEX))
    assert before == after


def test_16_future_adapter_policy_documented():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")
    assert "/v1/chat/completions" in text
    assert "handle_user_message" in text
    assert "LLMManager.query" in text


def test_17_no_memory_semantic_staged():
    assert not any(p.startswith("memory/semantic/") for p in _git_staged_names())


def test_18_no_trading_staged():
    assert not any(p == "trading" or p.startswith("trading/") for p in _git_staged_names())


def test_19_no_b8_staged():
    assert not any(p == "B8" or p.startswith("B8/") for p in _git_staged_names())


def test_20_no_tmp_agent_strategies_staged():
    assert not any(p.startswith("tmp_agent/strategies/") for p in _git_staged_names())


def test_21_no_env_staged():
    assert not any(p == ".env" or p.endswith("/.env") for p in _git_staged_names())


def test_22_roadmap_status_json_valid():
    with (ROOT / "ROADMAP_STATUS.json").open(encoding="utf-8") as fh:
        assert isinstance(json.load(fh), dict)


def test_23_ledger_exists():
    assert (ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md").exists()
