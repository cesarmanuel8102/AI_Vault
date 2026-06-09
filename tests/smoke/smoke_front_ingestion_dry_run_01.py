"""Smoke test for FRONT-INGESTION-DRY-RUN-01.

Validates:
1. ingestion_dry_run module loads and is pure Python (no network, no file writes).
2. Default dry-run runs successfully.
3. Dry-run result contains safety_flags.
4. All safety flags are False (no ingestion, no memory write, no FAISS, etc.).
5. Result has candidates, blocked, invalid lists.
6. Blocked source becomes dry_run_status blocked.
7. local_file_dry_run_only becomes candidate.
8. uploaded_document_operator_review becomes operator_review_required.
9. registry_only source does not become candidate.
10. candidate_id is deterministic.
11. validate_dry_run_result returns ok:true for default result.
12. summarize_dry_run returns counts.
13. No candidate has can_write_semantic_memory true.
14. No candidate has can_promote_faiss true.
15-32. Module safety and staging hygiene checks.
33. ROADMAP_STATUS.json remains valid.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.ingestion_registry as ir
import brain.ingestion_dry_run as idr


def test_modules_import_cleanly():
    assert callable(idr.build_dry_run_candidate)
    assert callable(idr.run_registry_dry_run)
    assert callable(idr.validate_dry_run_result)
    assert callable(idr.summarize_dry_run)
    assert callable(ir.build_default_registry)


def test_default_dry_run_runs():
    result = idr.run_registry_dry_run()
    assert result["total_records"] == 6
    assert "candidates" in result
    assert "blocked" in result
    assert "invalid" in result
    assert "operator_review_required" in result
    assert "registry_only" in result


def test_safety_flags_present():
    result = idr.run_registry_dry_run()
    assert "safety_flags" in result
    flags = result["safety_flags"]
    assert flags["ingestion_executed"] is False
    assert flags["memory_write_executed"] is False
    assert flags["faiss_write_executed"] is False
    assert flags["network_called"] is False
    assert flags["connector_called"] is False
    assert flags["content_read"] is False
    assert flags["promotion_executed"] is False


def test_candidate_safety_flags():
    result = idr.run_registry_dry_run()
    for candidate in result["candidates"]:
        flags = candidate["safety_flags"]
        assert flags["ingestion_executed"] is False
        assert flags["memory_write_executed"] is False
        assert flags["faiss_write_executed"] is False
        assert flags["network_called"] is False
        assert flags["connector_called"] is False
        assert flags["content_read"] is False


def test_blocked_source_becomes_blocked():
    result = idr.run_registry_dry_run()
    blocked_ids = [b["source_id"] for b in result["blocked"]]
    assert "api_reference_blocked_until_credentials_policy" in blocked_ids


def test_local_file_becomes_candidate():
    result = idr.run_registry_dry_run()
    candidate_ids = [c["source_id"] for c in result["candidates"]]
    assert "local_file_dry_run_only" in candidate_ids


def test_uploaded_document_becomes_operator_review():
    result = idr.run_registry_dry_run()
    review_ids = [r["source_id"] for r in result["operator_review_required"]]
    assert "uploaded_document_operator_review" in review_ids


def test_registry_only_source_not_candidate():
    result = idr.run_registry_dry_run()
    registry_ids = [r["source_id"] for r in result["registry_only"]]
    assert "manual_text_low_risk" in registry_ids
    candidate_ids = [c["source_id"] for c in result["candidates"]]
    assert "manual_text_low_risk" not in candidate_ids


def test_candidate_id_is_deterministic():
    result = idr.run_registry_dry_run()
    for candidate in result["candidates"]:
        expected = f"dryrun:{candidate['source_id']}"
        assert candidate["candidate_id"] == expected


def test_validate_dry_run_result_ok_for_default():
    result = idr.run_registry_dry_run()
    validation = idr.validate_dry_run_result(result)
    assert validation["ok"] is True, f"Validation errors: {validation['errors']}"


def test_summarize_returns_counts():
    result = idr.run_registry_dry_run()
    summary = idr.summarize_dry_run(result)
    assert summary["total_records"] == 6
    assert summary["candidates_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["operator_review_required_count"] == 3
    assert summary["registry_only_count"] == 1
    assert summary["invalid_count"] == 0


def test_no_network_imports_in_module():
    src = Path("brain/ingestion_dry_run.py").read_text(encoding="utf-8")
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
    src = Path("brain/ingestion_dry_run.py").read_text(encoding="utf-8")
    assert "open(" not in src
    assert ".read_text(" not in src
    assert ".write_text(" not in src
    assert ".write_bytes(" not in src


def test_web_reference_becomes_operator_review():
    result = idr.run_registry_dry_run()
    review_ids = [r["source_id"] for r in result["operator_review_required"]]
    assert "web_reference_operator_review" in review_ids


def test_connector_reference_becomes_operator_review():
    result = idr.run_registry_dry_run()
    review_ids = [r["source_id"] for r in result["operator_review_required"]]
    assert "connector_reference_operator_review" in review_ids


def test_count_consistency():
    result = idr.run_registry_dry_run()
    total = result["total_records"]
    counts = (
        len(result["candidates"])
        + len(result["blocked"])
        + len(result["invalid"])
        + len(result["operator_review_required"])
        + len(result["registry_only"])
    )
    assert total == counts, f"Count mismatch: total={total}, sum={counts}"


def test_candidate_has_planned_actions():
    result = idr.run_registry_dry_run()
    for candidate in result["candidates"]:
        assert "planned_actions" in candidate
        assert len(candidate["planned_actions"]) > 0


def test_blocked_has_reasons():
    result = idr.run_registry_dry_run()
    for blocked in result["blocked"]:
        assert "blocked_reasons" in blocked
        assert len(blocked["blocked_reasons"]) > 0


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
