"""Smoke test for FRONT-RUNTIME-ACTUAL-STARTUP-VERIFY-01.

Validates runtime recovery artifacts and real execution gate behavior.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.real_execution_gate as reg


def test_real_execution_gate_imports():
    assert callable(reg.build_real_execution_readiness)
    assert callable(reg.validate_real_execution_readiness)
    assert callable(reg.summarize_real_execution_readiness)


def test_runtime_health_check_script_exists():
    assert Path("scripts/ops/runtime_health_check.ps1").is_file()


def test_runtime_recovery_runbook_exists():
    assert Path("docs/RUNTIME_RECOVERY_RUNBOOK.md").is_file()


def test_real_execution_policy_exists():
    assert Path("docs/REAL_EXECUTION_POLICY.md").is_file()


def test_front_doc_exists():
    assert Path("docs/FRONT_RUNTIME_ACTUAL_STARTUP_VERIFY_01.md").is_file()


def test_default_operator_approval_false_blocks_execution():
    runtime = {
        "dashboard_ok": True,
        "brain_server_ok": True,
        "ollama_ok": True,
        "git_tracked_clean": True,
        "roadmap_valid": True,
    }
    approval = {
        "operator_approval_visible": False,
        "evidence_path_exists": True,
    }
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False
    assert "operator approval not visible" in readiness["denied_reasons"]


def test_dashboard_ok_true_alone_does_not_allow_execution():
    runtime = {"dashboard_ok": True}
    approval = {}
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False


def test_brain_server_ok_true_alone_does_not_allow_execution():
    runtime = {"brain_server_ok": True}
    approval = {}
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False


def test_all_runtime_ok_but_approval_false_denies_execution():
    runtime = {
        "dashboard_ok": True,
        "brain_server_ok": True,
        "ollama_ok": True,
        "git_tracked_clean": True,
        "roadmap_valid": True,
    }
    approval = {
        "operator_approval_visible": False,
        "evidence_path_exists": True,
    }
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False


def test_all_runtime_ok_and_approval_true_allows_execution():
    runtime = {
        "dashboard_ok": True,
        "brain_server_ok": True,
        "ollama_ok": True,
        "git_tracked_clean": True,
        "roadmap_valid": True,
    }
    approval = {
        "operator_approval_visible": True,
        "evidence_path_exists": True,
    }
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is True


def test_semantic_memory_write_allowed_false():
    readiness = reg.build_real_execution_readiness(
        {"dashboard_ok": True, "brain_server_ok": True, "ollama_ok": True, "git_tracked_clean": True, "roadmap_valid": True},
        {"operator_approval_visible": True, "evidence_path_exists": True},
    )
    assert readiness["semantic_memory_write_allowed"] is False


def test_faiss_write_allowed_false():
    readiness = reg.build_real_execution_readiness(
        {"dashboard_ok": True, "brain_server_ok": True, "ollama_ok": True, "git_tracked_clean": True, "roadmap_valid": True},
        {"operator_approval_visible": True, "evidence_path_exists": True},
    )
    assert readiness["faiss_write_allowed"] is False


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0


def test_no_semantic_memory_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic" not in staged


def test_no_faiss_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "faiss" not in staged.lower()


def test_no_env_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_trading_or_b8_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


def test_no_session_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_no_main_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "main.py" not in staged


def test_no_curated_runtime_lookup_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "curated_runtime_lookup.py" not in staged


def test_no_execution_gate_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    staged = result.stdout.strip()
    if staged:
        assert "execution_gate.py" not in staged
