"""
Smoke tests for front-memory-git-hygiene-final-01.
Rules:
- Local memory state from 08F must be preserved.
- Runtime memory files must no longer be tracked by Git.
- .gitignore must block runtime memory paths.
- Guard script must block staging of sensitive paths.
"""
import sys
import json
import hashlib
import subprocess
from pathlib import Path

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/scripts/git_hygiene")

from check_no_sensitive_paths_staged import _is_blocked_path

ROOT = Path("C:/AI_VAULT_CANONICAL")
HYGIENE_DIR = ROOT / "tmp_agent" / "front_memory_git_hygiene_final_01"
MEM_DIR = ROOT / "memory" / "semantic"
MANIFEST = ROOT / "tmp_agent" / "front_brain_agent_v2_text_dedup_batch_promotion_08f" / "promotion_manifest_24_text_unique.json"

EXPECTED_RECORDS = 1756
EXPECTED_IDS = 1747
EXPECTED_NTOTAL = 1747


def _run(cmd):
    result = subprocess.run(cmd, cwd=ROOT, shell=True, capture_output=True, text=True)
    return result.stdout.strip().splitlines()


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_semantic_memory_files_exist_locally():
    assert (MEM_DIR / "semantic_memory.jsonl").exists()
    assert (MEM_DIR / "semantic_memory_faiss.index").exists()
    assert (MEM_DIR / "semantic_memory_faiss_ids.json").exists()
    print("PASS: semantic_memory_files_exist_locally")


def test_semantic_memory_records_preserved_1756():
    pre = _load_json(HYGIENE_DIR / "post_untrack_memory_state.json")
    assert pre["semantic_memory_records"] == EXPECTED_RECORDS
    lines = [line for line in (MEM_DIR / "semantic_memory.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == EXPECTED_RECORDS
    print("PASS: semantic_memory_records_preserved_1756")


def test_faiss_ids_count_preserved_1747():
    post = _load_json(HYGIENE_DIR / "post_untrack_memory_state.json")
    assert post["faiss_ids_count"] == EXPECTED_IDS
    ids = json.loads((MEM_DIR / "semantic_memory_faiss_ids.json").read_text(encoding="utf-8"))
    assert len(ids) == EXPECTED_IDS
    print("PASS: faiss_ids_count_preserved_1747")


def test_faiss_ntotal_preserved_1747():
    post = _load_json(HYGIENE_DIR / "post_untrack_memory_state.json")
    assert post["faiss_ntotal"] == EXPECTED_NTOTAL
    print("PASS: faiss_ntotal_preserved_1747")


def test_runtime_memory_files_not_tracked():
    post = _load_json(HYGIENE_DIR / "post_untrack_memory_state.json")
    assert post["semantic_memory_tracked"] is False
    assert post["faiss_index_tracked"] is False
    assert post["faiss_ids_tracked"] is False
    assert post["promotion_audit_tracked"] is False
    assert not _run("git ls-files memory/semantic/semantic_memory.jsonl")
    assert not _run("git ls-files memory/semantic/semantic_memory_faiss.index")
    assert not _run("git ls-files memory/semantic/semantic_memory_faiss_ids.json")
    assert not _run("git ls-files memory/semantic/promotion_audit.jsonl")
    print("PASS: runtime_memory_files_not_tracked")


def test_autonomous_journal_not_tracked():
    assert not _run("git ls-files memory/autonomous_journal.jsonl")
    print("PASS: autonomous_journal_not_tracked")


def test_rollback_snapshots_not_tracked():
    tracked = _run("git ls-files memory/rollback_snapshots/")
    assert not tracked
    print("PASS: rollback_snapshots_not_tracked")


def test_secrets_report_csv_not_tracked():
    assert not _run("git ls-files audit_reports/secrets_report.csv")
    print("PASS: secrets_report_csv_not_tracked")


def test_gitignore_blocks_runtime_memory():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "memory/semantic/semantic_memory.jsonl" in ignore
    assert "memory/semantic/promotion_audit.jsonl" in ignore
    assert "memory/semantic/*.index" in ignore or "memory/semantic/semantic_memory_faiss.index" in ignore
    assert "memory/autonomous_journal.jsonl" in ignore
    assert "memory/rollback_snapshots/" in ignore
    assert "audit_reports/secrets_report.csv" in ignore
    print("PASS: gitignore_blocks_runtime_memory")


def test_guard_blocks_staged_memory_path():
    assert _is_blocked_path("A", "memory/semantic/semantic_memory.jsonl")
    assert _is_blocked_path("M", "memory/semantic/semantic_memory_faiss.index")
    assert _is_blocked_path("A", "memory/autonomous_journal.jsonl")
    print("PASS: guard_blocks_staged_memory_path")


def test_guard_blocks_staged_secrets_report():
    assert _is_blocked_path("A", "audit_reports/secrets_report.csv")
    print("PASS: guard_blocks_staged_secrets_report")


def test_guard_allows_safe_report_artifact():
    assert not _is_blocked_path("A", "tmp_agent/front_memory_git_hygiene_final_01/pre_hygiene_memory_state.json")
    assert not _is_blocked_path("A", "tmp_agent/front_brain_agent_v2_text_dedup_batch_promotion_08f/batch_promotion_summary.md")
    print("PASS: guard_allows_safe_report_artifact")


def test_promoted_08f_ids_still_in_jsonl():
    manifest = [m["candidate_id"] for m in _load_json(MANIFEST)]
    records = [json.loads(line) for line in (MEM_DIR / "semantic_memory.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    jsonl_ids = {r.get("id") for r in records}
    assert all(cid in jsonl_ids for cid in manifest)
    print("PASS: promoted_08f_ids_still_in_jsonl")


def test_promoted_08f_ids_still_in_faiss_ids():
    manifest = [m["candidate_id"] for m in _load_json(MANIFEST)]
    ids = set(str(i) for i in json.loads((MEM_DIR / "semantic_memory_faiss_ids.json").read_text(encoding="utf-8")))
    assert all(cid in ids for cid in manifest)
    print("PASS: promoted_08f_ids_still_in_faiss_ids")


def test_no_memory_files_staged():
    staged = _run("git diff --cached --name-status")
    content_staged = [line for line in staged if line]
    memory_additions = [line for line in content_staged if line.startswith(("A", "M", "C", "R")) and ("memory/semantic" in line or "memory/rollback_snapshots" in line or "memory/autonomous_journal" in line)]
    assert not memory_additions, f"memory content staged: {memory_additions}"
    print("PASS: no_memory_files_staged_as_content")


if __name__ == "__main__":
    test_semantic_memory_files_exist_locally()
    test_semantic_memory_records_preserved_1756()
    test_faiss_ids_count_preserved_1747()
    test_faiss_ntotal_preserved_1747()
    test_runtime_memory_files_not_tracked()
    test_autonomous_journal_not_tracked()
    test_rollback_snapshots_not_tracked()
    test_secrets_report_csv_not_tracked()
    test_gitignore_blocks_runtime_memory()
    test_guard_blocks_staged_memory_path()
    test_guard_blocks_staged_secrets_report()
    test_guard_allows_safe_report_artifact()
    test_promoted_08f_ids_still_in_jsonl()
    test_promoted_08f_ids_still_in_faiss_ids()
    test_no_memory_files_staged()
    print("ALL MEMORY GIT HYGIENE FINAL 01 TESTS PASSED")
