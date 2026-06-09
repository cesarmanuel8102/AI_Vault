"""Smoke test for FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-01.

Validates:
1. ingestion_manual_approval_sample module loads and is pure Python.
2. Default approved sample has one planned item.
3. Synthetic denied sample has one rejected item.
4. Safety flags are all False.
5. No execution item claims real ingestion.
6. Count consistency across pipeline stages.
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

import brain.ingestion_manual_approval_sample as imas


def test_modules_import_cleanly():
    assert callable(imas.build_synthetic_approved_registry)
    assert callable(imas.build_synthetic_denied_registry)
    assert callable(imas.run_manual_approval_sample)
    assert callable(imas.validate_manual_approval_sample)
    assert callable(imas.summarize_manual_approval_sample)


def test_default_sample_runs():
    result = imas.run_manual_approval_sample()
    assert result["total_records"] == 1
    assert result["registry_valid"] is True
    assert "dry_run_result" in result
    assert "review_queue" in result
    assert "default_decision_result" in result
    assert "synthetic_decision_result" in result
    assert "execution_result" in result


def test_synthetic_approved_reaches_planned():
    result = imas.run_manual_approval_sample()
    exec_result = result["execution_result"]
    assert len(exec_result["reviewed_dry_run_planned"]) == 1
    item = exec_result["reviewed_dry_run_planned"][0]
    assert item["source_id"] == "synthetic_approved_document"
    assert item["execution_status"] == "reviewed_dry_run_planned"
    assert item["allowed_execution_mode"] == "future_controlled_dry_run_only"


def test_synthetic_denied_reaches_rejected():
    denied_registry = imas.build_synthetic_denied_registry()
    result = imas.run_manual_approval_sample(denied_registry)
    exec_result = result["execution_result"]
    assert len(exec_result["rejected"]) == 1
    item = exec_result["rejected"][0]
    assert item["source_id"] == "synthetic_denied_document"
    assert item["execution_status"] == "rejected"


def test_safety_flags_present():
    result = imas.run_manual_approval_sample()
    flags = result["safety_flags"]
    assert flags["ingestion_executed"] is False
    assert flags["memory_write_executed"] is False
    assert flags["faiss_write_executed"] is False
    assert flags["network_called"] is False
    assert flags["connector_called"] is False
    assert flags["content_read"] is False
    assert flags["promotion_executed"] is False


def test_no_item_allows_real_ingestion():
    result = imas.run_manual_approval_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["allowed_execution_mode"] in ("none", "future_controlled_dry_run_only")


def test_no_item_reads_content():
    result = imas.run_manual_approval_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["content_read"] is False


def test_no_item_allows_memory_write():
    result = imas.run_manual_approval_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["memory_write_executed"] is False


def test_no_item_allows_faiss_promotion():
    result = imas.run_manual_approval_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["faiss_write_executed"] is False


def test_validate_returns_ok():
    result = imas.run_manual_approval_sample()
    validation = imas.validate_manual_approval_sample(result)
    assert validation["ok"] is True, f"Errors: {validation['errors']}"


def test_summarize_returns_counts():
    result = imas.run_manual_approval_sample()
    summary = imas.summarize_manual_approval_sample(result)
    assert summary["total_records"] == 1
    assert summary["reviewed_dry_run_planned_count"] == 1
    assert summary["synthetic_accepted_count"] == 1
    assert summary["reviewed_dry_run_skipped_no_approval_count"] == 0
    assert summary["blocked_count"] == 0
    assert summary["no_action_count"] == 0
    assert summary["rejected_count"] == 0
    assert summary["invalid_count"] == 0


def test_denied_sample_summary():
    denied_registry = imas.build_synthetic_denied_registry()
    result = imas.run_manual_approval_sample(denied_registry)
    summary = imas.summarize_manual_approval_sample(result)
    assert summary["total_records"] == 1
    assert summary["reviewed_dry_run_planned_count"] == 0
    assert summary["synthetic_accepted_count"] == 0
    assert summary["rejected_count"] == 1


def test_count_consistency():
    result = imas.run_manual_approval_sample()
    exec_result = result["execution_result"]
    total = exec_result["total_records"]
    counts = (
        len(exec_result["reviewed_dry_run_planned"])
        + len(exec_result["reviewed_dry_run_skipped_no_approval"])
        + len(exec_result["blocked"])
        + len(exec_result["no_action"])
        + len(exec_result["rejected"])
        + len(exec_result["invalid"])
    )
    assert total == counts


def test_no_network_imports_in_module():
    src = Path("brain/ingestion_manual_approval_sample.py").read_text(encoding="utf-8")
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
    src = Path("brain/ingestion_manual_approval_sample.py").read_text(encoding="utf-8")
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
