"""
FRONT-CI-SMOKE-REGRESSION-EXPANSION-01
CI configuration smoke test.

Verifies:
1. workflow file exists
2. workflow uses Python 3.11
3. workflow does not include trading/QC/IBKR/broker patterns
4. workflow includes P0 security test
5. workflow includes 09E retrieval test
6. workflow includes memory cleanup test
7. workflow includes FAISS hydration test
8. workflow includes Visual Trace 8092 test
9. workflow includes roadmap rebase test
10. workflow runs guard script
11. accepted manifest exists
12. memory baseline still 1794 / 1794 / 1794
13. blank_text_count == 0
14. duplicate_id_count == 0
15. no memory files staged
16. no trading files touched

No memory mutation.
No ingestion.
No trading.
"""
import json
import os
import subprocess
import sys
import yaml
from pathlib import Path

_ROOT = Path(r"C:\AI_VAULT_CANONICAL")
_MEMORY_SEMANTIC = _ROOT / "memory/semantic"
_JSONL = _MEMORY_SEMANTIC / "semantic_memory.jsonl"
_IDS = _MEMORY_SEMANTIC / "semantic_memory_faiss_ids.json"
_IDX = _MEMORY_SEMANTIC / "semantic_memory_faiss.index"
_WORKFLOW = _ROOT / ".github/workflows/nontrading-smoke-regression.yml"
_MANIFEST = _ROOT / "tmp_agent/front_ci_smoke_regression_expansion_01/accepted_ci_test_manifest.json"

sys.path.insert(0, str(_ROOT))


# ── 1. workflow file exists ──

def test_workflow_file_exists():
    assert _WORKFLOW.is_file(), f"Workflow file missing: {_WORKFLOW}"
    print("PASS: workflow_file_exists")


# ── 2. workflow uses Python 3.11 ──

def test_workflow_uses_python_311():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "python-version: '3.11'" in content or 'python-version: "3.11"' in content, "Python 3.11 not specified"
    print("PASS: workflow_uses_python_311")


# ── 3. workflow does not include trading/QC/IBKR/broker patterns ──

def test_workflow_excludes_trading_patterns():
    content = _WORKFLOW.read_text(encoding="utf-8").lower()
    forbidden = [
        "broker", "ibkr", "quantconnect", "backtester",
        "portfolio_manager", "live_trading", "financial_autonomy"
    ]
    found = [p for p in forbidden if p in content]
    assert not found, f"Forbidden trading patterns found: {found}"
    # "trading" alone is too broad (matches "nontrading"); check explicit trading files instead
    assert "trading/" not in content, "Contains trading/ directory reference"
    assert "trading.py" not in content, "Contains trading.py file reference"
    print("PASS: workflow_excludes_trading_patterns")


# ── 4-9. workflow includes accepted tests ──

def test_workflow_includes_p0_security():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "test_p0_nontrading_security_reality_check_and_fix_01" in content
    print("PASS: workflow_includes_p0_security")


def test_workflow_includes_09e_retrieval():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "test_09e_retrieval_quality_memory_utility_evaluation_01" in content
    print("PASS: workflow_includes_09e_retrieval")


def test_workflow_includes_memory_cleanup():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "test_memory_historical_debt_cleanup_01" in content
    print("PASS: workflow_includes_memory_cleanup")


def test_workflow_includes_faiss_hydration():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "test_agent_v2_faiss_rebuild_hydration_01" in content
    print("PASS: workflow_includes_faiss_hydration")


def test_workflow_includes_visual_trace_8092():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "test_visual_trace_8092_canonical_path_fix_01" in content
    print("PASS: workflow_includes_visual_trace_8092")


def test_workflow_includes_roadmap_rebase():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "test_post_09e_nontrading_roadmap_rebase_01" in content
    print("PASS: workflow_includes_roadmap_rebase")


# ── 10. workflow runs guard script ──

def test_workflow_runs_guard_script():
    content = _WORKFLOW.read_text(encoding="utf-8")
    assert "check_no_sensitive_paths_staged" in content
    print("PASS: workflow_runs_guard_script")


# ── 11. accepted manifest exists ──

def test_accepted_manifest_exists():
    assert _MANIFEST.is_file(), f"Manifest missing: {_MANIFEST}"
    data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert "suites" in data and len(data["suites"]) >= 10
    assert "excluded_patterns" in data
    print("PASS: accepted_manifest_exists")


# ── 12-14. memory baseline ──

def test_memory_baseline_unchanged():
    import faiss
    records = [l for l in _JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    ids = json.loads(_IDS.read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(_IDX)).ntotal)
    assert len(records) == 1794, f"Expected 1794 records, got {len(records)}"
    assert len(ids) == 1794, f"Expected 1794 ids, got {len(ids)}"
    assert ntotal == 1794, f"Expected 1794 ntotal, got {ntotal}"
    print("PASS: memory_baseline_unchanged")


def test_blank_text_count_zero():
    records = [json.loads(l) for l in _JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    blank = sum(1 for r in records if not (r.get("text", "") or "").strip())
    assert blank == 0, f"Expected 0 blank, got {blank}"
    print("PASS: blank_text_count_zero")


def test_duplicate_id_count_zero():
    records = [json.loads(l) for l in _JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    dup = len(records) - len({r.get("id", "") for r in records})
    assert dup == 0, f"Expected 0 duplicates, got {dup}"
    print("PASS: duplicate_id_count_zero")


# ── 15. no memory files staged ──

def test_no_memory_files_staged():
    result = subprocess.run(
        ["git", "status", "--short", "--", "memory/semantic", "memory/autonomous_journal.jsonl", "memory/promotion_queue", "memory/semantic_staging"],
        cwd=str(_ROOT), capture_output=True, text=True,
    )
    staged = [l for l in result.stdout.splitlines() if l.strip().startswith(("A", "M", "D"))]
    assert not staged, f"Memory files staged: {staged}"
    print("PASS: no_memory_files_staged")


# ── 16. no trading files touched ──

def test_no_trading_files_touched():
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=str(_ROOT), capture_output=True, text=True,
    )
    dirty = result.stdout.splitlines()
    trading_dirty = [f for f in dirty if any(p in f.lower() for p in ["trading", "broker", "ibkr", "quantconnect", "backtester", "portfolio", "live_trading", "financial_autonomy"])]
    assert not trading_dirty, f"Trading files touched: {trading_dirty}"
    print("PASS: no_trading_files_touched")


if __name__ == "__main__":
    test_workflow_file_exists()
    test_workflow_uses_python_311()
    test_workflow_excludes_trading_patterns()
    test_workflow_includes_p0_security()
    test_workflow_includes_09e_retrieval()
    test_workflow_includes_memory_cleanup()
    test_workflow_includes_faiss_hydration()
    test_workflow_includes_visual_trace_8092()
    test_workflow_includes_roadmap_rebase()
    test_workflow_runs_guard_script()
    test_accepted_manifest_exists()
    test_memory_baseline_unchanged()
    test_blank_text_count_zero()
    test_duplicate_id_count_zero()
    test_no_memory_files_staged()
    test_no_trading_files_touched()
    print("\nALL 16 CI CONFIG SMOKE TESTS PASSED")
