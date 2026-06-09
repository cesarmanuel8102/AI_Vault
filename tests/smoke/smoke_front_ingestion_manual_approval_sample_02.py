"""Smoke test for FRONT-INGESTION-MANUAL-APPROVAL-SAMPLE-02.

Validates:
1. ingestion_manual_approval_batch_sample module loads and is pure Python.
2. Default batch sample has mixed decisions across all 6 sources.
3. Safety flags are all False.
4. Expected counts match contract.
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

import brain.ingestion_manual_approval_batch_sample as imb
import brain.ingestion_approval_decision_dry_run as iad
import brain.ingestion_operator_review as ior
import brain.ingestion_reviewed_dry_run_execution as irde


def test_modules_import_cleanly():
    assert callable(imb.build_manual_batch_id)
    assert callable(imb.build_default_manual_decision_plan)
    assert callable(imb.find_review_item_by_source_id)
    assert callable(imb.apply_manual_decision_plan)
    assert callable(imb.run_manual_approval_batch_sample)
    assert callable(imb.validate_manual_approval_batch_sample)
    assert callable(imb.summarize_manual_approval_batch_sample)


def test_existing_pipeline_modules_import():
    assert callable(ior.build_review_queue)
    assert callable(iad.apply_decision_to_item)
    assert callable(irde.run_reviewed_dry_run_execution)


def test_default_batch_sample_runs():
    result = imb.run_manual_approval_batch_sample()
    assert result["total_records"] == 6
    assert "decision_result" in result
    assert "execution_result" in result
    assert result["batch_id"] == "batch:manual:sample_operator"


def test_batch_id_is_deterministic():
    batch_id = imb.build_manual_batch_id("sample_operator")
    assert batch_id == "batch:manual:sample_operator"


def test_default_decision_plan_has_six_entries():
    plan = imb.build_default_manual_decision_plan()
    assert len(plan) == 6
    source_ids = [p["source_id"] for p in plan]
    expected = [
        "local_file_dry_run_only",
        "uploaded_document_operator_review",
        "connector_reference_operator_review",
        "web_reference_operator_review",
        "api_reference_blocked_until_credentials_policy",
        "manual_text_low_risk",
    ]
    assert sorted(source_ids) == sorted(expected)


def test_local_file_is_approved():
    result = imb.run_manual_approval_batch_sample()
    dec_result = result["decision_result"]
    accepted = dec_result["accepted_for_future_dry_run"]
    assert len(accepted) == 1
    assert accepted[0]["source_id"] == "local_file_dry_run_only"
    assert accepted[0]["decision_status"] == "accepted_for_future_dry_run"


def test_uploaded_document_is_rejected():
    result = imb.run_manual_approval_batch_sample()
    dec_result = result["decision_result"]
    rejected = dec_result["rejected"]
    assert len(rejected) == 1
    assert rejected[0]["source_id"] == "uploaded_document_operator_review"
    assert rejected[0]["decision_status"] == "rejected"


def test_connector_reference_requests_more_context():
    result = imb.run_manual_approval_batch_sample()
    dec_result = result["decision_result"]
    more = dec_result["more_context_required"]
    assert any(d["source_id"] == "connector_reference_operator_review" for d in more)


def test_web_reference_requests_more_context():
    result = imb.run_manual_approval_batch_sample()
    dec_result = result["decision_result"]
    more = dec_result["more_context_required"]
    assert any(d["source_id"] == "web_reference_operator_review" for d in more)


def test_api_reference_remains_kept_blocked():
    result = imb.run_manual_approval_batch_sample()
    dec_result = result["decision_result"]
    blocked = dec_result["kept_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["source_id"] == "api_reference_blocked_until_credentials_policy"
    assert blocked[0]["decision_status"] == "kept_blocked"


def test_manual_text_remains_no_action():
    result = imb.run_manual_approval_batch_sample()
    dec_result = result["decision_result"]
    no_action = dec_result["no_action"]
    assert len(no_action) == 1
    assert no_action[0]["source_id"] == "manual_text_low_risk"
    assert no_action[0]["decision_status"] == "no_action"


def test_reviewed_dry_run_planned_count_is_one():
    result = imb.run_manual_approval_batch_sample()
    exec_result = result["execution_result"]
    planned = exec_result["reviewed_dry_run_planned"]
    assert len(planned) == 1
    item = planned[0]
    assert item["source_id"] == "local_file_dry_run_only"
    assert item["execution_status"] == "reviewed_dry_run_planned"
    assert item["allowed_execution_mode"] == "future_controlled_dry_run_only"


def test_rejected_count_is_one():
    result = imb.run_manual_approval_batch_sample()
    exec_result = result["execution_result"]
    rejected = exec_result["rejected"]
    assert len(rejected) == 1
    assert rejected[0]["source_id"] == "uploaded_document_operator_review"


def test_more_context_required_count_is_two():
    result = imb.run_manual_approval_batch_sample()
    dec_result = result["decision_result"]
    more = dec_result["more_context_required"]
    assert len(more) == 2


def test_kept_blocked_count_is_one():
    result = imb.run_manual_approval_batch_sample()
    exec_result = result["execution_result"]
    blocked = exec_result["blocked"]
    assert len(blocked) == 1
    assert blocked[0]["source_id"] == "api_reference_blocked_until_credentials_policy"


def test_no_action_count_is_one():
    result = imb.run_manual_approval_batch_sample()
    exec_result = result["execution_result"]
    no_action = exec_result["no_action"]
    assert len(no_action) == 1
    assert no_action[0]["source_id"] == "manual_text_low_risk"


def test_skipped_no_approval_count_is_two():
    result = imb.run_manual_approval_batch_sample()
    exec_result = result["execution_result"]
    skipped = exec_result["reviewed_dry_run_skipped_no_approval"]
    assert len(skipped) == 2


def test_approval_authorizes_real_ingestion_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["decision_result"]["decisions"]:
        assert item["approval_authorizes_real_ingestion"] is False


def test_can_write_semantic_memory_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["decision_result"]["decisions"]:
        assert item["can_write_semantic_memory"] is False


def test_can_promote_faiss_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["decision_result"]["decisions"]:
        assert item["can_promote_faiss"] is False


def test_content_read_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["content_read"] is False


def test_memory_write_executed_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["memory_write_executed"] is False


def test_faiss_write_executed_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["faiss_write_executed"] is False


def test_network_called_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["network_called"] is False


def test_connector_called_false():
    result = imb.run_manual_approval_batch_sample()
    for item in result["execution_result"]["execution_items"]:
        assert item["safety_flags"]["connector_called"] is False


def test_blocked_source_cannot_be_approved():
    queue = ior.build_review_queue()
    item = imb.find_review_item_by_source_id(
        queue, "api_reference_blocked_until_credentials_policy"
    )
    assert item["review_status"] == "blocked"
    assert "approve_for_future_dry_run" not in item["allowed_decisions"]


def test_unknown_source_returns_source_not_found():
    queue = ior.build_review_queue()
    result = imb.find_review_item_by_source_id(queue, "nonexistent_source")
    assert result is None


def test_invalid_decision_returns_denied():
    queue = ior.build_review_queue()
    item = imb.find_review_item_by_source_id(queue, "local_file_dry_run_only")
    decision = iad.apply_decision_to_item(item, requested_decision="invalid_decision")
    assert decision["decision_status"] == "denied_invalid_decision"


def test_validate_returns_ok():
    result = imb.run_manual_approval_batch_sample()
    validation = imb.validate_manual_approval_batch_sample(result)
    assert validation["ok"] is True, f"Errors: {validation['errors']}"


def test_summarize_returns_expected_counts():
    result = imb.run_manual_approval_batch_sample()
    summary = imb.summarize_manual_approval_batch_sample(result)
    assert summary["total_records"] == 6
    assert summary["approved_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["more_context_required_count"] == 2
    assert summary["kept_blocked_count"] == 1
    assert summary["no_action_count"] == 1
    assert summary["reviewed_dry_run_planned_count"] == 1
    assert summary["reviewed_dry_run_skipped_no_approval_count"] == 2
    assert summary["blocked_count"] == 1
    assert summary["invalid_count"] == 0


def test_count_consistency():
    result = imb.run_manual_approval_batch_sample()
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
    src = Path("brain/ingestion_manual_approval_batch_sample.py").read_text(
        encoding="utf-8"
    )
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
    src = Path("brain/ingestion_manual_approval_batch_sample.py").read_text(
        encoding="utf-8"
    )
    assert "open(" not in src
    assert ".read_text(" not in src
    assert ".write_text(" not in src


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
