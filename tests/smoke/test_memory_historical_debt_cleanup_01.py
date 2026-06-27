"""
Smoke test: Memory Historical Debt Cleanup
Verifies that the historical debt cleanup removed all blank/malformed records
while preserving all valid records including 09D promoted IDs.
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))

JSONL_PATH = str(REPO_ROOT / "memory/semantic/semantic_memory.jsonl")
FAISS_IDS_PATH = str(REPO_ROOT / "memory/semantic/semantic_memory_faiss_ids.json")
FAISS_INDEX_PATH = str(REPO_ROOT / "memory/semantic/semantic_memory_faiss.index")
SNAPSHOT_DIR = str(REPO_ROOT / "memory/rollback_snapshots/20260627T003901_historical_debt_cleanup_01")

IS_CI = bool(os.getenv("GITHUB_ACTIONS"))


def _require_runtime_artifact(path, label):
    if not Path(path).exists():
        if IS_CI:
            print(f"SKIP [{label}]: CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE — {path} not present in CI checkout")
            return False
        else:
            raise AssertionError(f"LOCAL_RUNTIME_ARTIFACT_MISSING: {path} must exist locally")
    return True

PROMOTED_IDS = [
    "4da11a6bf9d56d895193c93b",
    "0a585014ab31d166d7fa07e2",
    "5251e2a66aa705c6c2f1a5ef",
    "d3804be5dd651e841f84f366",
    "6470b144fc6d87d8f6419d6d",
    "2254d5b420821c03a79a9a2d",
    "ee7b607ad696bfc4d594e21d",
    "9ba53b29cebef8e697eb3172",
]


def load_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def compute_stats(records):
    ids = [r.get("id", "") for r in records]
    blank = sum(1 for r in records if not (r.get("text", "") or "").strip())
    none_id = sum(1 for r in records if r.get("id") is None)
    empty_id = sum(1 for r in records if r.get("id", "") == "")
    dup_count = len(ids) - len(set(ids))
    return blank, none_id, empty_id, dup_count


def test_records_count_equals_1794():
    if not _require_runtime_artifact(JSONL_PATH, "test_records_count_equals_1794"):
        return
    records = load_jsonl(JSONL_PATH)
    assert len(records) == 1794, f"Expected 1794, got {len(records)}"
    print("PASS: records_count_equals_1794")


def test_faiss_ids_count_equals_1794():
    if not _require_runtime_artifact(FAISS_IDS_PATH, "test_faiss_ids_count_equals_1794"):
        return
    ids = json.load(open(FAISS_IDS_PATH))
    assert len(ids) == 1794, f"Expected 1794, got {len(ids)}"
    print("PASS: faiss_ids_count_equals_1794")


def test_faiss_ntotal_equals_1794():
    if not _require_runtime_artifact(FAISS_INDEX_PATH, "test_faiss_ntotal_equals_1794"):
        return
    import faiss
    idx = faiss.read_index(FAISS_INDEX_PATH)
    assert idx.ntotal == 1794, f"Expected 1794, got {idx.ntotal}"
    print("PASS: faiss_ntotal_equals_1794")


def test_blank_text_count_is_zero():
    if not _require_runtime_artifact(JSONL_PATH, "test_blank_text_count_is_zero"):
        return
    records = load_jsonl(JSONL_PATH)
    blank, _, _, _ = compute_stats(records)
    assert blank == 0, f"Expected 0 blank text, got {blank}"
    print("PASS: blank_text_count_is_zero")


def test_duplicate_id_count_is_zero():
    if not _require_runtime_artifact(JSONL_PATH, "test_duplicate_id_count_is_zero"):
        return
    records = load_jsonl(JSONL_PATH)
    _, _, _, dup = compute_stats(records)
    assert dup == 0, f"Expected 0 duplicates, got {dup}"
    print("PASS: duplicate_id_count_is_zero")


def test_none_id_count_is_zero():
    if not _require_runtime_artifact(JSONL_PATH, "test_none_id_count_is_zero"):
        return
    records = load_jsonl(JSONL_PATH)
    _, none_id, _, _ = compute_stats(records)
    assert none_id == 0, f"Expected 0 none IDs, got {none_id}"
    print("PASS: none_id_count_is_zero")


def test_empty_id_count_is_zero():
    if not _require_runtime_artifact(JSONL_PATH, "test_empty_id_count_is_zero"):
        return
    records = load_jsonl(JSONL_PATH)
    _, _, empty_id, _ = compute_stats(records)
    assert empty_id == 0, f"Expected 0 empty IDs, got {empty_id}"
    print("PASS: empty_id_count_is_zero")


def test_malformed_count_is_zero():
    if not _require_runtime_artifact(JSONL_PATH, "test_malformed_count_is_zero"):
        return
    records = load_jsonl(JSONL_PATH)
    malformed = sum(1 for r in records if not r.get("id") or not r.get("text"))
    assert malformed == 0, f"Expected 0 malformed, got {malformed}"
    print("PASS: malformed_count_is_zero")


def test_all_09d_promoted_ids_in_jsonl():
    if not _require_runtime_artifact(JSONL_PATH, "test_all_09d_promoted_ids_in_jsonl"):
        return
    records = load_jsonl(JSONL_PATH)
    ids = {r.get("id") for r in records if r.get("id")}
    missing = [pid for pid in PROMOTED_IDS if pid not in ids]
    assert not missing, f"Missing promoted IDs in JSONL: {missing}"
    print("PASS: all_09d_promoted_ids_in_jsonl")


def test_all_09d_promoted_ids_in_faiss():
    if not _require_runtime_artifact(FAISS_IDS_PATH, "test_all_09d_promoted_ids_in_faiss"):
        return
    ids = json.load(open(FAISS_IDS_PATH))
    missing = [pid for pid in PROMOTED_IDS if pid not in ids]
    assert not missing, f"Missing promoted IDs in FAISS: {missing}"
    print("PASS: all_09d_promoted_ids_in_faiss")


def test_faiss_ids_subset_of_jsonl():
    if not _require_runtime_artifact(JSONL_PATH, "test_faiss_ids_subset_of_jsonl") or not _require_runtime_artifact(FAISS_IDS_PATH, "test_faiss_ids_subset_of_jsonl"):
        return
    records = load_jsonl(JSONL_PATH)
    jsonl_ids = {r.get("id") for r in records if r.get("id")}
    faiss_ids = set(json.load(open(FAISS_IDS_PATH)))
    assert faiss_ids.issubset(jsonl_ids), f"Orphan FAISS IDs: {faiss_ids - jsonl_ids}"
    print("PASS: faiss_ids_subset_of_jsonl")


def test_rollback_snapshot_exists():
    if not _require_runtime_artifact(SNAPSHOT_DIR, "test_rollback_snapshot_exists"):
        return
    assert os.path.isdir(SNAPSHOT_DIR), f"Snapshot dir missing: {SNAPSHOT_DIR}"
    assert os.path.isfile(os.path.join(SNAPSHOT_DIR, "snapshot_meta.json"))
    print("PASS: rollback_snapshot_exists")


def test_retrieval_for_09d_promoted_ids():
    if not _require_runtime_artifact(JSONL_PATH, "test_retrieval_for_09d_promoted_ids"):
        return
    from tmp_agent.brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
    gateway = MemoryGatewayV2()
    records = load_jsonl(JSONL_PATH)
    id_map = {r.get("id"): r for r in records if r.get("id")}
    for pid in PROMOTED_IDS:
        text = id_map[pid]["text"][:50]
        result = gateway.semantic_retrieve(text, top_k=5)
        hits = result.get("hits", [])
        found = any(h.get("id") == pid for h in hits)
        assert found, f"Promoted ID {pid} not found in retrieval for text: {text}"
    print("PASS: retrieval_for_09d_promoted_ids")


def test_guard_passes():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Guard failed: {result.stdout}\n{result.stderr}"
    print("PASS: guard_passes")


def test_no_memory_files_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    staged = result.stdout.strip()
    for line in staged.splitlines() if staged else []:
        assert "memory/semantic" not in line, f"Memory file staged: {line}"
        assert "memory/autonomous_journal" not in line, f"Autonomous journal staged: {line}"
        assert "memory/rollback_snapshots" not in line, f"Rollback snapshot staged: {line}"
    print("PASS: no_memory_files_staged")


if __name__ == "__main__":
    test_records_count_equals_1794()
    test_faiss_ids_count_equals_1794()
    test_faiss_ntotal_equals_1794()
    test_blank_text_count_is_zero()
    test_duplicate_id_count_is_zero()
    test_none_id_count_is_zero()
    test_empty_id_count_is_zero()
    test_malformed_count_is_zero()
    test_all_09d_promoted_ids_in_jsonl()
    test_all_09d_promoted_ids_in_faiss()
    test_faiss_ids_subset_of_jsonl()
    test_rollback_snapshot_exists()
    test_retrieval_for_09d_promoted_ids()
    test_guard_passes()
    test_no_memory_files_staged()
    print("\nALL MEMORY HISTORICAL DEBT CLEANUP TESTS PASSED")
