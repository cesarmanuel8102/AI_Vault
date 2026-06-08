"""Smoke test for FRONT-REAL-MEMORY-FAISS-PROMOTION-01."""

import json
import os
from pathlib import Path

EVIDENCE_DIR = "tmp_agent/front_real_memory_faiss_promotion_01"
CANARY_ID = "canary-00000000-0000-0000-0000-000000000001"
SEMANTIC_JSONL = "memory/semantic/semantic_memory.jsonl"


def test_backup_exists():
    backup_dir = Path(f"{EVIDENCE_DIR}/backups")
    assert backup_dir.is_dir()
    files = ["semantic_memory.jsonl", "semantic_memory_faiss.index",
             "semantic_memory_faiss_ids.json", "semantic_memory_index.npz"]
    for f in files:
        assert (backup_dir / f).is_file(), f"Missing backup: {f}"


def test_baseline_snapshot_exists():
    p = Path(f"{EVIDENCE_DIR}/baseline_snapshot.json")
    assert p.is_file()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("canary_count_in_jsonl") == 1
    assert data.get("canary_is_last_line") is True


def test_faiss_inventory_exists():
    p = Path(f"{EVIDENCE_DIR}/faiss_inventory.json")
    assert p.is_file()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("safe_single_record_promotion_possible") is True


def test_promotion_plan_exists():
    p = Path(f"{EVIDENCE_DIR}/promotion_plan.json")
    assert p.is_file()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["records_to_promote"] == [CANARY_ID]
    assert data["canary_already_present"] is False


def test_pre_write_validation_exists():
    p = Path(f"{EVIDENCE_DIR}/pre_write_validation.json")
    assert p.is_file()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("status") == "PASS"


def test_promotion_execution_exists():
    p = Path(f"{EVIDENCE_DIR}/promotion_execution.json")
    assert p.is_file()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["promoted"] is True
    assert data["already_present"] is False
    assert data["error"] is None
    assert data["canary_id"] == CANARY_ID


def test_post_promotion_validation_exists():
    p = Path(f"{EVIDENCE_DIR}/post_promotion_validation.json")
    assert p.is_file()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["semantic_memory_jsonl_unchanged"] is True
    assert data["canary_exactly_once"] is True
    assert data["canary_unique_in_ids"] is True
    assert data["faiss_index_changed"] or data["faiss_ids_changed"]


def test_semantic_memory_jsonl_unchanged():
    import hashlib
    with open(f"{EVIDENCE_DIR}/baseline_snapshot.json", "r", encoding="utf-8") as f:
        baseline = json.load(f)
    baseline_sha = baseline["semantic_memory_jsonl"]["sha256"]
    h = hashlib.sha256()
    with open(SEMANTIC_JSONL, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    assert h.hexdigest() == baseline_sha


def test_canary_exists_once_in_jsonl():
    count = 0
    with open(SEMANTIC_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    obj = json.loads(line)
                    if obj.get("id") == CANARY_ID:
                        count += 1
                except json.JSONDecodeError:
                    pass
    assert count == 1


def test_canary_in_faiss_ids_or_noop_documented():
    with open(f"{EVIDENCE_DIR}/post_promotion_validation.json", "r", encoding="utf-8") as f:
        validation = json.load(f)
    result_type = validation["promotion_result"]
    if result_type == "PROMOTED_CANARY_TO_FAISS":
        with open("memory/semantic/semantic_memory_faiss_ids.json", "r", encoding="utf-8") as f:
            ids = json.load(f)
        assert CANARY_ID in ids
    elif result_type == "PROMOTION_ALREADY_PRESENT_NOOP":
        assert validation["canary_count_in_ids_after"] >= 1
    else:
        raise AssertionError(f"Unexpected result_type: {result_type}")


def test_no_duplicate_canary_id():
    with open("memory/semantic/semantic_memory_faiss_ids.json", "r", encoding="utf-8") as f:
        ids = json.load(f)
    assert ids.count(CANARY_ID) <= 1


def test_rollback_files_exist():
    backup_dir = Path(f"{EVIDENCE_DIR}/backups")
    for name in ["semantic_memory_faiss.index", "semantic_memory_faiss_ids.json", "semantic_memory_index.npz"]:
        assert (backup_dir / name).is_file(), f"Missing rollback artifact: {name}"


def test_doc_exists():
    assert os.path.isfile("docs/FRONT_REAL_MEMORY_FAISS_PROMOTION_01.md")


def test_doc_declares_scope_single_canary():
    with open("docs/FRONT_REAL_MEMORY_FAISS_PROMOTION_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "records_to_promote: [\"canary-00000000-0000-0000-0000-000000000001\"]" in content


def test_doc_declares_no_memory_jsonl_write():
    with open("docs/FRONT_REAL_MEMORY_FAISS_PROMOTION_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "semantic_memory_jsonl_modified" in content and "false" in content.lower()


def test_doc_declares_no_patch_application():
    with open("docs/FRONT_REAL_MEMORY_FAISS_PROMOTION_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "patch_application_executed" in content and "false" in content.lower()


def test_doc_decision_present():
    with open("docs/FRONT_REAL_MEMORY_FAISS_PROMOTION_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "PROMOTED_CANARY_TO_FAISS" in content or "PROMOTION_ALREADY_PRESENT_NOOP" in content


def test_no_trading_or_b8_staged():
    # Check git status for staged trading/B8 files
    import subprocess
    result = subprocess.run(["git", "diff", "--cached", "--name-status"],
                            capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad
