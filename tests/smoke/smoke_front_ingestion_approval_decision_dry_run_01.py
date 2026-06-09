"""Smoke test for FRONT-INGESTION-APPROVAL-DECISION-DRY-RUN-01.

Validates:
1. ingestion_approval_decision_dry_run module loads and is pure Python.
2. Default approval decision dry-run builds.
3. Safety flags are all False.
4. Decision statuses are correct for default decisions.
5. No decision authorizes real ingestion.
6. No decision allows memory/FAISS write.
7. Invalid requested decisions become denied.
8. Decision structure is correct.
9. Staging hygiene checks.
10. ROADMAP_STATUS.json valid.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.ingestion_approval_decision_dry_run as iad
import brain.ingestion_operator_review as ior


def test_modules_import_cleanly():
    assert callable(iad.build_decision_id)
    assert callable(iad.apply_decision_to_item)
    assert callable(iad.run_approval_decision_dry_run)
    assert callable(iad.validate_decision_result)
    assert callable(iad.summarize_decision_result)
    assert callable(iad.default_requested_decision_for_item)


def test_default_decision_dry_run_builds():
    result = iad.run_approval_decision_dry_run()
    assert result["total_records"] == 6
    assert "decisions" in result
    assert len(result["decisions"]) == 6


def test_safety_flags_present():
    result = iad.run_approval_decision_dry_run()
    flags = result["safety_flags"]
    assert flags["ingestion_executed"] is False
    assert flags["memory_write_executed"] is False
    assert flags["faiss_write_executed"] is False
    assert flags["network_called"] is False
    assert flags["connector_called"] is False
    assert flags["content_read"] is False
    assert flags["promotion_executed"] is False


def test_decision_safety_flags():
    result = iad.run_approval_decision_dry_run()
    for d in result["decisions"]:
        flags = d["safety_flags"]
        assert flags["ingestion_executed"] is False
        assert flags["memory_write_executed"] is False


def test_pending_defaults_to_request_more_context():
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"]
    assert len(pending) > 0
    item = pending[0]
    default = iad.default_requested_decision_for_item(item)
    assert default == "request_more_context"


def test_approve_maps_to_accepted():
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"]
    assert len(pending) > 0
    item = pending[0]
    decision = iad.apply_decision_to_item(item, "approve_for_future_dry_run")
    assert decision["decision_status"] == "accepted_for_future_dry_run"
    assert decision["allowed_next_step"] == "future_controlled_dry_run_only"


def test_accepted_does_not_authorize_real_ingestion():
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"]
    item = pending[0]
    decision = iad.apply_decision_to_item(item, "approve_for_future_dry_run")
    assert decision["approval_authorizes_real_ingestion"] is False


def test_accepted_does_not_allow_memory_write():
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"]
    item = pending[0]
    decision = iad.apply_decision_to_item(item, "approve_for_future_dry_run")
    assert decision["can_write_semantic_memory"] is False


def test_accepted_does_not_allow_faiss_promotion():
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"]
    item = pending[0]
    decision = iad.apply_decision_to_item(item, "approve_for_future_dry_run")
    assert decision["can_promote_faiss"] is False


def test_blocked_remains_kept_blocked():
    queue = ior.build_review_queue()
    blocked = queue["blocked"]
    assert len(blocked) > 0
    item = blocked[0]
    decision = iad.apply_decision_to_item(item, "keep_blocked")
    assert decision["decision_status"] == "kept_blocked"


def test_registry_only_no_action():
    queue = ior.build_review_queue()
    reg_only = queue["registry_only"]
    assert len(reg_only) > 0
    item = reg_only[0]
    decision = iad.apply_decision_to_item(item, "no_action")
    assert decision["decision_status"] == "no_action"


def test_invalid_requested_decision_denied():
    queue = ior.build_review_queue()
    blocked = queue["blocked"]
    assert len(blocked) > 0
    item = blocked[0]
    decision = iad.apply_decision_to_item(item, "approve_for_future_dry_run")
    assert decision["decision_status"] == "denied_invalid_decision"


def test_decision_id_is_deterministic():
    queue = ior.build_review_queue()
    item = queue["items"][0]
    decision = iad.apply_decision_to_item(item)
    expected = f"decision:{item['review_id']}"
    assert decision["decision_id"] == expected


def test_validate_decision_result_ok():
    result = iad.run_approval_decision_dry_run()
    validation = iad.validate_decision_result(result)
    assert validation["ok"] is True, f"Errors: {validation['errors']}"


def test_summarize_decision_result():
    result = iad.run_approval_decision_dry_run()
    summary = iad.summarize_decision_result(result)
    assert summary["total_records"] == 6
    assert summary["more_context_required_count"] == 4
    assert summary["kept_blocked_count"] == 1
    assert summary["no_action_count"] == 1


def test_count_consistency():
    result = iad.run_approval_decision_dry_run()
    total = result["total_records"]
    counts = (
        len(result["accepted_for_future_dry_run"])
        + len(result["rejected"])
        + len(result["more_context_required"])
        + len(result["kept_blocked"])
        + len(result["no_action"])
        + len(result["denied_invalid_decision"])
    )
    assert total == counts


def test_no_network_imports_in_module():
    src = Path("brain/ingestion_approval_decision_dry_run.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    bad = [i for i in imports if any(b in i for b in ("requests", "httpx", "aiohttp", "urllib"))]
    assert not bad, f"Forbidden network imports found: {bad}"


def test_no_file_io_in_module():
    src = Path("brain/ingestion_approval_decision_dry_run.py").read_text(encoding="utf-8")
    assert "open(" not in src
    assert ".read_text(" not in src
    assert ".write_text(" not in src


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


def test_no_trading_or_b8_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


def test_no_session_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_no_main_py_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "main.py" not in staged


def test_no_curated_runtime_lookup_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "curated_runtime_lookup.py" not in staged


def test_no_execution_gate_staged():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status"],
        capture_output=True, text=True, cwd="."
    )
    staged = result.stdout.strip()
    if staged:
        assert "execution_gate.py" not in staged


def test_roadmap_status_json_valid():
    result = subprocess.run(
        ["python", "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True, text=True, cwd="."
    )
    assert result.returncode == 0
