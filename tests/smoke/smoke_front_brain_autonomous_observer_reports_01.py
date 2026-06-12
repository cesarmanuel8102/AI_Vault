import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))

from brain_v9.reports.autonomous_observer_report import validate_observer_report, write_observer_report


def _valid_payload():
    return {
        "front": "FRONT-X",
        "objective": "test",
        "actions_taken": [],
        "files_changed": [],
        "tests_run": [],
        "evidence_paths": [],
        "gates_passed": [],
        "gates_failed": [],
        "memory_mutated": False,
        "faiss_mutated": False,
        "trading_touched": False,
        "secrets_exposed": False,
        "raw_cot_exposed": False,
        "runtime_used": "8091",
        "next_recommended_front": "FRONT-Y",
        "human_review_needed": False,
    }


def test_01_validate_observer_report_accepts_required_payload(tmp_path):
    assert validate_observer_report(_valid_payload()) == []
    out = write_observer_report(tmp_path / "report.json", _valid_payload())
    assert out["valid"] is True


def test_02_validate_observer_report_rejects_missing_fields():
    errors = validate_observer_report({"front": "x"})
    assert errors
    assert any(error.startswith("missing_fields") for error in errors)


def test_03_validate_observer_report_rejects_non_bool_safety():
    payload = _valid_payload()
    payload["memory_mutated"] = "false"
    assert "memory_mutated_must_be_bool" in validate_observer_report(payload)
