"""
Smoke test: FRONT-CI-REMOTE-UNPATCHED-STEPS-ARTIFACT-AWARE-FIX-02 Verification
Verifies that all artifact-dependent tests are properly guarded for CI.
"""

import os
import sys
from pathlib import Path
from tests._repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))


def test_09e_contains_ci_memory_artifact_skip():
    path = REPO_ROOT / "tests/smoke/test_09e_retrieval_quality_memory_utility_evaluation_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE" in content
    assert "IS_CI" in content
    assert "_require_memory_artifact" in content
    print("PASS: 09e_contains_ci_memory_artifact_skip")


def test_09d_contains_ci_snapshot_artifact_skip():
    path = REPO_ROOT / "tests/smoke/test_09d_post_write_reconciliation_repair_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_RUNTIME_ROLLBACK_SNAPSHOT_ARTIFACTS_UNAVAILABLE" in content
    assert "CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE" in content
    assert "IS_CI" in content
    assert "_require_snapshot_artifact" in content
    assert "_require_memory_artifact" in content
    print("PASS: 09d_contains_ci_snapshot_artifact_skip")


def test_visual_trace_contains_ci_backend_skip():
    path = REPO_ROOT / "tests/smoke/test_visual_trace_8092_canonical_path_fix_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_BACKEND_8091_UNAVAILABLE" in content
    assert "IS_CI" in content
    assert "_require_backend" in content
    print("PASS: visual_trace_contains_ci_backend_skip")


def test_faiss_rebuild_contains_ci_memory_skip():
    path = REPO_ROOT / "tests/smoke/test_agent_v2_faiss_rebuild_hydration_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE" in content
    assert "IS_CI" in content
    assert "_require_memory_artifact" in content
    print("PASS: faiss_rebuild_contains_ci_memory_skip")


def test_semantic_hygiene_contains_ci_memory_skip():
    path = REPO_ROOT / "tests/smoke/test_agent_v2_semantic_retrieval_hygiene_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_RUNTIME_MEMORY_ARTIFACTS_UNAVAILABLE" in content
    assert "IS_CI" in content
    assert "_require_memory_artifact" in content
    print("PASS: semantic_hygiene_contains_ci_memory_skip")


def test_app_js_checks_still_active():
    path = REPO_ROOT / "tests/smoke/test_visual_trace_8092_canonical_path_fix_01.py"
    content = path.read_text(encoding="utf-8")
    assert "test_dashboard_app_js_has_no_hardcoded_8091_trace_url" in content
    assert "test_dashboard_app_js_uses_same_origin_trace_proxy" in content
    print("PASS: app_js_checks_still_active")


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
    assert "test_p0_trading" not in content.lower()
    assert "test_qc" not in content.lower()
    assert "test_ibkr" not in content.lower()
    assert "test_broker" not in content.lower()
    print("PASS: workflow_does_not_invoke_trading")


def test_no_memory_files_staged():
    import subprocess
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
    import subprocess
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Guard failed: {result.stdout}\n{result.stderr}"
    print("PASS: guard_passes")


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


if __name__ == "__main__":
    test_09e_contains_ci_memory_artifact_skip()
    test_09d_contains_ci_snapshot_artifact_skip()
    test_visual_trace_contains_ci_backend_skip()
    test_faiss_rebuild_contains_ci_memory_skip()
    test_semantic_hygiene_contains_ci_memory_skip()
    test_app_js_checks_still_active()
    test_workflow_includes_all_5_jobs()
    test_workflow_does_not_invoke_trading()
    test_no_memory_files_staged()
    test_guard_passes()
    test_local_memory_baseline_unchanged()
    test_blank_text_count_is_zero()
    test_duplicate_id_count_is_zero()
    print("\nALL UNPATCHED STEPS ARTIFACT-AWARE FIX VERIFICATION TESTS PASSED")
