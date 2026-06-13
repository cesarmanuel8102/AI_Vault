
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "tmp_agent" / "front_brain_dashboard_status_endpoint_rootcause_repair_01_retry_after_admin_stop"
ROADMAP = ROOT / "ROADMAP_STATUS.json"
LEDGER = ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_live_endpoint_validation_status_ok():
    validation = read_json(EVIDENCE_DIR / "live_endpoint_validation.json")

    assert validation["status_ok"] is True
    assert validation["status_http"] == 200
    assert validation["status_latency_ms"] < 5000
    assert validation["root_ok"] is True
    assert validation["activity_ok"] is True
    assert validation["scheduler_ok"] is True
    assert validation["safety_ok"] is True
    assert validation["promotion_queue_ok"] is True
    assert validation["chat_ok"] is True
    assert validation["no_raw_traceback"] is True
    assert validation["no_raw_cot"] is True


def test_no_window_validation_and_final_report_exist():
    no_window = read_json(EVIDENCE_DIR / "no_window_validation.json")
    final = read_json(EVIDENCE_DIR / "final_report.json")

    assert no_window["no_window_verified"] is True
    assert no_window["all_status_http_200"] is True
    assert no_window["all_scheduler_http_200"] is True
    assert final["status"] == "BRAIN_DASHBOARD_STATUS_ENDPOINT_ROOTCAUSE_REPAIR_COMPLETED"
    assert final["process_8092"]["restart_success"] is True
    assert final["dashboard"]["status_ok"] is True


def test_canonical_memory_faiss_and_scope_safety():
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
