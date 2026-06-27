"""
Smoke test: FRONT-CI-MEMORY-09E-ONLY-FINAL-FIX-03 Verification
Verifies that 09E test file is fully guarded for CI.
"""

import os
import sys
import subprocess
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


def test_09e_contains_ci_backend_skip():
    path = REPO_ROOT / "tests/smoke/test_09e_retrieval_quality_memory_utility_evaluation_01.py"
    content = path.read_text(encoding="utf-8")
    assert "CI_BACKEND_AGENT_V2_UNAVAILABLE" in content
    print("PASS: 09e_contains_ci_backend_skip")


def test_09e_all_main_functions_guarded():
    path = REPO_ROOT / "tests/smoke/test_09e_retrieval_quality_memory_utility_evaluation_01.py"
    content = path.read_text(encoding="utf-8")
    
    # Find all function calls in __main__
    main_block = content.split("if __name__ == \"__main__\":")[-1]
    lines = [l.strip() for l in main_block.splitlines() if l.strip().startswith("test_")]
    
    guarded = []
    unguarded = []
    
    for line in lines:
        func_name = line.split("(")[0].strip()
        # Check if this function has a guard
        func_pattern = f"def {func_name}("
        func_idx = content.find(func_pattern)
        if func_idx > 0:
            func_block = content[func_idx:func_idx+500]
            if "_require_memory_artifact" in func_block or "socket.create_connection" in func_block or "subprocess.run" in func_block:
                guarded.append(func_name)
            else:
                unguarded.append(func_name)
    
    assert not unguarded, f"Unguarded functions in __main__: {unguarded}"
    print(f"PASS: all_main_functions_guarded ({len(guarded)} functions)")


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


def test_workflow_includes_memory_retrieval():
    path = REPO_ROOT / ".github/workflows/nontrading-smoke-regression.yml"
    content = path.read_text(encoding="utf-8")
    assert "memory-retrieval:" in content
    assert "09E Retrieval Quality Evaluation" in content
    print("PASS: workflow_includes_memory_retrieval")


def test_workflow_does_not_invoke_trading():
    path = REPO_ROOT / ".github/workflows/nontrading-smoke-regression.yml"
    content = path.read_text(encoding="utf-8")
    assert "test_p0_trading" not in content.lower()
    assert "test_qc" not in content.lower()
    assert "test_ibkr" not in content.lower()
    assert "test_broker" not in content.lower()
    print("PASS: workflow_does_not_invoke_trading")


if __name__ == "__main__":
    test_09e_contains_ci_memory_artifact_skip()
    test_09e_contains_ci_backend_skip()
    test_09e_all_main_functions_guarded()
    test_no_memory_files_staged()
    test_guard_passes()
    test_local_memory_baseline_unchanged()
    test_blank_text_count_is_zero()
    test_duplicate_id_count_is_zero()
    test_workflow_includes_memory_retrieval()
    test_workflow_does_not_invoke_trading()
    print("\nALL 09E FINAL FIX VERIFICATION TESTS PASSED")
