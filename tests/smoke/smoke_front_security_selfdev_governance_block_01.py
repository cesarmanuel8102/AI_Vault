"""Smoke test for FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01.

Validates:
1. protected_paths.py module loads and classifies paths correctly.
2. Extended protected path coverage (.env, memory/semantic/, session.py,
   curated_runtime_lookup.py, governance/, security/, api_security.py, etc.).
3. Ledger paths are recognized as allowed during dedicated fronts.
4. ExecutionGate blocks protected path edits even with GOD mode active.
5. Normal paths remain editable.
6. Staging hygiene: no protected files staged.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Ensure tmp_agent is on sys.path so brain_v9 imports resolve
_TMP_AGENT = str(Path(__file__).resolve().parent.parent.parent / "tmp_agent")
if _TMP_AGENT not in sys.path:
    sys.path.insert(0, _TMP_AGENT)

from brain_v9.governance.protected_paths import (
    is_protected_path,
    is_ledger_path,
    assert_not_protected_path,
    classify_path_protection,
    normalize_repo_path,
)


def test_normalize_repo_path():
    assert normalize_repo_path("C:/AI_VAULT/tmp_agent/foo.py") == "tmp_agent/foo.py"
    assert normalize_repo_path("/AI_VAULT/governance/x.py") == "governance/x.py"
    assert normalize_repo_path("./memory/semantic/data.jsonl") == "memory/semantic/data.jsonl"
    assert normalize_repo_path("tmp_agent\\brain_v9\\governance") == "tmp_agent/brain_v9/governance"
    assert normalize_repo_path("") == ""


def test_is_protected_path_extended_coverage():
    """New paths protected by FRONT-SECURITY-SELFDEV-GOVERNANCE-BLOCK-01."""
    protected = [
        ".env",
        ".dev_auth/token.json",
        "memory/semantic/semantic_memory.jsonl",
        "memory/semantic/semantic_memory_faiss.index",
        "tmp_agent/brain_v9/core/session.py",
        "brain_v9/core/session.py",
        "core/session.py",
        "session.py",
        "brain/curated_runtime_lookup.py",
        "curated_runtime_lookup.py",
        "tmp_agent/brain_v9/governance/execution_gate.py",
        "brain_v9/governance/ethics_kernel.py",
        "governance/approval.py",
        "tmp_agent/brain_v9/security/rbac.py",
        "brain_v9/security/trace_redactor.py",
        "security/api_security.py",
        "tmp_agent/brain_v9/api_security.py",
        "tmp_agent/brain_v9/trace_redactor.py",
    ]
    for p in protected:
        assert is_protected_path(p), f"Expected protected: {p}"


def test_is_protected_path_allows_normal_paths():
    safe = [
        "tmp_agent/brain_v9/ui/dashboard.py",
        "tmp_agent/scripts/helper.py",
        "docs/README.md",
        "tmp_agent/strategies/mean_reversion_eq/main.py",
        "brain_v9/core/settings.py",
        "tmp_agent/brain_v9/chat_area_upgrade/router.py",
    ]
    for p in safe:
        assert not is_protected_path(p), f"Expected NOT protected: {p}"


def test_proposal_governance_protected_by_basename_token():
    # Files with "governance" in basename are protected regardless of directory,
    # consistent with execution_gate.py legacy behavior.
    assert is_protected_path("tmp_agent/brain_v9/learning/proposal_governance.py") is True


def test_is_ledger_path():
    assert is_ledger_path("ROADMAP_STATUS.json") is True
    assert is_ledger_path("docs/MIGRATION_CONTROL_LEDGER.md") is True
    assert is_ledger_path("roadmap_status.json") is True  # case-insensitive
    assert is_ledger_path("tmp_agent/ROADMAP_STATUS.json") is False
    assert is_ledger_path("README.md") is False


def test_assert_not_protected_path_blocks():
    try:
        assert_not_protected_path("tmp_agent/brain_v9/governance/execution_gate.py")
    except PermissionError as exc:
        assert "Protected path modification denied" in str(exc)
    else:
        raise AssertionError("Expected PermissionError for protected path")


def test_assert_not_protected_path_allows_ledger():
    # Should NOT raise when allow_ledger=True
    assert_not_protected_path("ROADMAP_STATUS.json", allow_ledger=True)


def test_classify_path_protection_metadata():
    result = classify_path_protection("tmp_agent/brain_v9/governance/execution_gate.py")
    assert result["is_protected"] is True
    assert result["reason"] == "exact_basename_match"

    result2 = classify_path_protection("tmp_agent/brain_v9/ui/dashboard.py")
    assert result2["is_protected"] is False
    assert result2["reason"] == "not_protected"


def test_execution_gate_blocks_god_mode_on_protected_paths():
    from brain_v9.governance.execution_gate import ExecutionGate, ExecutionMode

    gate = ExecutionGate.__new__(ExecutionGate)
    gate._mode = ExecutionMode.BUILD
    gate._pending = []
    gate._god_sessions = {}
    gate._save_state = lambda: None
    gate._audit_log = lambda *a, **kw: None

    sid = "test_god_protected"
    gate._god_sessions[sid] = {"active": True}

    from brain_v9.governance.execution_gate import push_god_session, pop_god_session
    tok = push_god_session(sid)
    try:
        result = gate.check(
            "edit_file",
            {"path": "tmp_agent/brain_v9/core/session.py"},
            session_id=sid,
        )
    finally:
        pop_god_session(tok)

    assert result["allowed"] is False
    assert "SELFDEV_PROTECTED_GOVERNANCE_SECURITY_PATH" in result["reason"]
    assert result["action"] == "blocked"
    assert result.get("requires_human_approval") is True


def test_execution_gate_allows_normal_paths_in_god_mode():
    from brain_v9.governance.execution_gate import ExecutionGate, ExecutionMode

    gate = ExecutionGate.__new__(ExecutionGate)
    gate._mode = ExecutionMode.BUILD
    gate._pending = []
    gate._god_sessions = {}
    gate._save_state = lambda: None
    gate._audit_log = lambda *a, **kw: None

    sid = "test_god_normal"
    gate._god_sessions[sid] = {"active": True}

    from brain_v9.governance.execution_gate import push_god_session, pop_god_session
    tok = push_god_session(sid)
    try:
        result = gate.check(
            "edit_file",
            {"path": "tmp_agent/brain_v9/ui/dashboard.py"},
            session_id=sid,
        )
    finally:
        pop_god_session(tok)

    assert result["allowed"] is True
    assert result.get("god_mode") is True


def test_execution_gate_blocks_memory_semantic_via_god():
    from brain_v9.governance.execution_gate import ExecutionGate, ExecutionMode

    gate = ExecutionGate.__new__(ExecutionGate)
    gate._mode = ExecutionMode.BUILD
    gate._pending = []
    gate._god_sessions = {}
    gate._save_state = lambda: None
    gate._audit_log = lambda *a, **kw: None

    sid = "test_god_memory"
    gate._god_sessions[sid] = {"active": True}

    from brain_v9.governance.execution_gate import push_god_session, pop_god_session
    tok = push_god_session(sid)
    try:
        result = gate.check(
            "write_file",
            {"path": "memory/semantic/semantic_memory.jsonl"},
            session_id=sid,
        )
    finally:
        pop_god_session(tok)

    assert result["allowed"] is False
    assert "SELFDEV_PROTECTED_GOVERNANCE_SECURITY_PATH" in result["reason"]


def test_no_memory_semantic_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic" not in staged


def test_no_faiss_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "faiss" not in staged.lower()


def test_no_env_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_session_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_no_curated_runtime_lookup_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "curated_runtime_lookup.py" not in staged


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True, text=True, cwd="."
    )
    assert result.returncode == 0
