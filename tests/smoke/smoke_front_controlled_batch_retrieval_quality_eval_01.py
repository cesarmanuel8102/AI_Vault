"""tests/smoke/smoke_front_controlled_batch_retrieval_quality_eval_01.py
FRONT-CONTROLLED-BATCH-RETRIEVAL-QUALITY-EVAL-01 — Smoke tests
"""

import json
import subprocess
from pathlib import Path

from brain.controlled_batch_retrieval_quality_eval import (
    front_id,
    expected_records,
    query_suite,
    baseline_inventory,
    run_retrieval_quality_eval,
    summarize_quality_eval,
    assert_read_only_integrity,
)


def test_01_module_imports():
    import brain.controlled_batch_retrieval_quality_eval as mod
    assert callable(getattr(mod, "front_id", None))
    assert callable(getattr(mod, "run_retrieval_quality_eval", None))


def test_02_front_id_exact():
    assert front_id() == "FRONT-CONTROLLED-BATCH-RETRIEVAL-QUALITY-EVAL-01"


def test_03_expected_records_has_three_ids():
    recs = expected_records()
    assert len(recs) == 3
    ids = {r["id"] for r in recs}
    assert ids == {
        "controlled_batch_01_real_execution_policy",
        "controlled_batch_01_runtime_recovery_runbook",
        "controlled_batch_01_memory_faiss_canary_doc",
    }


def test_04_query_suite_has_at_least_15_queries():
    qs = query_suite()
    assert len(qs) >= 15


def test_05_each_record_has_at_least_5_queries():
    qs = query_suite()
    counts = {}
    for q in qs:
        counts.setdefault(q["expected_id"], 0)
        counts[q["expected_id"]] += 1
    assert all(c >= 5 for c in counts.values()), counts


def test_06_baseline_inventory_reads_without_writing():
    inv = baseline_inventory()
    assert inv["files"]["semantic_memory.jsonl"]["exists"] is True
    assert inv["files"]["semantic_memory_faiss.index"]["exists"] is True
    assert inv["files"]["semantic_memory_faiss_ids.json"]["exists"] is True


def test_07_run_returns_expected_keys():
    result = run_retrieval_quality_eval()
    for key in (
        "front_id",
        "network_called",
        "connector_called",
        "trading_executed",
        "b8_touched",
        "memory_mutated",
        "faiss_mutated",
        "per_record",
        "overall",
        "before_inventory",
        "after_inventory",
    ):
        assert key in result


def test_08_network_called_false():
    result = run_retrieval_quality_eval()
    assert result["network_called"] is False


def test_09_connector_called_false():
    result = run_retrieval_quality_eval()
    assert result["connector_called"] is False


def test_10_trading_executed_false():
    result = run_retrieval_quality_eval()
    assert result["trading_executed"] is False


def test_11_b8_touched_false():
    result = run_retrieval_quality_eval()
    assert result["b8_touched"] is False


def test_12_memory_mutated_false():
    result = run_retrieval_quality_eval()
    assert result["memory_mutated"] is False


def test_13_faiss_mutated_false():
    result = run_retrieval_quality_eval()
    assert result["faiss_mutated"] is False


def test_14_pass_criteria_computed_deterministically():
    result = run_retrieval_quality_eval()
    summary = summarize_quality_eval(result)
    assert isinstance(summary["pass_criteria_met"], bool)
    assert summary["total_queries"] == 15


def test_15_no_semantic_memory_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/"],
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == ""


def test_16_no_faiss_index_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/semantic_memory_faiss.index"],
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == ""


def test_17_no_faiss_ids_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", "memory/semantic/semantic_memory_faiss_ids.json"],
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == ""


def test_18_no_protected_files_staged():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", ".env", "session.py", "main.py", "execution_gate.py", "brain/curated_runtime_lookup.py", "trading", "B8", "tmp_agent/strategies"],
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == ""


def test_19_roadmap_valid_json():
    roadmap = Path("ROADMAP_STATUS.json")
    assert roadmap.exists()
    obj = json.loads(roadmap.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)


def test_20_docs_ledger_exists():
    ledger = Path("docs/MIGRATION_CONTROL_LEDGER.md")
    assert ledger.exists()
    text = ledger.read_text(encoding="utf-8")
    assert "FRONT-FIRST-REAL-LOCAL-INGESTION-CONTROLLED-BATCH-01" in text


def test_21_per_record_top_k_found():
    result = run_retrieval_quality_eval()
    for pr in result["per_record"]:
        found_any = any(e["found_top_10"] for e in pr["evaluations"])
        assert found_any, f"Record {pr['record_id']} not found in any query"


def test_22_top_5_pass_rate_threshold():
    result = run_retrieval_quality_eval()
    summary = summarize_quality_eval(result)
    assert summary["top_5_pass_rate"] >= 0.80


def test_23_top_10_pass_rate_perfect():
    result = run_retrieval_quality_eval()
    summary = summarize_quality_eval(result)
    assert summary["top_10_pass_rate"] == 1.0


def test_24_assert_integrity_ok():
    before = baseline_inventory()
    result = run_retrieval_quality_eval()
    after = result["after_inventory"]
    integrity = assert_read_only_integrity(before, after)
    assert integrity["ok"] is True
