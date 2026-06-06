"""Smoke tests for external source operator review queue - dry-run only."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.operator_review_queue_dry_run as queue_module
from brain.external_sources.operator_review_queue_dry_run import (
    build_operator_queue_item,
    build_operator_review_queue,
    run_operator_review_queue_dry_run,
    summarize_operator_review_queue,
)


def approved_review(**overrides):
    data = {
        "candidate_id": "candidate_1",
        "provider": "github",
        "source_id": "source_1",
        "decision": "approved_for_operator_review",
        "review_score": 0.95,
        "reasons": ["quality_gate: scores meet operator review threshold"],
        "blocking_issues": [],
        "reviewed_at": "2026-06-06T00:00:00+00:00",
    }
    data.update(overrides)
    return data


def rejected_review(decision="rejected_low_quality"):
    item = approved_review()
    item["decision"] = decision
    return item


def fake_gate(output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = [
        approved_review(candidate_id="candidate_1", provider="github", source_id="repo"),
        approved_review(candidate_id="candidate_2", provider="sec", source_id="sec_submissions"),
        rejected_review("rejected_low_quality"),
        rejected_review("needs_more_evidence"),
    ]
    (out / "review_results.json").write_text(json.dumps(results), encoding="utf-8")
    return {
        "ok": True,
        "candidates_reviewed": len(results),
        "approved_for_operator_review": 2,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
    }


def test_import_module():
    assert queue_module is not None


def test_build_operator_queue_item_exists():
    assert callable(build_operator_queue_item)


def test_run_operator_review_queue_dry_run_exists():
    assert callable(run_operator_review_queue_dry_run)


def test_approved_review_result_becomes_queue_item():
    item = build_operator_queue_item(approved_review())
    assert item["decision"] == "approved_for_operator_review"
    assert item["candidate_id"] == "candidate_1"


def test_rejected_review_result_is_excluded():
    queue = build_operator_review_queue([approved_review(), rejected_review()])
    assert len(queue) == 1


def test_needs_more_evidence_result_is_excluded():
    queue = build_operator_review_queue([approved_review(), rejected_review("needs_more_evidence")])
    assert len(queue) == 1


def test_queue_item_has_operator_status_pending_operator_review():
    item = build_operator_queue_item(approved_review())
    assert item["operator_status"] == "pending_operator_review"


def test_queue_item_has_recommended_operator_action():
    item = build_operator_queue_item(approved_review())
    assert item["recommended_operator_action"] == "review_evidence_and_decide_promotion_plan"


def test_queue_item_has_allowed_actions():
    item = build_operator_queue_item(approved_review())
    assert "approve_for_promotion_dry_run" in item["allowed_actions"]


def test_queue_item_has_forbidden_actions():
    item = build_operator_queue_item(approved_review())
    assert "write_memory" in item["forbidden_actions"]
    assert "auto_promote" in item["forbidden_actions"]


def test_promotion_allowed_is_false():
    item = build_operator_queue_item(approved_review())
    assert item["safety_flags"]["promotion_allowed"] is False


def test_memory_write_allowed_is_false():
    item = build_operator_queue_item(approved_review())
    assert item["safety_flags"]["memory_write_allowed"] is False


def test_faiss_write_allowed_is_false():
    item = build_operator_queue_item(approved_review())
    assert item["safety_flags"]["faiss_write_allowed"] is False


def test_real_write_allowed_is_false():
    item = build_operator_queue_item(approved_review())
    assert item["safety_flags"]["real_write_allowed"] is False


def test_summarize_operator_review_queue_counts_items():
    summary = summarize_operator_review_queue([build_operator_queue_item(approved_review())])
    assert summary["queue_items"] == 1
    assert summary["ok"] is True


def test_run_writes_operator_review_queue_json(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        run_operator_review_queue_dry_run(td)
        assert Path(td, "operator_review_queue.json").exists()


def test_run_writes_operator_review_queue_jsonl(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        run_operator_review_queue_dry_run(td)
        assert Path(td, "operator_review_queue.jsonl").exists()


def test_run_writes_operator_review_queue_summary_json(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        run_operator_review_queue_dry_run(td)
        assert Path(td, "operator_review_queue_summary.json").exists()


def test_run_writes_operator_review_queue_md(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        run_operator_review_queue_dry_run(td)
        assert Path(td, "operator_review_queue.md").exists()


def test_run_summary_reports_excluded_count(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        result = run_operator_review_queue_dry_run(td)
        assert result["queue_items"] == 2
        assert result["approved_candidates_seen"] == 2
        assert result["rejected_or_deferred_excluded"] == 2


def test_no_token_appears_in_outputs(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        run_operator_review_queue_dry_run(td)
        combined = "\n".join(p.read_text(encoding="utf-8") for p in Path(td).glob("operator_review_queue*") if p.is_file())
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "FRED_API_KEY" not in combined


def test_no_memory_semantic_write(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_operator_review_queue_dry_run(td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_write(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        result = run_operator_review_queue_dry_run(td)
    assert result["faiss_write_performed"] is False


def test_no_real_write(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        result = run_operator_review_queue_dry_run(td)
    assert result["real_write_performed"] is False


def test_no_promotion(monkeypatch):
    monkeypatch.setattr(queue_module, "run_candidate_review_gate_dry_run", fake_gate)
    with tempfile.TemporaryDirectory() as td:
        result = run_operator_review_queue_dry_run(td)
    assert result["promotion_performed"] is False


def test_non_approved_queue_item_raises():
    try:
        build_operator_queue_item(rejected_review())
    except ValueError as exc:
        assert "approved_for_operator_review" in str(exc)
    else:
        raise AssertionError("expected ValueError")
