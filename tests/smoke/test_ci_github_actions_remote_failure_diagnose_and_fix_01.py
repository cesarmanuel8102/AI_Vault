"""
Smoke test: CI GitHub Actions Remote Failure Diagnose and Fix
Verifies all CI-included smoke tests are portable (no hardcoded paths),
and that tests/_repo_root.py helper resolves correctly.
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tests._repo_root import REPO_ROOT


def test_repo_root_resolves():
    assert REPO_ROOT.exists(), f"REPO_ROOT does not exist: {REPO_ROOT}"
    print(f"PASS: repo_root_resolves ({REPO_ROOT})")


def test_no_hardcoded_ai_vault_paths_in_ci_tests():
    smoke_dir = REPO_ROOT / "tests" / "smoke"
    ci_tests = [
        "test_p0_nontrading_security_reality_check_and_fix_01.py",
        "test_post_09e_nontrading_roadmap_rebase_01.py",
        "test_09e_retrieval_quality_memory_utility_evaluation_01.py",
        "test_memory_historical_debt_cleanup_01.py",
        "test_09d_post_write_reconciliation_repair_01.py",
        "test_agent_v2_faiss_rebuild_hydration_01.py",
        "test_visual_trace_8092_canonical_path_fix_01.py",
        "test_ci_smoke_regression_expansion_01.py",
        "test_e2e_self_learning_loop_nontrading_01.py",
    ]
    for name in ci_tests:
        fpath = smoke_dir / name
        content = fpath.read_text()
        matches = list(re.finditer(r'AI_VAULT_CANONICAL', content))
        assert not matches, f"Found hardcoded path in {name}: {len(matches)} occurrences"
    print(f"PASS: no_hardcoded_ai_vault_paths_in_ci_tests ({len(ci_tests)} files checked)")


def test_all_ci_tests_import_repo_root():
    smoke_dir = REPO_ROOT / "tests" / "smoke"
    ci_tests = [
        "test_p0_nontrading_security_reality_check_and_fix_01.py",
        "test_post_09e_nontrading_roadmap_rebase_01.py",
        "test_09e_retrieval_quality_memory_utility_evaluation_01.py",
        "test_memory_historical_debt_cleanup_01.py",
        "test_09d_post_write_reconciliation_repair_01.py",
        "test_agent_v2_faiss_rebuild_hydration_01.py",
        "test_visual_trace_8092_canonical_path_fix_01.py",
        "test_ci_smoke_regression_expansion_01.py",
        "test_e2e_self_learning_loop_nontrading_01.py",
    ]
    for name in ci_tests:
        fpath = smoke_dir / name
        content = fpath.read_text()
        assert 'from tests._repo_root import REPO_ROOT' in content, f"Missing import in {name}"
    print(f"PASS: all_ci_tests_import_repo_root ({len(ci_tests)} files checked)")


def test_all_ci_tests_compile():
    import py_compile
    smoke_dir = REPO_ROOT / "tests" / "smoke"
    ci_tests = [
        "test_p0_nontrading_security_reality_check_and_fix_01.py",
        "test_post_09e_nontrading_roadmap_rebase_01.py",
        "test_09e_retrieval_quality_memory_utility_evaluation_01.py",
        "test_memory_historical_debt_cleanup_01.py",
        "test_09d_post_write_reconciliation_repair_01.py",
        "test_agent_v2_faiss_rebuild_hydration_01.py",
        "test_visual_trace_8092_canonical_path_fix_01.py",
        "test_ci_smoke_regression_expansion_01.py",
        "test_e2e_self_learning_loop_nontrading_01.py",
    ]
    for name in ci_tests:
        fpath = smoke_dir / name
        py_compile.compile(str(fpath), doraise=True)
    print(f"PASS: all_ci_tests_compile ({len(ci_tests)} files checked)")


def test_workflow_file_exists():
    wf = REPO_ROOT / ".github" / "workflows" / "nontrading-smoke-regression.yml"
    assert wf.exists(), "Workflow file missing"
    content = wf.read_text()
    assert 'PYTHONPATH' in content or 'python -m pytest' in content, "Workflow should run pytest"
    print("PASS: workflow_file_exists")


if __name__ == "__main__":
    test_repo_root_resolves()
    test_no_hardcoded_ai_vault_paths_in_ci_tests()
    test_all_ci_tests_import_repo_root()
    test_all_ci_tests_compile()
    test_workflow_file_exists()
    print("\nALL CI GITHUB ACTIONS REMOTE FAILURE DIAGNOSE AND FIX TESTS PASSED")
