# Promotion Pipeline Adapter Dry-Run Smoke Tests for Agent V2
import sys
import hashlib
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")

from tmp_agent.brain_v9.memory.promotion_pipeline_adapter import (
    PromotionPipelineAdapter,
    normalize_candidate,
    validate_candidate,
    dry_run_promotion,
)

SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
JSONL_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
IDX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _memory_shas():
    return {
        "jsonl": _sha256(JSONL_PATH),
        "index": _sha256(IDX_PATH),
        "ids": _sha256(IDS_PATH),
    }


def test_promotion_queue_candidates_load():
    adapter = PromotionPipelineAdapter()
    candidates = adapter.load_candidates("promotion_queue")
    assert len(candidates) > 0, "no promotion_queue candidates loaded"
    print("PASS: promotion_queue_candidates_load")


def test_semantic_staging_candidates_load():
    adapter = PromotionPipelineAdapter()
    candidates = adapter.load_candidates("semantic_staging")
    assert len(candidates) > 0, "no semantic_staging candidates loaded"
    print("PASS: semantic_staging_candidates_load")


def test_normalize_candidate_has_required_fields():
    raw = {
        "candidate_id": "test_123",
        "text": "sample memory text",
        "summary": "summary",
        "domain": "brain_architecture",
        "category": "lesson",
        "confidence": 0.85,
        "source_cycle": "cycle_1",
        "evidence_path": "some/path.json",
    }
    norm = normalize_candidate(raw, "memory/promotion_queue/test_123.json")
    for key in ["candidate_id", "text", "source_path", "source_bucket", "hash"]:
        assert key in norm, f"missing {key}"
    assert norm["source_bucket"] == "promotion_queue"
    print("PASS: normalize_candidate_has_required_fields")


def test_validate_candidate_rejects_blank_text():
    raw = {"candidate_id": "blank", "text": "   "}
    norm = normalize_candidate(raw, "memory/promotion_queue/blank.json")
    v = validate_candidate(norm)
    assert not v["valid"]
    assert "blank_text" in v["validation_errors"]
    print("PASS: validate_candidate_rejects_blank_text")


def test_validate_candidate_rejects_raw_cot():
    raw = {"candidate_id": "cot", "text": "lesson", "raw_cot_exposed": True}
    norm = normalize_candidate(raw, "memory/promotion_queue/cot.json")
    v = validate_candidate(norm)
    assert not v["valid"]
    assert "raw_cot_exposed" in v["validation_errors"]
    print("PASS: validate_candidate_rejects_raw_cot")


def test_validate_candidate_rejects_secrets():
    raw = {"candidate_id": "sec", "text": "lesson", "secrets_exposed": True}
    norm = normalize_candidate(raw, "memory/promotion_queue/sec.json")
    v = validate_candidate(norm)
    assert not v["valid"]
    assert "secrets_exposed" in v["validation_errors"]
    print("PASS: validate_candidate_rejects_secrets")


def test_dry_run_does_not_write_memory():
    adapter = PromotionPipelineAdapter()
    before = _memory_shas()
    candidates = adapter.load_candidates("promotion_queue")
    assert candidates
    result = adapter.dry_run_promotion(candidates[0]["candidate_id"])
    assert result["write_performed"] is False
    after = _memory_shas()
    assert before["jsonl"] == after["jsonl"]
    assert before["index"] == after["index"]
    assert before["ids"] == after["ids"]
    print("PASS: dry_run_does_not_write_memory")


def test_dry_run_returns_write_performed_false():
    adapter = PromotionPipelineAdapter()
    candidates = adapter.load_candidates("promotion_queue")
    assert candidates
    result = adapter.dry_run_promotion(candidates[0]["candidate_id"])
    assert result["would_write_jsonl"] is False
    assert result["would_write_faiss"] is False
    assert result["write_performed"] is False
    assert result["would_require_human_approval"] is True
    print("PASS: dry_run_returns_write_performed_false")


def test_duplicate_detection_exact_text():
    import json
    with JSONL_PATH.open("r", encoding="utf-8") as fh:
        first_line = next(line for line in fh if line.strip())
    rec = json.loads(first_line)
    raw = {"candidate_id": "dup", "text": rec.get("text", "")}
    norm = normalize_candidate(raw, "memory/promotion_queue/dup.json")
    v = validate_candidate(norm)
    assert v["duplicate_exact"] is True
    print("PASS: duplicate_detection_exact_text")


def test_adapter_does_not_import_old_semantic_memory_writer():
    import inspect
    import tmp_agent.brain_v9.memory.promotion_pipeline_adapter as adapter_module
    source = inspect.getsource(adapter_module)
    assert "get_semantic_memory" not in source
    assert ".ingest_text" not in source
    assert "semantic_memory_index.npz" not in source
    print("PASS: adapter_does_not_import_old_semantic_memory_writer")


def test_tool_gateway_has_promotion_candidate_validate():
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    gw = ToolGatewayV2()
    caps = {c["name"] for c in gw.list_capabilities()}
    assert "promotion_candidate_validate" in caps
    print("PASS: tool_gateway_has_promotion_candidate_validate")


if __name__ == "__main__":
    test_promotion_queue_candidates_load()
    test_semantic_staging_candidates_load()
    test_normalize_candidate_has_required_fields()
    test_validate_candidate_rejects_blank_text()
    test_validate_candidate_rejects_raw_cot()
    test_validate_candidate_rejects_secrets()
    test_dry_run_does_not_write_memory()
    test_dry_run_returns_write_performed_false()
    test_duplicate_detection_exact_text()
    test_adapter_does_not_import_old_semantic_memory_writer()
    test_tool_gateway_has_promotion_candidate_validate()
    print("ALL ADAPTER SMOKE TESTS PASSED")
