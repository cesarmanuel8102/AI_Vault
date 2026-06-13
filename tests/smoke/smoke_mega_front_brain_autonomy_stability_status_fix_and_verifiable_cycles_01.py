import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "tmp_agent" / "mega_front_brain_autonomy_stability_status_fix_and_verifiable_cycles_01"
DASHBOARD_ROUTES = ROOT / "tmp_agent" / "brain_v9" / "dashboard" / "dashboard_routes.py"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


def test_status_route_is_nonblocking_and_read_mostly():
    source = read_text(DASHBOARD_ROUTES)

    assert '@router.get("/status")' in source
    assert "write_status_snapshot" not in source
    assert "_scheduler_info(use_subprocess=False)" in source
    assert "cached_no_subprocess" in source
    assert "safe_component" in source
    assert "status_latency_ms" in source


def test_scheduler_endpoint_uses_hidden_short_subprocess_only():
    source = read_text(DASHBOARD_ROUTES)

    assert '@router.get("/scheduler")' in source
    assert "_scheduler_info(use_subprocess=True)" in source
    assert "startupinfo_no_window()" in source
    assert "CREATE_NO_WINDOW" in source
    assert '"timeout": 3' in source


def test_source_fixed_but_live_old_process_blocked_cycles():
    source_validation = read_json(EVIDENCE_DIR / "status_source_validation.json")
    endpoint_validation = read_json(EVIDENCE_DIR / "dashboard_endpoint_validation.json")
    root_cause = read_json(EVIDENCE_DIR / "live_status_root_cause.json")

    assert source_validation["source_status_ok"] is True
    assert source_validation["has_required_keys"] is True
    assert endpoint_validation["status_endpoint_fixed_source"] is True
    assert endpoint_validation["status_endpoint_fixed_live"] is False
    assert root_cause["restart_blocked"] is True
    assert root_cause["cycles_run"] == 0


def test_final_report_marks_partial_not_completed():
    report = read_json(EVIDENCE_DIR / "final_report.json")

    assert report["status"] == "BRAIN_AUTONOMY_STABILITY_STATUS_FIX_AND_VERIFIABLE_CYCLES_PARTIAL"
    assert report["cleanup"]["dirty_journal_reviewed"] is True
    assert report["cleanup"]["dirty_journal_safe"] is True
    assert report["cleanup"]["journal_commit"] == "4459870"
    assert report["dashboard"]["status_endpoint_fixed_source"] is True
    assert report["dashboard"]["status_endpoint_fixed_live"] is False
    assert report["autonomy"]["cycles_completed"] == 0
    assert report["autonomy"]["batches_completed"] == 0


def test_safety_baseline_unchanged():
    safety = read_json(EVIDENCE_DIR / "final_safety_verify.json")

    assert safety["semantic_memory_lines"] == 1715
    assert safety["faiss_ids"] == 1616
    assert safety["faiss_ntotal"] == 1616
    assert safety["semantic_memory_hash_unchanged"] is True
    assert safety["faiss_index_hash_unchanged"] is True
    assert safety["faiss_ids_hash_unchanged"] is True
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False


def test_required_operator_reports_exist():
    assert (EVIDENCE_DIR / "final_report.md").exists()
    assert (EVIDENCE_DIR / "cesar_review_report.md").exists()
    assert (EVIDENCE_DIR / "NEXT_PROMPT_RECOMMENDATION.md").exists()
    assert (EVIDENCE_DIR / "score_before.json").exists()
    assert (EVIDENCE_DIR / "score_after.json").exists()
