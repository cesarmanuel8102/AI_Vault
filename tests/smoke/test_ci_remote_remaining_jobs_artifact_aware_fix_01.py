"""
Smoke test: FRONT-CI-REMOTE-REMAINING-JOBS-ARTIFACT-AWARE-FIX-01 Verification
Verifies that all 3 patched test files are properly artifact-aware.
"""

import os
import subprocess
import sys
from pathlib import Path
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))


def test_memory_historical_debt_contains_ci_skip():
    path = REPO_ROOT / "tests/smoke/test_memory_historical_debt_cleanup_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE" in content
    assert "IS_CI" in content
    print("PASS: memory_historical_debt_contains_ci_skip")


def test_post_09e_roadmap_contains_ci_skip():
    path = REPO_ROOT / "tests/smoke/test_post_09e_nontrading_roadmap_rebase_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE" in content
    assert "IS_CI" in content
    print("PASS: post_09e_roadmap_contains_ci_skip")


def test_visual_trace_contains_ci_skip():
    path = REPO_ROOT / "tests/smoke/test_visual_trace_8092_canonical_path_fix_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE" in content
    assert "IS_CI" in content
    print("PASS: visual_trace_contains_ci_skip")


def test_visual_trace_defines_is_ci_before_memory_mutation():
    path = REPO_ROOT / "tests/smoke/test_visual_trace_8092_canonical_path_fix_01.py"
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    is_ci_line = None
    memory_mutation_line = None
    for i, line in enumerate(lines):
        if "IS_CI =" in line:
            is_ci_line = i
        if "def test_no_memory_mutation" in line:
            memory_mutation_line = i
    assert is_ci_line is not None, "IS_CI not defined"
    assert memory_mutation_line is not None, "test_no_memory_mutation not found"
    assert is_ci_line < memory_mutation_line, "IS_CI must be defined before test_no_memory_mutation"
    print("PASS: visual_trace_defines_is_ci_before_memory_mutation")


def test_roadmap_report_checks_still_exist():
    path = REPO_ROOT / "tests/smoke/test_post_09e_nontrading_roadmap_rebase_01.py"
    content = path.read_text(encoding="utf-8")
    assert "test_roadmap_report_exists" in content
    assert "test_recommended_next_front_exists" in content
    assert "test_all_trading_items_deferred" in content
    assert "test_at_least_8_nontrading_fronts" in content
    print("PASS: roadmap_report_checks_still_exist")


def test_visual_trace_still_checks_app_js_and_dashboard_routes():
    path = REPO_ROOT / "tests/smoke/test_visual_trace_8092_canonical_path_fix_01.py"
    content = path.read_text(encoding="utf-8")
    assert "test_dashboard_app_js_has_no_hardcoded_8091_trace_url" in content
    assert "test_dashboard_app_js_uses_same_origin_trace_proxy" in content
    assert "test_dashboard_proxy_trace_route_exists" in content
    assert "test_dashboard_chat_route_exists" in content
    assert "test_trace_url_mapping_converts_v2_trace_to_dashboard_proxy" in content
    print("PASS: visual_trace_still_checks_app_js_and_dashboard_routes")


def test_workflow_includes_all_5_jobs():
    path = REPO_ROOT / ".github/workflows/nontrading-smoke-regression.yml"
    content = path.read_text(encoding="utf-8")
    assert "security:" in content
    assert "memory-retrieval:" in content
    assert "dashboard-trace:" in content
    assert "roadmap-policy:" in content
    assert "hygiene-guard:" in content
    print("PASS: workflow_includes_all_5_jobs")


def test_workflow_does_not_invoke_trading():
    path = REPO_ROOT / ".github/workflows/nontrading-smoke-regression.yml"
    content = path.read_text(encoding="utf-8")
    # Ensure it does not invoke trading/QC/IBKR/broker test files
    assert "test_p0_trading" not in content.lower()
    assert "test_qc" not in content.lower()
    assert "test_ibkr" not in content.lower()
    assert "test_broker" not in content.lower()
    print("PASS: workflow_does_not_invoke_trading")


def test_local_memory_baseline_unchanged():
    jsonl = REPO_ROOT / "memory/semantic/semantic_memory.jsonl"
    if not jsonl.exists():
        print("SKIP: local memory artifacts not present")
        return
    import json
    records = [json.loads(line) for line in open(jsonl, "r", encoding="utf-8") if line.strip()]
    assert len(records) == 1794, f"Expected 1794, got {len(records)}"
    print("PASS: local_memory_baseline_unchanged")


def test_blank_text_count_is_zero():
    jsonl = REPO_ROOT / "memory/semantic/semantic_memory.jsonl"
    if not jsonl.exists():
        print("SKIP: local memory artifacts not present")
        return
    import json
    records = [json.loads(line) for line in open(jsonl, "r", encoding="utf-8") if line.strip()]
    blank = sum(1 for r in records if not (r.get("text", "") or "").strip())
    assert blank == 0, f"Expected 0 blank, got {blank}"
    print("PASS: blank_text_count_is_zero")


def test_duplicate_id_count_is_zero():
    jsonl = REPO_ROOT / "memory/semantic/semantic_memory.jsonl"
    if not jsonl.exists():
        print("SKIP: local memory artifacts not present")
        return
    import json
    records = [json.loads(line) for line in open(jsonl, "r", encoding="utf-8") if line.strip()]
    dup = len([r.get("id") for r in records]) - len({r.get("id") for r in records})
    assert dup == 0, f"Expected 0 duplicates, got {dup}"
    print("PASS: duplicate_id_count_is_zero")


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


def test_guard_passes():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Guard failed: {result.stdout}\n{result.stderr}"
    print("PASS: guard_passes")


if __name__ == "__main__":
    test_memory_historical_debt_contains_ci_skip()
    test_post_09e_roadmap_contains_ci_skip()
    test_visual_trace_contains_ci_skip()
    test_visual_trace_defines_is_ci_before_memory_mutation()
    test_roadmap_report_checks_still_exist()
    test_visual_trace_still_checks_app_js_and_dashboard_routes()
    test_workflow_includes_all_5_jobs()
    test_workflow_does_not_invoke_trading()
    test_local_memory_baseline_unchanged()
    test_blank_text_count_is_zero()
    test_duplicate_id_count_is_zero()
    test_no_memory_files_staged()
    test_guard_passes()
    print("\nALL ARTIFACT-AWARE FIX VERIFICATION TESTS PASSED")
