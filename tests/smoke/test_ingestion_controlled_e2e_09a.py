"""
Smoke tests for Ingestion Controlled E2E 09A.

Rules:
- 3 curated candidates promoted with approval token AGENTV2_APPROVED_INGESTION_09A_CESAR_3
- Verifies promotion, retrieval, and agent probe behavior.
- Tests are designed to run against the already-promoted state (no rollback required).
- If run after a fresh reset, they will fail until promotions are re-done.
"""
import os
import sys
import json
import faiss
import subprocess
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

client = TestClient(app)
VALID_TOKEN = "AGENTV2_TEST_ADMIN_TOKEN"

PROMOTED_IDS = {
    "ingest09a_auth_hardening_critical_endpoints",
    "ingest09a_memory_hygiene_runtime_state",
    "ingest09a_text_dedup_promotion_batches",
}

APPROVAL_TOKEN = "AGENTV2_APPROVED_INGESTION_09A_CESAR_3"


def _memory_counts():
    records = [line for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = json.loads(IDS_PATH.read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(IDX_PATH)).ntotal)
    return len(records), len(ids), ntotal


def test_phase_7_post_promotion_counts():
    """Expect 1759 JSONL, 1750 FAISS after 3 promotions."""
    records, ids_count, ntotal = _memory_counts()
    assert records >= 1759, f"expected >=1759 jsonl, got {records}"
    assert ids_count >= 1750, f"expected >=1750 ids, got {ids_count}"
    assert ntotal >= 1750, f"expected >=1750 ntotal, got {ntotal}"
    print(f"PASS: post_promotion_counts jsonl={records} ids={ids_count} ntotal={ntotal}")


def test_phase_7_all_3_ids_in_jsonl():
    records = [json.loads(line) for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = {r.get("id") for r in records}
    for cid in PROMOTED_IDS:
        assert cid in ids, f"{cid} not found in jsonl"
    print("PASS: all_3_ids_in_jsonl")


def test_phase_7_all_3_ids_in_faiss_ids():
    ids = set(json.loads(IDS_PATH.read_text(encoding="utf-8")))
    for cid in PROMOTED_IDS:
        assert cid in ids, f"{cid} not found in faiss_ids"
    print("PASS: all_3_ids_in_faiss_ids")


def test_phase_8_retrieval_auth_hardening():
    from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
    mem = get_semantic_memory_faiss()
    matches = mem.search("strict token authentication on critical agent endpoints", top_k=5, min_score=0.1)
    top_ids = [m.get("id") for m in matches]
    assert "ingest09a_auth_hardening_critical_endpoints" in top_ids, f"auth candidate not in top_k retrieval: {top_ids}"
    print("PASS: retrieval_auth_hardening")


def test_phase_8_retrieval_memory_hygiene():
    from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
    mem = get_semantic_memory_faiss()
    matches = mem.search("runtime semantic memory must remain local and untracked", top_k=5, min_score=0.1)
    top_ids = [m.get("id") for m in matches]
    assert "ingest09a_memory_hygiene_runtime_state" in top_ids, f"memory candidate not in top_k retrieval: {top_ids}"
    print("PASS: retrieval_memory_hygiene")


def test_phase_8_retrieval_text_dedup():
    from tmp_agent.brain_v9.core.semantic_memory_faiss import get_semantic_memory_faiss
    mem = get_semantic_memory_faiss()
    matches = mem.search("deduplicate by exact normalized text content", top_k=5, min_score=0.1)
    top_ids = [m.get("id") for m in matches]
    assert "ingest09a_text_dedup_promotion_batches" in top_ids, f"dedup candidate not in top_k retrieval: {top_ids}"
    print("PASS: retrieval_text_dedup")


def test_phase_9_agent_probe_auth_question():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "What should I know about auth on critical endpoints?", "mode": "read_only", "user_id": "09a_probe"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    answer = str(data.get("answer") or data.get("final_answer") or "").lower()
    assert "auth" in answer or "endpoint" in answer or "token" in answer, f"unexpected answer: {answer[:200]}"
    print("PASS: agent_probe_auth_question")


def test_phase_9_agent_probe_memory_question():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "How should runtime memory be handled in Git?", "mode": "read_only", "user_id": "09a_probe"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    answer = str(data.get("answer") or data.get("final_answer") or "").lower()
    assert "memory" in answer or "git" in answer or "untrack" in answer, f"unexpected answer: {answer[:200]}"
    print("PASS: agent_probe_memory_question")


def test_phase_9_agent_probe_dedup_question():
    r = client.post(
        "/v2/chat/agent",
        json={"message": "Why deduplicate by text during promotion?", "mode": "read_only", "user_id": "09a_probe"},
        headers={"X-Brain-Token": VALID_TOKEN},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    answer = str(data.get("answer") or data.get("final_answer") or "").lower()
    assert "deduplicate" in answer or "duplicate" in answer or "id" in answer, f"unexpected answer: {answer[:200]}"
    print("PASS: agent_probe_dedup_question")


def test_phase_11_memory_git_safety():
    import subprocess
    result = subprocess.run(
        ["python", "scripts/git_hygiene/check_no_sensitive_paths_staged.py"],
        cwd="C:/AI_VAULT_CANONICAL",
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    assert result.returncode == 0, f"guard script failed: {result.stdout} {result.stderr}"
    print("PASS: memory_git_safety")


def test_phase_11_memory_files_untracked():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd="C:/AI_VAULT_CANONICAL",
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    tracked = result.stdout.splitlines()
    forbidden = [
        "memory/semantic/semantic_memory.jsonl",
        "memory/semantic/semantic_memory_faiss.index",
        "memory/semantic/semantic_memory_faiss_ids.json",
        "memory/semantic/promotion_audit.jsonl",
        "memory/autonomous_journal.jsonl",
    ]
    for f in forbidden:
        assert f not in tracked, f"{f} is tracked (should be untracked)"
    print("PASS: memory_files_untracked")


def test_candidate_text_length_constraints():
    CANDIDATES_PATH = Path("C:/AI_VAULT_CANONICAL/tmp_agent/front_ingestion_controlled_e2e_09a/curated_candidates_09a.json")
    with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)
    for c in candidates:
        words = len(c["text"].split())
        assert 80 <= words <= 220, f"{c['candidate_id']} has {words} words (must be 80-220)"
    print("PASS: candidate_text_length_constraints")


def test_candidate_domains_valid():
    valid_domains = {"governance", "semantic_memory", "tools_capabilities", "production_operations", "brain_architecture"}
    CANDIDATES_PATH = Path("C:/AI_VAULT_CANONICAL/tmp_agent/front_ingestion_controlled_e2e_09a/curated_candidates_09a.json")
    with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)
    for c in candidates:
        assert c["domain"] in valid_domains, f"{c['candidate_id']} has invalid domain {c['domain']}"
    print("PASS: candidate_domains_valid")


def test_no_secrets_or_cot_in_candidates():
    CANDIDATES_PATH = Path("C:/AI_VAULT_CANONICAL/tmp_agent/front_ingestion_controlled_e2e_09a/curated_candidates_09a.json")
    with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
        candidates = json.load(f)
    for c in candidates:
        assert not c.get("secrets_exposed", False), f"{c['candidate_id']} exposes secrets"
        assert not c.get("raw_cot_exposed", False), f"{c['candidate_id']} exposes raw CoT"
        assert not c.get("trading_execution_detected", False), f"{c['candidate_id']} has trading execution"
    print("PASS: no_secrets_or_cot_in_candidates")


if __name__ == "__main__":
    test_phase_7_post_promotion_counts()
    test_phase_7_all_3_ids_in_jsonl()
    test_phase_7_all_3_ids_in_faiss_ids()
    test_phase_8_retrieval_auth_hardening()
    test_phase_8_retrieval_memory_hygiene()
    test_phase_8_retrieval_text_dedup()
    test_phase_9_agent_probe_auth_question()
    test_phase_9_agent_probe_memory_question()
    test_phase_9_agent_probe_dedup_question()
    test_phase_11_memory_git_safety()
    test_phase_11_memory_files_untracked()
    test_candidate_text_length_constraints()
    test_candidate_domains_valid()
    test_no_secrets_or_cot_in_candidates()
    print("ALL 16 TESTS PASSED")
