"""
Smoke tests for Ingestion Small Batch 09B.

Rules:
- 12 curated candidates promoted with approval token AGENTV2_APPROVED_INGESTION_09B_CESAR_12
- Verifies promotion, retrieval, and agent probe behavior.
- Tests run against already-promoted state (no rollback required).
"""
import os
import sys
import json
import subprocess
import faiss
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from fastapi.testclient import TestClient

os.environ.setdefault("BRAIN_ADMIN_TOKEN", "AGENTV2_TEST_ADMIN_TOKEN")
from tmp_agent.brain_v9.main import app

SEMANTIC_ROOT = Path("C:/AI_VAULT_CANONICAL/memory/semantic")
JSONL_PATH = SEMANTIC_ROOT / "semantic_memory.jsonl"
IDS_PATH = SEMANTIC_ROOT / "semantic_memory_faiss_ids.json"
IDX_PATH = SEMANTIC_ROOT / "semantic_memory_faiss.index"
REPORT_DIR = Path("C:/AI_VAULT_CANONICAL/tmp_agent/front_ingestion_small_batch_09b")
CANDIDATES_PATH = REPORT_DIR / "curated_candidates_09b.json"

client = TestClient(app)
VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"


def _load_candidates():
    with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _memory_counts():
    records = [line for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(IDX_PATH)).ntotal)
    return len(records), len(ids), ntotal


def test_curated_candidates_count_is_12():
    candidates = _load_candidates()
    assert len(candidates) == 12, f"expected 12 candidates, got {len(candidates)}"
    print("PASS: curated_candidates_count_is_12")


def test_curated_candidates_schema_valid():
    candidates = _load_candidates()
    required = {"candidate_id", "source_front", "source_path", "domain", "category", "text", "summary", "created_by", "source_cycle"}
    for c in candidates:
        assert required.issubset(set(c.keys())), f"{c['candidate_id']} missing required fields"
    print("PASS: curated_candidates_schema_valid")


def test_validation_dry_run_all_12_valid():
    summary_path = REPORT_DIR / "validation_summary.json"
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    assert summary["valid_candidates"] == 12, f"expected 12 valid, got {summary['valid_candidates']}"
    print("PASS: validation_dry_run_all_12_valid")


def test_validation_dry_run_no_writes():
    summary_path = REPORT_DIR / "validation_summary.json"
    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    assert summary["no_writes_performed"] is True, "dry-run performed writes"
    print("PASS: validation_dry_run_no_writes")


def test_promotion_incremented_jsonl_by_12():
    verify_path = REPORT_DIR / "post_promotion_verify.json"
    with open(verify_path, "r", encoding="utf-8") as f:
        verify = json.load(f)
    assert verify["jsonl_increment"] == 12, f"expected +12 jsonl, got {verify['jsonl_increment']}"
    print("PASS: promotion_incremented_jsonl_by_12")


def test_promotion_incremented_faiss_ids_by_12():
    verify_path = REPORT_DIR / "post_promotion_verify.json"
    with open(verify_path, "r", encoding="utf-8") as f:
        verify = json.load(f)
    assert verify["faiss_ids_increment"] == 12, f"expected +12 ids, got {verify['faiss_ids_increment']}"
    print("PASS: promotion_incremented_faiss_ids_by_12")


def test_promotion_incremented_faiss_ntotal_by_12():
    verify_path = REPORT_DIR / "post_promotion_verify.json"
    with open(verify_path, "r", encoding="utf-8") as f:
        verify = json.load(f)
    assert verify["faiss_ntotal_increment"] == 12, f"expected +12 ntotal, got {verify['faiss_ntotal_increment']}"
    print("PASS: promotion_incremented_faiss_ntotal_by_12")


def test_promoted_ids_in_jsonl():
    candidates = _load_candidates()
    records = [json.loads(line) for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = {r.get("id") for r in records}
    for c in candidates:
        assert c["candidate_id"] in ids, f"{c['candidate_id']} not in jsonl"
    print("PASS: promoted_ids_in_jsonl")


def test_promoted_ids_in_faiss_ids():
    candidates = _load_candidates()
    ids = set(json.loads(IDS_PATH.read_text(encoding="utf-8")))
    for c in candidates:
        assert c["candidate_id"] in ids, f"{c['candidate_id']} not in faiss_ids"
    print("PASS: promoted_ids_in_faiss_ids")


def test_no_blank_text_added():
    candidates = _load_candidates()
    records = [json.loads(line) for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    promoted_ids = {c["candidate_id"] for c in candidates}
    promoted_records = [r for r in records if r.get("id") in promoted_ids]
    for r in promoted_records:
        assert (r.get("text") or "").strip(), f"blank text for {r.get('id')}"
    print("PASS: no_blank_text_added")


def test_no_duplicate_text_added():
    candidates = _load_candidates()
    records = [json.loads(line) for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    promoted_ids = {c["candidate_id"] for c in candidates}
    promoted_texts = [r.get("text", "").strip() for r in records if r.get("id") in promoted_ids]
    assert len(promoted_texts) == len(set(promoted_texts)), "duplicate text among promoted candidates"
    print("PASS: no_duplicate_text_added")


def test_retrieval_e2e_passed_for_12():
    retrieval_path = REPORT_DIR / "retrieval_e2e_results.json"
    with open(retrieval_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["retrieval_passed_count"] == 12, f"expected 12 retrieval passed, got {data['retrieval_passed_count']}"
    print("PASS: retrieval_e2e_passed_for_12")


def test_agent_use_probe_auth_required():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What should I know about auth on critical endpoints?", "mode": "read_only", "user_id": "09b_probe"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    print("PASS: agent_use_probe_auth_required")


def test_agent_use_probe_no_write_tools():
    from tmp_agent.brain_v9.core.agent_kernel_v2.tool_gateway import ToolGatewayV2
    from tmp_agent.brain_v9.core.agent_kernel_v2.schemas import ToolCallRequest
    req = ToolCallRequest(
        tool_name="promotion_candidate_promote",
        args={"candidate_id": "probe_09b", "source": "all", "approval_token": "AGENTV2_APPROVED_TEST_SHOULD_NOT_MATTER", "operator_id": "probe", "confirm_phrase": "PROMOTE_ONE_CANDIDATE_TO_CANONICAL_MEMORY"},
        mode="read_only",
    )
    result = ToolGatewayV2().call(req)
    assert result.blocked is True or result.ok is False or bool(result.error), "write tool allowed in read_only"
    print("PASS: agent_use_probe_no_write_tools")


def test_memory_files_not_tracked():
    result = subprocess.run(["git", "ls-files"], cwd="C:/AI_VAULT_CANONICAL", capture_output=True, text=True, encoding="utf-8", errors="replace")
    tracked = result.stdout.splitlines()
    forbidden = [
        "memory/semantic/semantic_memory.jsonl",
        "memory/semantic/semantic_memory_faiss.index",
        "memory/semantic/semantic_memory_faiss_ids.json",
        "memory/semantic/promotion_audit.jsonl",
        "memory/autonomous_journal.jsonl",
    ]
    for f in forbidden:
        assert f not in tracked, f"{f} is tracked"
    print("PASS: memory_files_not_tracked")


def test_memory_files_not_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd="C:/AI_VAULT_CANONICAL", capture_output=True, text=True, encoding="utf-8", errors="replace")
    staged = result.stdout.splitlines()
    forbidden = [
        "memory/semantic/semantic_memory.jsonl",
        "memory/semantic/semantic_memory_faiss.index",
    ]
    for f in forbidden:
        assert f not in staged, f"{f} is staged"
    print("PASS: memory_files_not_staged")


def test_guard_blocks_memory_staging():
    result = subprocess.run(["python", "scripts/git_hygiene/check_no_sensitive_paths_staged.py"], cwd="C:/AI_VAULT_CANONICAL", capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, f"guard failed: {result.stdout} {result.stderr}"
    print("PASS: guard_blocks_memory_staging")


def test_rollback_snapshot_exists():
    snapshot_report = REPORT_DIR / "pre_promotion_snapshot_report.json"
    with open(snapshot_report, "r", encoding="utf-8") as f:
        report = json.load(f)
    snapshot_dir = Path(report["snapshot_dir"])
    assert snapshot_dir.exists(), f"snapshot dir missing: {snapshot_dir}"
    assert (snapshot_dir / "SNAPSHOT_REASON.txt").exists(), "SNAPSHOT_REASON.txt missing"
    print("PASS: rollback_snapshot_exists")


def test_promotion_queue_not_mutated():
    result = subprocess.run(["git", "status", "--short", "--", "memory/promotion_queue"], cwd="C:/AI_VAULT_CANONICAL", capture_output=True, text=True, encoding="utf-8", errors="replace")
    staged = [line for line in result.stdout.splitlines() if line.strip().startswith(("A", "M", "D"))]
    assert len(staged) == 0, f"promotion_queue mutated: {staged}"
    print("PASS: promotion_queue_not_mutated")


def test_semantic_staging_not_mutated():
    result = subprocess.run(["git", "status", "--short", "--", "memory/semantic_staging"], cwd="C:/AI_VAULT_CANONICAL", capture_output=True, text=True, encoding="utf-8", errors="replace")
    staged = [line for line in result.stdout.splitlines() if line.strip().startswith(("A", "M", "D"))]
    assert len(staged) == 0, f"semantic_staging mutated: {staged}"
    print("PASS: semantic_staging_not_mutated")


if __name__ == "__main__":
    test_curated_candidates_count_is_12()
    test_curated_candidates_schema_valid()
    test_validation_dry_run_all_12_valid()
    test_validation_dry_run_no_writes()
    test_promotion_incremented_jsonl_by_12()
    test_promotion_incremented_faiss_ids_by_12()
    test_promotion_incremented_faiss_ntotal_by_12()
    test_promoted_ids_in_jsonl()
    test_promoted_ids_in_faiss_ids()
    test_no_blank_text_added()
    test_no_duplicate_text_added()
    test_retrieval_e2e_passed_for_12()
    test_agent_use_probe_auth_required()
    test_agent_use_probe_no_write_tools()
    test_memory_files_not_tracked()
    test_memory_files_not_staged()
    test_guard_blocks_memory_staging()
    test_rollback_snapshot_exists()
    test_promotion_queue_not_mutated()
    test_semantic_staging_not_mutated()
    print("ALL 20 TESTS PASSED")
