"""
Smoke test: Post-09E Non-Trading Roadmap Rebase
Verifies roadmap artifacts, non-trading priorities, and trading deferral.
"""

import json
import os
import sys
import subprocess
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))

ROADMAP_DIR = str(REPO_ROOT / "tmp_agent/front_post_09e_nontrading_roadmap_rebase_01")


def test_memory_baseline_1794():
    import faiss
    records = [json.loads(line) for line in open(str(REPO_ROOT / "memory/semantic/semantic_memory.jsonl"), "r", encoding="utf-8") if line.strip()]
    faiss_ids = json.load(open(str(REPO_ROOT / "memory/semantic/semantic_memory_faiss_ids.json")))
    idx = faiss.read_index(str(REPO_ROOT / "memory/semantic/semantic_memory_faiss.index"))
    assert len(records) == 1794
    assert len(faiss_ids) == 1794
    assert idx.ntotal == 1794
    print("PASS: memory_baseline_1794")


def test_blank_and_duplicate_zero():
    records = [json.loads(line) for line in open(str(REPO_ROOT / "memory/semantic/semantic_memory.jsonl"), "r", encoding="utf-8") if line.strip()]
    blank = sum(1 for r in records if not (r.get("text", "") or "").strip())
    dup = len([r.get("id") for r in records]) - len({r.get("id") for r in records})
    assert blank == 0
    assert dup == 0
    print("PASS: blank_and_duplicate_zero")


def test_roadmap_report_exists():
    assert os.path.isdir(ROADMAP_DIR)
    assert os.path.isfile(os.path.join(ROADMAP_DIR, "nontrading_roadmap.json"))
    assert os.path.isfile(os.path.join(ROADMAP_DIR, "remaining_work_classification.json"))
    assert os.path.isfile(os.path.join(ROADMAP_DIR, "recommended_next_front.json"))
    print("PASS: roadmap_report_exists")


def test_recommended_next_front_exists():
    data = json.load(open(os.path.join(ROADMAP_DIR, "recommended_next_front.json")))
    assert data.get("recommended_next_front")
    assert data.get("reason")
    print("PASS: recommended_next_front_exists")


def test_all_trading_items_deferred():
    data = json.load(open(os.path.join(ROADMAP_DIR, "remaining_work_classification.json")))
    trading_items = [item for item in data["items"] if item.get("trading_related")]
    for item in trading_items:
        assert item["category"] == "D_TRADING_DEFERRED_FINAL", f"Trading item {item['item_id']} not deferred: {item['category']}"
    print(f"PASS: all_trading_items_deferred ({len(trading_items)} items)")


def test_at_least_8_nontrading_fronts():
    data = json.load(open(os.path.join(ROADMAP_DIR, "nontrading_roadmap.json")))
    fronts = data["sequenced_fronts"]
    assert len(fronts) >= 8, f"Only {len(fronts)} non-trading fronts found"
    print(f"PASS: at_least_8_nontrading_fronts ({len(fronts)} fronts)")


def test_no_memory_mutation():
    result = subprocess.run(
        ["git", "diff", "--name-status"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    for line in result.stdout.strip().splitlines():
        assert "memory/semantic" not in line, f"Memory mutated: {line}"
    print("PASS: no_memory_mutation")


def test_guard_passes():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
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
        assert "memory/semantic" not in line
        assert "memory/autonomous_journal" not in line
        assert "memory/rollback_snapshots" not in line
    print("PASS: no_memory_files_staged")


def test_trading_files_not_touched():
    result = subprocess.run(
        ["git", "diff", "--name-status"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    for line in result.stdout.strip().splitlines():
        assert "tmp_agent/strategies" not in line
        assert "trading/" not in line
        assert "financial_autonomy" not in line
    print("PASS: trading_files_not_touched")


if __name__ == "__main__":
    test_memory_baseline_1794()
    test_blank_and_duplicate_zero()
    test_roadmap_report_exists()
    test_recommended_next_front_exists()
    test_all_trading_items_deferred()
    test_at_least_8_nontrading_fronts()
    test_no_memory_mutation()
    test_guard_passes()
    test_no_memory_files_staged()
    test_trading_files_not_touched()
    print("\nALL POST-09E NONTRADING ROADMAP REBASE TESTS PASSED")
