from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "tmp_agent" / "restart_brain_8091_load_patched_provider_route_01"


def _load_json(name: str) -> dict:
    path = EVIDENCE / name
    assert path.exists(), f"missing evidence file: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_required_evidence_files_exist() -> None:
    required = [
        "preflight.json",
        "process_8091_inventory.json",
        "start_clean_8091_report.json",
        "live_patched_route_validation.json",
        "final_safety_verify.json",
        "final_report.json",
    ]
    for name in required:
        assert (EVIDENCE / name).exists(), name


def test_completed_route_is_live_and_not_dry_run_or_admin_has_manual_command() -> None:
    report = _load_json("final_report.json")
    if report["status"] == "BRAIN_8091_PATCHED_PROVIDER_ROUTE_RELOAD_COMPLETED":
        validation = _load_json("live_patched_route_validation.json")
        first = validation["results"][0]
        assert first["route"] != "diagnostic_dry_run"
        assert first["route"] == "llm_grounded_provider_eval"
        assert first["dry_run"] is False
        assert first["provider_selected"]
        assert first["model_selected"]
    elif report["status"] == "BRAIN_8091_PATCHED_PROVIDER_ROUTE_RELOAD_NEEDS_ADMIN_ACTION":
        stop_report = _load_json("stop_old_8091_report.json")
        assert stop_report.get("manual_admin_command")
    else:
        raise AssertionError(f"unexpected final status: {report['status']}")


def test_semantic_and_faiss_baseline_unchanged() -> None:
    safety = _load_json("final_safety_verify.json")
    assert safety["semantic_lines_before"] == safety["semantic_lines_after"]
    assert safety["faiss_ids_before"] == safety["faiss_ids_after"]
    assert safety["faiss_ntotal_before"] == safety["faiss_ntotal_after"]
    assert safety["semantic_hash_before"] == safety["semantic_hash_after"]
    assert safety["faiss_index_hash_before"] == safety["faiss_index_hash_after"]
    assert safety["faiss_ids_hash_before"] == safety["faiss_ids_hash_after"]
    assert safety["canonical_semantic_mutated"] is False
    assert safety["faiss_index_mutated"] is False
    assert safety["faiss_ids_mutated"] is False


def test_scope_and_safety_flags() -> None:
    safety = _load_json("final_safety_verify.json")
    report = _load_json("final_report.json")
    assert safety["trading_touched"] is False
    assert safety["b8_touched"] is False
    assert safety["strategies_touched"] is False
    assert safety["secrets_exposed"] is False
    assert safety["raw_cot_exposed"] is False
    assert report["safety"]["trading_touched"] is False
    assert report["safety"]["b8_touched"] is False
    assert report["safety"]["secrets_exposed"] is False
    assert report["safety"]["raw_cot_exposed"] is False


def test_roadmap_json_valid_and_ledger_exists() -> None:
    json.loads((ROOT / "ROADMAP_STATUS.json").read_text(encoding="utf-8"))
    ledger = ROOT / "docs" / "MIGRATION_CONTROL_LEDGER.md"
    assert ledger.exists()
    assert "RESTART-BRAIN-8091-LOAD-PATCHED-PROVIDER-ROUTE-01" in ledger.read_text(encoding="utf-8")
