
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "tmp_agent" / "front_brain_dashboard_status_endpoint_rootcause_repair_01"
DASHBOARD_ROUTES = ROOT / "tmp_agent" / "brain_v9" / "dashboard" / "dashboard_routes.py"
ROADMAP = ROOT / "ROADMAP_STATUS.json"
LEDGER = ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


def test_dashboard_status_source_route_is_fixed():
    source = read_text(DASHBOARD_ROUTES)

    assert '@router.get("/status")' in source
    assert "write_status_snapshot" not in source
    assert "_scheduler_info(use_subprocess=False)" in source
    assert "cached_no_subprocess" in source


def test_scheduler_source_uses_no_window_subprocess():
    source = read_text(DASHBOARD_ROUTES)

    assert '@router.get("/scheduler")' in source
    assert "_scheduler_info(use_subprocess=True)" in source
    assert "startupinfo_no_window()" in source
    assert "CREATE_NO_WINDOW" in source


def test_live_validation_exists_and_matches_final_status():
    live = read_json(EVIDENCE_DIR / "live_endpoint_validation.json")
    final = read_json(EVIDENCE_DIR / "final_report.json")

    assert live["root_ok"] is True
    if final["status"] == "BRAIN_DASHBOARD_STATUS_ENDPOINT_ROOTCAUSE_REPAIR_COMPLETED":
        assert live["status_ok"] is True
    else:
        assert final["status"] == "BRAIN_DASHBOARD_STATUS_ENDPOINT_ROOTCAUSE_REPAIR_NEEDS_ADMIN_ACTION"
        assert final["process_8092"]["needs_admin_action"] is True


def test_no_window_and_reports_exist():
    no_window = read_json(EVIDENCE_DIR / "no_window_validation.json")

    assert no_window["status_path_uses_cached_scheduler"] is True
    assert no_window["status_route_no_write_status_snapshot"] is True
    assert no_window["scheduler_endpoint_uses_create_no_window"] is True
    assert (EVIDENCE_DIR / "final_report.json").exists()
    assert (EVIDENCE_DIR / "final_report.md").exists()
    assert (EVIDENCE_DIR / "cesar_review_report.md").exists()
    assert (EVIDENCE_DIR / "NEXT_PROMPT_RECOMMENDATION.md").exists()


def test_canonical_memory_and_faiss_unchanged():
    safety = read_json(EVIDENCE_DIR / "final_safety_verify.json")

    assert safety["semantic_memory_lines"] == 1715
    assert safety["faiss_ids"] == 1616
    assert safety["faiss_ntotal"] == 1616
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_mutated"] is False
    assert safety["env_touched"] is False
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False


def test_roadmap_valid_and_ledger_exists():
    assert isinstance(read_json(ROADMAP), dict)
    assert LEDGER.exists()
