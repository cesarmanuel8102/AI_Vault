"""
Smoke tests for the write-gated promotion candidate tool.

Rules:
- All successful promotion tests rollback canonical memory to baseline.
- No real promotion_queue or semantic_staging files are mutated.
- Synthetic candidates are written to a temp directory, never to real queues.
"""
import sys
import hashlib
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
from tmp_agent.brain_v9.memory.promotion_candidate_promoter import (
    promote_candidate,
    rollback_promotion,
    _sha_optional,
    _faiss_ntotal,
)

SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
JSONL_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
IDX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
AUDIT_PATH = SEMANTIC_ROOT / "promotion_audit.jsonl"

DUP_CANDIDATE_ID = "codex_pure_brain_training_autonomy_dashboard_visual_trace_self_improvement_governance_training_1"
APPROVAL_TOKEN = "AGENTV2_APPROVED_08B_TEST"
CONFIRM = "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_jsonl_ids():
    if not IDS_PATH.exists():
        return []
    try:
        data = json.loads(IDS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _build_synthetic_candidate(candidate_id: str, text: str):
    return {
        "candidate_id": candidate_id,
        "text": text,
        "summary": text,
        "domain": "brain_architecture",
        "canonical_domain": "brain_architecture",
        "category": "test_promotion",
        "confidence": 0.92,
        "quality_score": 0.91,
        "usefulness_score": 0.90,
        "safety_score": 0.99,
        "terminal_status": "approved_for_canonical_promotion",
        "staging_status": "unknown",
        "canonical_promotion": True,
        "review_required": False,
        "raw_cot_exposed": False,
        "secrets_exposed": False,
        "trading_execution_detected": False,
        "source_cycle": "test_08b_cycle",
        "source_metadata": {"cycle_id": "test_08b_cycle", "external_source": False, "front": "08B_TEST"},
        "evidence_path": "",
        "created_utc": "2026-06-25T00:00:00Z",
    }


def _install_synthetic_candidate(candidate_id: str, text: str) -> Path:
    """Install a synthetic candidate in a temp promotion_queue dir for load_candidates."""
    tmpdir = Path("C:/AI_VAULT_CANONICAL/tests/.tmp_08b")
    tmpdir.mkdir(parents=True, exist_ok=True)
    # Clean previous temp candidates to avoid ID collisions
    for p in tmpdir.glob("test_promote_08b_*.json"):
        p.unlink()
    path = tmpdir / f"{candidate_id}.json"
    path.write_text(json.dumps(_build_synthetic_candidate(candidate_id, text), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _all_memory_shas():
    return {
        "jsonl": _sha_optional(JSONL_PATH),
        "index": _sha_optional(IDX_PATH),
        "ids": _sha_optional(IDS_PATH),
    }


def _text_exists_in_canonical(text: str) -> bool:
    target = text.strip()
    if not JSONL_PATH.exists():
        return False
    for line in JSONL_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if str(rec.get("text", "")).strip() == target:
                return True
        except Exception:
            continue
    return False


def test_tool_gateway_has_promotion_candidate_promote():
    caps = {c["name"] for c in ToolGatewayV2().list_capabilities()}
    assert "promotion_candidate_promote" in caps
    print("PASS: tool_gateway_has_promotion_candidate_promote")


def test_promote_rejects_read_only_mode():
    before = _all_memory_shas()
    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": DUP_CANDIDATE_ID, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM},
        mode="read_only",
    ))
    result = res.result
    assert res.blocked is True
    assert result["promotion_performed"] is False
    assert result["write_performed"] is False
    assert "read_only_mode_blocked" in result["validation_errors"]
    assert _all_memory_shas() == before
    print("PASS: promote_rejects_read_only_mode")


def test_promote_rejects_missing_approval_token():
    before = _all_memory_shas()
    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": DUP_CANDIDATE_ID, "source": "promotion_queue", "approval_token": "", "operator_id": "cesar", "confirm_phrase": CONFIRM},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is False
    assert result["write_performed"] is False
    assert "approval_token_invalid" in result["validation_errors"]
    assert _all_memory_shas() == before
    print("PASS: promote_rejects_missing_approval_token")


def test_promote_rejects_missing_confirm_phrase():
    before = _all_memory_shas()
    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": DUP_CANDIDATE_ID, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": "WRONG"},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is False
    assert result["write_performed"] is False
    assert "confirm_phrase_mismatch" in result["validation_errors"]
    assert _all_memory_shas() == before
    print("PASS: promote_rejects_missing_confirm_phrase")


def test_promote_rejects_duplicate_candidate():
    before = _all_memory_shas()
    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": DUP_CANDIDATE_ID, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is False
    assert result["write_performed"] is False
    assert "duplicate_exact_text_in_canonical_memory" in result["validation_errors"]
    assert _all_memory_shas() == before
    print("PASS: promote_rejects_duplicate_candidate")


def _safety_rejection_test(flag: str, expected_error: str):
    before = _all_memory_shas()
    candidate_id = f"test_promote_08b_{flag}_{int(time.time())}"
    cand = _build_synthetic_candidate(candidate_id, f"Unique text for {flag} rejection test {time.time()}")
    cand[flag] = True
    tmpdir = Path("C:/AI_VAULT_CANONICAL/tests/.tmp_08b")
    tmpdir.mkdir(parents=True, exist_ok=True)
    path = tmpdir / f"{candidate_id}.json"
    path.write_text(json.dumps(cand, ensure_ascii=False, indent=2), encoding="utf-8")

    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": candidate_id, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM, "queue_dir": str(tmpdir)},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is False
    assert result["write_performed"] is False
    assert expected_error in result["validation_errors"]
    assert _all_memory_shas() == before
    path.unlink(missing_ok=True)
    return result


def test_promote_rejects_raw_cot():
    _safety_rejection_test("raw_cot_exposed", "raw_cot_exposed")
    print("PASS: promote_rejects_raw_cot")


def test_promote_rejects_secrets():
    _safety_rejection_test("secrets_exposed", "secrets_exposed")
    print("PASS: promote_rejects_secrets")


def test_promote_rejects_trading_execution():
    _safety_rejection_test("trading_execution_detected", "trading_execution_detected")
    print("PASS: promote_rejects_trading_execution")


def test_promote_creates_snapshot_before_write():
    before = _all_memory_shas()
    candidate_id = f"test_promote_08b_snapshot_{int(time.time())}"
    text = f"Unique snapshot test memory content {time.time()} {hashlib.sha256(str(time.time()).encode()).hexdigest()}"
    path = _install_synthetic_candidate(candidate_id, text)
    tmpdir = path.parent

    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": candidate_id, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM, "queue_dir": str(tmpdir)},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is True
    assert result["snapshot_created"] is True
    assert Path(result["snapshot_path"]).exists()
    assert result["rollback_possible"] is True

    # Rollback to restore baseline
    rb = rollback_promotion(result["snapshot_path"])
    assert rb["ok"] is True
    assert _all_memory_shas() == before
    path.unlink(missing_ok=True)
    print("PASS: promote_creates_snapshot_before_write")


def test_promote_appends_exactly_one_jsonl_record():
    before = _all_memory_shas()
    candidate_id = f"test_promote_08b_jsonl_{int(time.time())}"
    text = f"Unique jsonl test memory content {time.time()} {hashlib.sha256(str(time.time()).encode()).hexdigest()}"
    path = _install_synthetic_candidate(candidate_id, text)
    tmpdir = path.parent

    before_count = sum(1 for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()) if JSONL_PATH.exists() else 0
    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": candidate_id, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM, "queue_dir": str(tmpdir)},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is True
    after_count = sum(1 for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip())
    assert after_count == before_count + 1

    # Rollback
    rb = rollback_promotion(result["snapshot_path"])
    assert rb["ok"] is True
    assert _all_memory_shas() == before
    path.unlink(missing_ok=True)
    print("PASS: promote_appends_exactly_one_jsonl_record")


def test_promote_updates_faiss_and_increments_count_by_one():
    before = _all_memory_shas()
    candidate_id = f"test_promote_08b_faiss_{int(time.time())}"
    text = f"Unique FAISS test memory content {time.time()} {hashlib.sha256(str(time.time()).encode()).hexdigest()}"
    path = _install_synthetic_candidate(candidate_id, text)
    tmpdir = path.parent

    before_ids_count = len(_load_jsonl_ids())
    before_ntotal = _faiss_ntotal()

    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": candidate_id, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM, "queue_dir": str(tmpdir)},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is True
    assert result["faiss_ids_after_count"] == before_ids_count + 1
    assert result["faiss_ntotal_after"] == before_ntotal + 1

    rb = rollback_promotion(result["snapshot_path"])
    assert rb["ok"] is True
    assert _all_memory_shas() == before
    path.unlink(missing_ok=True)
    print("PASS: promote_updates_faiss_and_increments_count_by_one")


def test_promote_appends_audit():
    before = _all_memory_shas()
    audit_before = AUDIT_PATH.read_bytes() if AUDIT_PATH.exists() else b""
    candidate_id = f"test_promote_08b_audit_{int(time.time())}"
    text = f"Unique audit test memory content {time.time()} {hashlib.sha256(str(time.time()).encode()).hexdigest()}"
    path = _install_synthetic_candidate(candidate_id, text)
    tmpdir = path.parent

    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": candidate_id, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM, "queue_dir": str(tmpdir)},
        mode="build",
    ))
    result = res.result
    assert result["audit_appended"] is True
    assert AUDIT_PATH.exists()
    audit_lines = [line for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    last_audit = json.loads(audit_lines[-1])
    assert last_audit["event"] == "canonical_promotion"
    assert last_audit["candidate_id"] == candidate_id

    rb = rollback_promotion(result["snapshot_path"])
    assert rb["ok"] is True
    assert _all_memory_shas() == before
    path.unlink(missing_ok=True)
    print("PASS: promote_appends_audit")


def test_promote_retrievable_after_write():
    before = _all_memory_shas()
    candidate_id = f"test_promote_08b_retrieve_{int(time.time())}"
    text = f"Unique retrieval test memory content {time.time()} {hashlib.sha256(str(time.time()).encode()).hexdigest()}"
    path = _install_synthetic_candidate(candidate_id, text)
    tmpdir = path.parent

    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": candidate_id, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM, "queue_dir": str(tmpdir)},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is True

    from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
    mem = get_semantic_memory_faiss()
    hits = mem.search(text, top_k=5, min_score=0.1)
    hit_ids = {str(h.get("id")) for h in hits}
    assert result["semantic_record_id"] in hit_ids

    rb = rollback_promotion(result["snapshot_path"])
    assert rb["ok"] is True
    assert _all_memory_shas() == before
    path.unlink(missing_ok=True)
    print("PASS: promote_retrievable_after_write")


def test_rollback_restores_previous_memory_state():
    before = _all_memory_shas()
    before_ntotal = _faiss_ntotal()
    before_ids_count = len(_load_jsonl_ids())
    before_jsonl_count = sum(1 for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()) if JSONL_PATH.exists() else 0

    candidate_id = f"test_promote_08b_rollback_{int(time.time())}"
    text = f"Unique rollback test memory content {time.time()} {hashlib.sha256(str(time.time()).encode()).hexdigest()}"
    path = _install_synthetic_candidate(candidate_id, text)
    tmpdir = path.parent

    res = ToolGatewayV2().call(ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": candidate_id, "source": "promotion_queue", "approval_token": APPROVAL_TOKEN, "operator_id": "cesar", "confirm_phrase": CONFIRM, "queue_dir": str(tmpdir)},
        mode="build",
    ))
    result = res.result
    assert result["promotion_performed"] is True

    # Rollback
    rb = rollback_promotion(result["snapshot_path"])
    assert rb["ok"] is True

    assert _sha_optional(JSONL_PATH) == before["jsonl"]
    assert _sha_optional(IDX_PATH) == before["index"]
    assert _sha_optional(IDS_PATH) == before["ids"]
    assert _faiss_ntotal() == before_ntotal
    assert len(_load_jsonl_ids()) == before_ids_count
    assert sum(1 for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()) == before_jsonl_count
    assert not _text_exists_in_canonical(text)

    path.unlink(missing_ok=True)
    print("PASS: rollback_restores_previous_memory_state")


def test_no_old_semantic_memory_index_used():
    import inspect
    import tmp_agent.brain_v9.memory.promotion_candidate_promoter as promoter
    import tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway as gateway
    promoter_src = inspect.getsource(promoter)
    gateway_src = inspect.getsource(gateway)
    assert "semantic_memory_index.npz" not in promoter_src
    assert "semantic_memory_index.npz" not in gateway_src
    assert "get_semantic_memory_faiss" in promoter_src
    print("PASS: no_old_semantic_memory_index_used")


def test_e2e_promotion_requires_write_mode_and_approval():
    import requests
    base = "http://127.0.0.1:8091"
    q = "promociona el candidato test_promote_08b_e2e a memoria canonical con aprobacion"
    r = requests.post(
        f"{base}/v2/chat/agent",
        json={"message": q, "mode": "read_only", "user_id": "test_08b_e2e"},
        timeout=120,
    )
    data = r.json()
    run_id = data["run_id"]
    trace = requests.get(f"{base}/v2/agent/runs/{run_id}/trace", timeout=30).json()
    tool_events = [e for e in trace.get("trace", []) if e.get("event_type", "").startswith("tool_call_")]
    executed_tools = {e.get("data", {}).get("tool") for e in tool_events}
    assert "promotion_candidate_promote" not in executed_tools
    # Should not have promoted
    assert data.get("mode_effective") == "read_only"
    print("PASS: e2e_promotion_requires_write_mode_and_approval")


def test_read_only_chat_request_cannot_promote():
    import requests
    base = "http://127.0.0.1:8091"
    q = "promociona el candidato test_promote_08b_chat a memoria canonical"
    r = requests.post(
        f"{base}/v2/chat/agent",
        json={"message": q, "mode": "read_only", "user_id": "test_08b_chat_readonly"},
        timeout=120,
    )
    data = r.json()
    assert data["ok"] is True
    assert data["mode_effective"] == "read_only"
    run_id = data["run_id"]
    trace = requests.get(f"{base}/v2/agent/runs/{run_id}/trace", timeout=30).json()
    tool_events = [e for e in trace.get("trace", []) if e.get("event_type", "").startswith("tool_call_")]
    executed_tools = {e.get("data", {}).get("tool") for e in tool_events}
    assert "promotion_candidate_promote" not in executed_tools
    final = data["final_answer"].lower()
    assert "read_only" in final or "solo lectura" in final or "approval" in final or "aprobacion" in final or "dry-run" in final or "validate" in final
    print("PASS: read_only_chat_request_cannot_promote")


if __name__ == "__main__":
    test_tool_gateway_has_promotion_candidate_promote()
    test_promote_rejects_read_only_mode()
    test_promote_rejects_missing_approval_token()
    test_promote_rejects_missing_confirm_phrase()
    test_promote_rejects_duplicate_candidate()
    test_promote_rejects_raw_cot()
    test_promote_rejects_secrets()
    test_promote_rejects_trading_execution()
    test_promote_creates_snapshot_before_write()
    test_promote_appends_exactly_one_jsonl_record()
    test_promote_updates_faiss_and_increments_count_by_one()
    test_promote_appends_audit()
    test_promote_retrievable_after_write()
    test_rollback_restores_previous_memory_state()
    test_no_old_semantic_memory_index_used()
    test_e2e_promotion_requires_write_mode_and_approval()
    test_read_only_chat_request_cannot_promote()
    print("ALL 08B PROMOTION TOOL TESTS PASSED")
