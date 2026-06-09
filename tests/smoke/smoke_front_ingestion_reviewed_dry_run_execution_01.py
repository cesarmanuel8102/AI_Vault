"""Smoke test for FRONT-INGESTION-REVIEWED-DRY-RUN-EXECUTION-01.

Validates:
1. ingestion_reviewed_dry_run_execution module loads and is pure Python.
2. Default reviewed dry-run execution builds.
3. Safety flags are all False.
4. Default result has zero approved execution items.
5. All 6 items are accounted for with correct statuses.
6. No execution item claims real ingestion.
7. Staging hygiene checks.
8. ROADMAP_STATUS.json valid.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.ingestion_reviewed_dry_run_execution as irde
import brain.ingestion_approval_decision_dry_run as iad
import brain.ingestion_operator_review as ior


def test_modules_import_cleanly():
    assert callable(irde.build_execution_id)
    assert callable(irde.build_execution_item)
    assert callable(irde.run_reviewed_dry_run_execution)
    assert callable(irde.validate_reviewed_dry_run_execution)
    assert callable(irde.summarize_reviewed_dry_run_execution)


def test_default_reviewed_dry_run_builds():
    result = irde.run_reviewed_dry_run_execution()
    assert result["total_records"] == 6
    assert "execution_items" in result
    assert len(result["execution_items"]) == 6


def test_safety_flags_present():
    result = irde.run_reviewed_dry_run_execution()
    flags = result["safety_flags"]
    assert flags["ingestion_executed"] is False
    assert flags["memory_write_executed"] is False
    assert flags["faiss_write_executed"] is False
    assert flags["network_called"] is False
    assert flags["connector_called"] is False
    assert flags["content_read"] is False
    assert flags["promotion_executed"] is False


def test_item_safety_flags():
    result = irde.run_reviewed_dry_run_execution()
    for item in result["execution_items"]:
        flags = item["safety_flags"]
        assert flags["ingestion_executed"] is False
        assert flags["memory_write_executed"] is False


def test_default_planned_count_is_zero():
    result = irde.run_reviewed_dry_run_execution()
    summary = irde.summarize_reviewed_dry_run_execution(result)
    assert summary["reviewed_dry_run_planned_count"] == 0


def test_default_skipped_count_is_four():
    result = irde.run_reviewed_dry_run_execution()
    summary = irde.summarize_reviewed_dry_run_execution(result)
    assert summary["reviewed_dry_run_skipped_no_approval_count"] == 4


def test_kept_blocked_is_blocked():
    result = irde.run_reviewed_dry_run_execution()
    assert len(result["blocked"]) == 1
    item = result["blocked"][0]
    assert item["source_id"] == "api_reference_blocked_until_credentials_policy"
    assert item["execution_status"] == "blocked"


def test_no_action_remains_no_action():
    result = irde.run_reviewed_dry_run_execution()
    assert len(result["no_action"]) == 1
    item = result["no_action"][0]
    assert item["source_id"] == "manual_text_low_risk"
    assert item["execution_status"] == "no_action"


def test_no_item_reads_content():
    result = irde.run_reviewed_dry_run_execution()
    for item in result["execution_items"]:
        assert item["safety_flags"]["content_read"] is False


def test_no_item_allows_memory_write():
    result = irde.run_reviewed_dry_run_execution()
    for item in result["execution_items"]:
        assert item["safety_flags"]["memory_write_executed"] is False


def test_no_item_allows_faiss_promotion():
    result = irde.run_reviewed_dry_run_execution()
    for item in result["execution_items"]:
        assert item["safety_flags"]["faiss_write_executed"] is False


def test_accepted_maps_to_planned_in_synthetic_test():
    # Create a synthetic accepted decision to verify mapping
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"][0]
    decision = iad.apply_decision_to_item(pending, "approve_for_future_dry_run")
    assert decision["decision_status"] == "accepted_for_future_dry_run"

    exec_item = irde.build_execution_item(decision)
    assert exec_item["execution_status"] == "reviewed_dry_run_planned"
    assert exec_item["allowed_execution_mode"] == "future_controlled_dry_run_only"


def test_more_context_maps_to_skipped():
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"][0]
    decision = iad.apply_decision_to_item(pending, "request_more_context")
    assert decision["decision_status"] == "more_context_required"

    exec_item = irde.build_execution_item(decision)
    assert exec_item["execution_status"] == "reviewed_dry_run_skipped_no_approval"
    assert exec_item["allowed_execution_mode"] == "none"


def test_execution_id_is_deterministic():
    decision = {"decision_id": "decision:test", "decision_status": "no_action", "source_id": "test"}
    item = irde.build_execution_item(decision)
    assert item["execution_id"] == "exec:decision:test"


def test_validate_returns_ok():
    result = irde.run_reviewed_dry_run_execution()
    validation = irde.validate_reviewed_dry_run_execution(result)
    assert validation["ok"] is True, f"Errors: {validation['errors']}"


def test_summarize_returns_counts():
    result = irde.run_reviewed_dry_run_execution()
    summary = irde.summarize_reviewed_dry_run_execution(result)
    assert summary["total_records"] == 6
    assert summary["reviewed_dry_run_planned_count"] == 0
    assert summary["reviewed_dry_run_skipped_no_approval_count"] == 4
    assert summary["blocked_count"] == 1
    assert summary["no_action_count"] == 1
    assert summary["rejected_count"] == 0
    assert summary["invalid_count"] == 0


def test_count_consistency():
    result = irde.run_reviewed_dry_run_execution()
    total = result["total_records"]
    counts = (
        len(result["reviewed_dry_run_planned"])
        + len(result["reviewed_dry_run_skipped_no_approval"])
        + len(result["blocked"])
        + len(result["no_action"])
        + len(result["rejected"])
        + len(result["invalid"])
    )
    assert total == counts


def test_no_network_imports_in_module():
    src = Path("brain/ingestion_reviewed_dry_run_execution.py").read_text(encoding="utf-8")
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
    src = Path("brain/ingestion_reviewed_dry_run_execution.py").read_text(encoding="utf-8")
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
