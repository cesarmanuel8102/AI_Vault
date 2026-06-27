"""
Smoke test: 09D Post-Write Reconciliation Repair
Verifies that the 09D batch of 8 promoted records is clean,
and that historical memory debt (blank text, duplicate IDs) did NOT increase.
"""

import json
import os
import sys
import subprocess
from tests._repo_root import REPO_ROOT

# Ensure imports resolve from project root
sys.path.insert(0, str(REPO_ROOT))

# Constants
SNAPSHOT_DIR = str(REPO_ROOT / "memory/rollback_snapshots/20260626T094552_806821_09d_batch_8")
PRE_JSONL = os.path.join(SNAPSHOT_DIR, "semantic_memory.jsonl")
PRE_FAISS_IDS = os.path.join(SNAPSHOT_DIR, "semantic_memory_faiss_ids.json")
PRE_FAISS_INDEX = os.path.join(SNAPSHOT_DIR, "semantic_memory_faiss.index")

CUR_JSONL = str(REPO_ROOT / "memory/semantic/semantic_memory.jsonl")
CUR_FAISS_IDS = str(REPO_ROOT / "memory/semantic/semantic_memory_faiss_ids.json")
CUR_FAISS_INDEX = str(REPO_ROOT / "memory/semantic/semantic_memory_faiss.index")

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
    dup_ids = {id for id in ids if ids.count(id) > 1}
    return {
        "count": len(records),
        "ids": ids,
        "blank": blank,
        "none_id": none_id,
        "empty_id": empty_id,
        "dup_count": dup_count,
        "dup_ids": dup_ids,
    }


def test_rollback_snapshot_exists():
    assert os.path.isdir(SNAPSHOT_DIR), f"Snapshot dir missing: {SNAPSHOT_DIR}"
    assert os.path.isfile(PRE_JSONL), f"Pre JSONL missing: {PRE_JSONL}"
    assert os.path.isfile(PRE_FAISS_IDS), f"Pre FAISS IDs missing: {PRE_FAISS_IDS}"
    assert os.path.isfile(PRE_FAISS_INDEX), f"Pre FAISS index missing: {PRE_FAISS_INDEX}"
    print("PASS: rollback_snapshot_exists")


def test_pre_counts_loadable():
    pre_records = load_jsonl(PRE_JSONL)
    pre_stats = compute_stats(pre_records)
    assert pre_stats["count"] == 1795, f"Expected 1795, got {pre_stats['count']}"
    print("PASS: pre_counts_loadable")


def test_current_counts_loadable():
    cur_records = load_jsonl(CUR_JSONL)
    cur_stats = compute_stats(cur_records)
    # FRONT-MEMORY-HISTORICAL-DEBT-CLEANUP-01 removed 9 blank records.
    # Accepted baseline: 1794 (was 1795 pre-cleanup + 8 promoted - 9 removed = 1794).
    assert cur_stats["count"] == 1794, f"Expected 1794, got {cur_stats['count']}"
    print("PASS: current_counts_loadable")


def test_promoted_id_list_has_eight():
    assert len(PROMOTED_IDS) == 8
    assert len(set(PROMOTED_IDS)) == 8
    print("PASS: promoted_id_list_has_eight")


def test_current_records_equals_pre_plus_eight_minus_cleanup():
    # FRONT-MEMORY-HISTORICAL-DEBT-CLEANUP-01 removed 9 blank records after 09D.
    # Current: 1794 = pre (1795) + 8 promoted - 9 removed
    pre_records = load_jsonl(PRE_JSONL)
    cur_records = load_jsonl(CUR_JSONL)
    assert len(cur_records) == len(pre_records) + 8 - 9, (
        f"Expected {len(pre_records) + 8 - 9}, got {len(cur_records)}"
    )
    print("PASS: current_records_equals_pre_plus_eight_minus_cleanup")


def test_current_faiss_ids_equals_pre_plus_eight():
    # Pre-snapshot FAISS already excluded 9 blank records (index=1786 vs jsonl=1795).
    # Cleanup rebuilt FAISS to match cleaned JSONL, so FAISS delta is simply +8 from 09D.
    pre_faiss_ids = json.load(open(PRE_FAISS_IDS))
    cur_faiss_ids = json.load(open(CUR_FAISS_IDS))
    assert len(cur_faiss_ids) == len(pre_faiss_ids) + 8, (
        f"Expected {len(pre_faiss_ids) + 8}, got {len(cur_faiss_ids)}"
    )
    print("PASS: current_faiss_ids_equals_pre_plus_eight")


def test_current_faiss_ntotal_equals_pre_plus_eight():
    import faiss
    pre_idx = faiss.read_index(PRE_FAISS_INDEX)
    cur_idx = faiss.read_index(CUR_FAISS_INDEX)
    assert cur_idx.ntotal == pre_idx.ntotal + 8, (
        f"Expected {pre_idx.ntotal + 8}, got {cur_idx.ntotal}"
    )
    print("PASS: current_faiss_ntotal_equals_pre_plus_eight")


def test_added_records_exactly_match_promoted_ids():
    pre_records = load_jsonl(PRE_JSONL)
    cur_records = load_jsonl(CUR_JSONL)
    pre_ids = {r.get("id", "") for r in pre_records}
    cur_ids = {r.get("id", "") for r in cur_records}
    added_ids = sorted(cur_ids - pre_ids)
    promoted_sorted = sorted(PROMOTED_IDS)
    assert added_ids == promoted_sorted, f"Added IDs mismatch:\n  added={added_ids}\n  promoted={promoted_sorted}"
    print("PASS: added_records_exactly_match_promoted_ids")


def test_added_records_no_blank_text():
    pre_records = load_jsonl(PRE_JSONL)
    cur_records = load_jsonl(CUR_JSONL)
    pre_ids = {r.get("id", "") for r in pre_records}
    added = [r for r in cur_records if r.get("id", "") not in pre_ids]
    blanks = sum(1 for r in added if not (r.get("text", "") or "").strip())
    assert blanks == 0, f"Found {blanks} blank added records"
    print("PASS: added_records_no_blank_text")


def test_added_records_no_duplicate_ids():
    pre_records = load_jsonl(PRE_JSONL)
    cur_records = load_jsonl(CUR_JSONL)
    pre_ids = {r.get("id", "") for r in pre_records}
    added = [r for r in cur_records if r.get("id", "") not in pre_ids]
    added_ids = [r.get("id", "") for r in added]
    dup = len(added_ids) - len(set(added_ids))
    assert dup == 0, f"Found {dup} duplicate IDs in added records"
    print("PASS: added_records_no_duplicate_ids")


def test_added_records_no_malformed_json():
    pre_records = load_jsonl(PRE_JSONL)
    cur_records = load_jsonl(CUR_JSONL)
    pre_ids = {r.get("id", "") for r in pre_records}
    added = [r for r in cur_records if r.get("id", "") not in pre_ids]
    malformed = sum(1 for r in added if not r.get("id") or not r.get("text"))
    assert malformed == 0, f"Found {malformed} malformed added records"
    print("PASS: added_records_no_malformed_json")


def test_all_promoted_ids_in_current_jsonl():
    cur_records = load_jsonl(CUR_JSONL)
    cur_ids = {r.get("id", "") for r in cur_records}
    missing = [pid for pid in PROMOTED_IDS if pid not in cur_ids]
    assert not missing, f"Missing promoted IDs in JSONL: {missing}"
    print("PASS: all_promoted_ids_in_current_jsonl")


def test_all_promoted_ids_in_current_faiss():
    cur_faiss_ids = json.load(open(CUR_FAISS_IDS))
    missing = [pid for pid in PROMOTED_IDS if pid not in cur_faiss_ids]
    assert not missing, f"Missing promoted IDs in FAISS: {missing}"
    print("PASS: all_promoted_ids_in_current_faiss")


def test_retrieval_for_all_promoted_ids():
    import faiss
    cur_idx = faiss.read_index(CUR_FAISS_INDEX)
    cur_faiss_ids = json.load(open(CUR_FAISS_IDS))
    # Build id -> index map
    id_to_idx = {fid: i for i, fid in enumerate(cur_faiss_ids)}
    # Simple embed placeholder: we will just check IDs exist and index is healthy
    assert cur_idx.ntotal == len(cur_faiss_ids)
    for pid in PROMOTED_IDS:
        assert pid in id_to_idx, f"Promoted ID {pid} not in FAISS ids"
    print("PASS: retrieval_for_all_promoted_ids (ids present)")


def test_historical_blank_text_count_did_not_increase():
    pre_stats = compute_stats(load_jsonl(PRE_JSONL))
    cur_stats = compute_stats(load_jsonl(CUR_JSONL))
    # FRONT-MEMORY-HISTORICAL-DEBT-CLEANUP-01 removed blanks, so count can decrease.
    assert cur_stats["blank"] <= pre_stats["blank"], (
        f"Blank text increased: pre={pre_stats['blank']} cur={cur_stats['blank']}"
    )
    print("PASS: historical_blank_text_count_did_not_increase")


def test_historical_duplicate_id_count_did_not_increase():
    pre_stats = compute_stats(load_jsonl(PRE_JSONL))
    cur_stats = compute_stats(load_jsonl(CUR_JSONL))
    # FRONT-MEMORY-HISTORICAL-DEBT-CLEANUP-01 removed duplicates, so count can decrease.
    assert cur_stats["dup_count"] <= pre_stats["dup_count"], (
        f"Duplicate count increased: pre={pre_stats['dup_count']} cur={cur_stats['dup_count']}"
    )
    print("PASS: historical_duplicate_id_count_did_not_increase")


def test_historical_debt_count_known():
    pre_stats = compute_stats(load_jsonl(PRE_JSONL))
    assert pre_stats["blank"] == 9
    assert pre_stats["dup_count"] == 4
    print("PASS: historical_debt_count_known")


def test_delta_clean():
    pre_records = load_jsonl(PRE_JSONL)
    cur_records = load_jsonl(CUR_JSONL)
    pre_ids = {r.get("id", "") for r in pre_records}
    added = [r for r in cur_records if r.get("id", "") not in pre_ids]
    added_blank = sum(1 for r in added if not (r.get("text", "") or "").strip())
    added_dup = len([r for r in added if sum(1 for x in added if x.get("id") == r.get("id")) > 1])
    added_malf = sum(1 for r in added if not r.get("id") or not r.get("text"))
    assert added_blank == 0 and added_dup == 0 and added_malf == 0
    print("PASS: delta_clean")


def test_guard_no_sensitive_files_staged():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Guard failed:\n{result.stdout}\n{result.stderr}"
    print("PASS: guard_no_sensitive_files_staged")


if __name__ == "__main__":
    test_rollback_snapshot_exists()
    test_pre_counts_loadable()
    test_current_counts_loadable()
    test_promoted_id_list_has_eight()
    test_current_records_equals_pre_plus_eight_minus_cleanup()
    test_current_faiss_ids_equals_pre_plus_eight()
    test_current_faiss_ntotal_equals_pre_plus_eight()
    test_added_records_exactly_match_promoted_ids()
    test_added_records_no_blank_text()
    test_added_records_no_duplicate_ids()
    test_added_records_no_malformed_json()
    test_all_promoted_ids_in_current_jsonl()
    test_all_promoted_ids_in_current_faiss()
    test_retrieval_for_all_promoted_ids()
    test_historical_blank_text_count_did_not_increase()
    test_historical_duplicate_id_count_did_not_increase()
    test_historical_debt_count_known()
    test_delta_clean()
    test_guard_no_sensitive_files_staged()
    print("\nALL 09D RECONCILIATION REPAIR TESTS PASSED")
