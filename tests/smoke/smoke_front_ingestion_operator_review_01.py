"""Smoke test for FRONT-INGESTION-OPERATOR-REVIEW-01.

Validates:
1. ingestion_operator_review module loads and is pure Python.
2. Default review queue builds successfully.
3. Safety flags are all False.
4. Review items have correct statuses for each dry-run type.
5. No item claims real ingestion authorization.
6. No item claims memory/FAISS write.
7. Review queue structure and counts are correct.
8. Module safety and staging hygiene.
9. ROADMAP_STATUS.json remains valid.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import brain.ingestion_operator_review as ior
import brain.ingestion_dry_run as idr


def test_modules_import_cleanly():
    assert callable(ior.build_review_id)
    assert callable(ior.build_review_item)
    assert callable(ior.build_review_queue)
    assert callable(ior.validate_review_queue)
    assert callable(ior.summarize_review_queue)
    assert callable(idr.run_registry_dry_run)


def test_default_review_queue_builds():
    queue = ior.build_review_queue()
    assert queue["total_records"] == 6
    assert "items" in queue
    assert "pending_operator_review" in queue
    assert "blocked" in queue
    assert "registry_only" in queue
    assert "not_reviewable" in queue


def test_safety_flags_present():
    queue = ior.build_review_queue()
    assert "safety_flags" in queue
    flags = queue["safety_flags"]
    assert flags["ingestion_executed"] is False
    assert flags["memory_write_executed"] is False
    assert flags["faiss_write_executed"] is False
    assert flags["network_called"] is False
    assert flags["connector_called"] is False
    assert flags["content_read"] is False
    assert flags["promotion_executed"] is False


def test_item_safety_flags():
    queue = ior.build_review_queue()
    for item in queue["items"]:
        flags = item["safety_flags"]
        assert flags["ingestion_executed"] is False
        assert flags["memory_write_executed"] is False


def test_local_file_pending_review():
    queue = ior.build_review_queue()
    ids = [i["source_id"] for i in queue["pending_operator_review"]]
    assert "local_file_dry_run_only" in ids


def test_uploaded_document_pending_review():
    queue = ior.build_review_queue()
    ids = [i["source_id"] for i in queue["pending_operator_review"]]
    assert "uploaded_document_operator_review" in ids


def test_connector_reference_pending_review():
    queue = ior.build_review_queue()
    ids = [i["source_id"] for i in queue["pending_operator_review"]]
    assert "connector_reference_operator_review" in ids


def test_web_reference_pending_review():
    queue = ior.build_review_queue()
    ids = [i["source_id"] for i in queue["pending_operator_review"]]
    assert "web_reference_operator_review" in ids


def test_api_reference_blocked():
    queue = ior.build_review_queue()
    ids = [i["source_id"] for i in queue["blocked"]]
    assert "api_reference_blocked_until_credentials_policy" in ids


def test_manual_text_registry_only():
    queue = ior.build_review_queue()
    ids = [i["source_id"] for i in queue["registry_only"]]
    assert "manual_text_low_risk" in ids


def test_no_real_ingestion_authorization():
    queue = ior.build_review_queue()
    for item in queue["items"]:
        assert item["approval_authorizes_real_ingestion"] is False


def test_no_can_write_semantic_memory():
    queue = ior.build_review_queue()
    for item in queue["items"]:
        assert item["can_write_semantic_memory"] is False


def test_no_can_promote_faiss():
    queue = ior.build_review_queue()
    for item in queue["items"]:
        assert item["can_promote_faiss"] is False


def test_validate_review_queue_ok():
    queue = ior.build_review_queue()
    result = ior.validate_review_queue(queue)
    assert result["ok"] is True, f"Errors: {result['errors']}"


def test_summarize_review_queue():
    queue = ior.build_review_queue()
    summary = ior.summarize_review_queue(queue)
    assert summary["total_records"] == 6
    assert summary["pending_operator_review_count"] == 4
    assert summary["blocked_count"] == 1
    assert summary["registry_only_count"] == 1


def test_review_id_is_deterministic():
    queue = ior.build_review_queue()
    for item in queue["items"]:
        expected = f"review:{item['source_id']}"
        assert item["review_id"] == expected


def test_approve_not_real_ingestion():
    queue = ior.build_review_queue()
    pending = queue["pending_operator_review"]
    assert len(pending) > 0
    item = pending[0]
    assert "approve_for_future_dry_run" in item["allowed_decisions"]
    assert item["approval_authorizes_real_ingestion"] is False


def test_count_consistency():
    queue = ior.build_review_queue()
    total = queue["total_records"]
    counts = (
        len(queue["pending_operator_review"])
        + len(queue["blocked"])
        + len(queue["registry_only"])
        + len(queue["not_reviewable"])
    )
    assert total == counts, f"Count mismatch: total={total}, sum={counts}"


def test_default_decisions():
    queue = ior.build_review_queue()
    for item in queue["items"]:
        if item["review_status"] == "pending_operator_review":
            assert item["default_decision"] == "request_more_context"
        elif item["review_status"] == "blocked":
            assert item["default_decision"] == "keep_blocked"
        elif item["review_status"] == "registry_only":
            assert item["default_decision"] == "no_action"


def test_no_network_imports_in_module():
    src = Path("brain/ingestion_operator_review.py").read_text(encoding="utf-8")
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
    src = Path("brain/ingestion_operator_review.py").read_text(encoding="utf-8")
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
