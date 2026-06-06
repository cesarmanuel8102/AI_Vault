"""Smoke tests for external source learning results report dry-run."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.learning_results_report_dry_run as report_module
from brain.external_sources.learning_results_report_dry_run import (
    build_learning_result_summary,
    build_operator_visible_report,
    run_learning_results_report_dry_run,
)


def fake_promotion_runner(output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan = [
        {
            "promotion_plan_item_id": "plan_1",
            "queue_item_id": "queue_1",
            "candidate_id": "candidate_1",
            "provider": "github",
            "source_id": "repo",
            "promotion_status": "planned_dry_run_only",
        }
    ]
    queue_dir = out / "run_operator_queue"
    ingestion_dir = queue_dir / "run_review_gate" / "run_ingestion"
    review_dir = queue_dir / "run_review_gate"
    ingestion_dir.mkdir(parents=True, exist_ok=True)
    (out / "promotion_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (queue_dir / "operator_review_queue.json").write_text(json.dumps([{"candidate_id": "candidate_1"}]), encoding="utf-8")
    (review_dir / "review_summary.json").write_text(json.dumps({"approved_for_operator_review": 1}), encoding="utf-8")
    (ingestion_dir / "ingestion_summary.json").write_text(
        json.dumps({"normalized_records_count": 1, "curated_candidates_count": 1}),
        encoding="utf-8",
    )
    (ingestion_dir / "curated_candidates.json").write_text(
        json.dumps(
            [
                {
                    "candidate_id": "candidate_1",
                    "claim": "External source retrieved from github: repository metadata",
                    "text": "Repository metadata excerpt",
                    "evidence_refs": ["repo"],
                }
            ]
        ),
        encoding="utf-8",
    )
    return {
        "ok": True,
        "promotion_plan_items": 1,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
    }


def test_import_module():
    assert report_module is not None


def test_run_learning_results_report_dry_run_exists():
    assert callable(run_learning_results_report_dry_run)


def test_build_learning_result_summary_exists():
    assert callable(build_learning_result_summary)


def test_build_operator_visible_report_exists():
    assert callable(build_operator_visible_report)


def test_files_written(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        assert Path(td, "learning_results_summary.json").exists()
        assert Path(td, "learning_results_report.md").exists()
        assert Path(td, "learning_results_cards.json").exists()
        assert Path(td, "learning_results_cards.jsonl").exists()


def test_cards_exist(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_learning_results_report_dry_run(td)
        assert result["learning_result_cards"] == 1


def test_card_status_ready_for_operator_review(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["status"] == "ready_for_operator_review"


def test_card_has_what_was_learned(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert "External source retrieved" in cards[0]["what_was_learned"]


def test_card_has_why_it_matters(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["why_it_matters"]


def test_card_has_provenance_available(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["evidence_status"] == "provenance_available"


def test_card_next_operator_action(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["next_operator_action"] == "review_promotion_plan"


def test_no_memory_write_flag_true(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["memory_write_allowed"] is False


def test_no_faiss_write_flag_true(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["faiss_write_allowed"] is False


def test_no_real_write_flag_true(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["real_write_allowed"] is False


def test_no_promotion_allowed_flag_true(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        cards = json.loads(Path(td, "learning_results_cards.json").read_text(encoding="utf-8"))
        assert cards[0]["promotion_allowed"] is False


def test_no_token_leak(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        combined = "\n".join(p.read_text(encoding="utf-8") for p in Path(td).glob("learning_results*") if p.is_file())
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "FRED_API_KEY" not in combined


def test_no_memory_semantic_write(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_learning_results_report_dry_run(td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_real_or_promotion(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_learning_results_report_dry_run(td)
    assert result["faiss_write_performed"] is False
    assert result["real_write_performed"] is False
    assert result["promotion_performed"] is False


def test_report_contains_visible_summaries(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        report = Path(td, "learning_results_report.md").read_text(encoding="utf-8")
        assert "What the operator can see now" in report
        assert "What learned means in this phase" in report


def test_no_runtime_chat_integration_yet(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_learning_results_report_dry_run(td)
    assert result["runtime_chat_integration"] is False


def test_no_trading_b8(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_learning_results_report_dry_run(td)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False


def test_operator_visible_report_mentions_next_step():
    summary = {
        "sources_seen": 1,
        "records_normalized": 1,
        "candidates_created": 1,
        "candidates_approved": 1,
        "queue_items": 1,
        "promotion_plan_items": 1,
        "learning_result_cards": 0,
        "cards": [],
    }
    report = build_operator_visible_report(summary)
    assert "RUNTIME-READONLY-EXTERNAL-KNOWLEDGE-RESULTS-ENDPOINT-DRY-RUN-01" in report


def test_summary_counts_pipeline_outputs(monkeypatch):
    monkeypatch.setattr(report_module, "run_promotion_plan_dry_run", fake_promotion_runner)
    with tempfile.TemporaryDirectory() as td:
        run_learning_results_report_dry_run(td)
        summary = json.loads(Path(td, "learning_results_summary.json").read_text(encoding="utf-8"))
        assert summary["sources_seen"] == 1
        assert summary["promotion_plan_items"] == 1
