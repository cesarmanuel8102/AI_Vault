"""Smoke test for FRONT-RUNTIME-RECOVERY-REAL-EXECUTION-GATE-01.

Validates:
1. real_execution_gate module loads and is pure Python.
2. Default readiness denies real execution.
3. Readiness allows only when all runtime fields true.
4. Safety flags are all False.
5. Missing required keys detected.
6. Staging hygiene checks.
7. ROADMAP_STATUS.json valid.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.real_execution_gate as reg


def test_module_imports_cleanly():
    assert callable(reg.build_real_execution_readiness)
    assert callable(reg.validate_real_execution_readiness)
    assert callable(reg.summarize_real_execution_readiness)


def test_default_readiness_denies_real_execution():
    readiness = reg.build_real_execution_readiness({}, {})
    assert readiness["real_execution_allowed"] is False
    assert readiness["dashboard_ok"] is False
    assert readiness["brain_server_ok"] is False
    assert readiness["ollama_ok"] is False
    assert readiness["operator_approval_visible"] is False
    assert readiness["git_tracked_clean"] is False
    assert readiness["roadmap_valid"] is False
    assert readiness["evidence_path_exists"] is False


def test_readiness_allows_when_all_true():
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
    # Because semantic_memory_write_allowed and faiss_write_allowed are hard False,
    # all_required should be True
    assert readiness["real_execution_allowed"] is True


def test_dashboard_false_blocks_execution():
    runtime = {
        "dashboard_ok": False,
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
    assert readiness["real_execution_allowed"] is False
    assert "dashboard not reachable" in readiness["denied_reasons"]


def test_brain_server_false_blocks_execution():
    runtime = {
        "dashboard_ok": True,
        "brain_server_ok": False,
        "ollama_ok": True,
        "git_tracked_clean": True,
        "roadmap_valid": True,
    }
    approval = {
        "operator_approval_visible": True,
        "evidence_path_exists": True,
    }
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False
    assert "brain server not reachable" in readiness["denied_reasons"]


def test_ollama_false_blocks_execution():
    runtime = {
        "dashboard_ok": True,
        "brain_server_ok": True,
        "ollama_ok": False,
        "git_tracked_clean": True,
        "roadmap_valid": True,
    }
    approval = {
        "operator_approval_visible": True,
        "evidence_path_exists": True,
    }
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False
    assert "ollama not reachable" in readiness["denied_reasons"]


def test_operator_approval_not_visible_blocks_execution():
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


def test_tracked_dirty_blocks_execution():
    runtime = {
        "dashboard_ok": True,
        "brain_server_ok": True,
        "ollama_ok": True,
        "git_tracked_clean": False,
        "roadmap_valid": True,
    }
    approval = {
        "operator_approval_visible": True,
        "evidence_path_exists": True,
    }
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False
    assert "git working tree not clean" in readiness["denied_reasons"]


def test_roadmap_invalid_blocks_execution():
    runtime = {
        "dashboard_ok": True,
        "brain_server_ok": True,
        "ollama_ok": True,
        "git_tracked_clean": True,
        "roadmap_valid": False,
    }
    approval = {
        "operator_approval_visible": True,
        "evidence_path_exists": True,
    }
    readiness = reg.build_real_execution_readiness(runtime, approval)
    assert readiness["real_execution_allowed"] is False
    assert "ROADMAP JSON invalid" in readiness["denied_reasons"]


def test_semantic_memory_write_remains_false():
    readiness = reg.build_real_execution_readiness(
        {"dashboard_ok": True, "brain_server_ok": True, "ollama_ok": True, "git_tracked_clean": True, "roadmap_valid": True},
        {"operator_approval_visible": True, "evidence_path_exists": True},
    )
    assert readiness["semantic_memory_write_allowed"] is False


def test_faiss_write_remains_false():
    readiness = reg.build_real_execution_readiness(
        {"dashboard_ok": True, "brain_server_ok": True, "ollama_ok": True, "git_tracked_clean": True, "roadmap_valid": True},
        {"operator_approval_visible": True, "evidence_path_exists": True},
    )
    assert readiness["faiss_write_allowed"] is False


def test_validate_returns_ok_for_valid_denied_result():
    readiness = reg.build_real_execution_readiness({}, {})
    validation = reg.validate_real_execution_readiness(readiness)
    assert validation["ok"] is True


def test_validate_returns_ok_for_valid_allowed_result():
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
    validation = reg.validate_real_execution_readiness(readiness)
    assert validation["ok"] is True


def test_summarize_returns_expected_fields():
    readiness = reg.build_real_execution_readiness({}, {})
    summary = reg.summarize_real_execution_readiness(readiness)
    assert summary["real_execution_allowed"] is False
    assert summary["dashboard_ok"] is False
    assert summary["brain_server_ok"] is False
    assert summary["ollama_ok"] is False
    assert summary["operator_approval_visible"] is False
    assert summary["git_tracked_clean"] is False
    assert summary["roadmap_valid"] is False
    assert summary["evidence_path_exists"] is False
    assert summary["semantic_memory_write_allowed"] is False
    assert summary["faiss_write_allowed"] is False
    assert summary["denied_reasons_count"] > 0


def test_safety_flags_present():
    readiness = reg.build_real_execution_readiness({}, {})
    flags = readiness["safety_flags"]
    assert flags["ingestion_executed"] is False
    assert flags["memory_write_executed"] is False
    assert flags["faiss_write_executed"] is False
    assert flags["network_called"] is False
    assert flags["connector_called"] is False
    assert flags["content_read"] is False
    assert flags["promotion_executed"] is False


def test_no_network_imports_in_module():
    src = Path("brain/real_execution_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    bad = [
        i
        for i in imports
        if any(b in i for b in ("requests", "httpx", "aiohttp", "urllib"))
    ]
    assert not bad, f"Forbidden network imports found: {bad}"


def test_no_file_io_in_module():
    src = Path("brain/real_execution_gate.py").read_text(encoding="utf-8")
    assert "open(" not in src
    assert ".read_text(" not in src
    assert ".write_text(" not in src


def test_runtime_health_check_script_exists():
    assert Path("scripts/ops/runtime_health_check.ps1").is_file()


def test_runtime_recovery_runbook_exists():
    assert Path("docs/RUNTIME_RECOVERY_RUNBOOK.md").is_file()


def test_real_execution_policy_exists():
    assert Path("docs/REAL_EXECUTION_POLICY.md").is_file()


def test_no_memory_semantic_staged():
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
        bad = any(
            "trading" in line or "b8" in line.lower() for line in lines
        )
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


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0
