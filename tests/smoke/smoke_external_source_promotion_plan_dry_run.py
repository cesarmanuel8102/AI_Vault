"""Smoke tests for external source promotion plan dry-run."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import brain.external_sources.promotion_plan_dry_run as plan_module
from brain.external_sources.promotion_plan_dry_run import (
    build_promotion_plan,
    build_promotion_plan_item,
    run_promotion_plan_dry_run,
    summarize_promotion_plan,
)


def queue_item(**overrides):
    data = {
        "queue_item_id": "queue_1",
        "candidate_id": "candidate_1",
        "provider": "github",
        "source_id": "source_1",
        "operator_status": "pending_operator_review",
        "safety_flags": {
            "promotion_allowed": False,
            "memory_write_allowed": False,
            "faiss_write_allowed": False,
            "real_write_allowed": False,
        },
    }
    data.update(overrides)
    return data


def fake_queue_runner(output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    queue = [
        queue_item(queue_item_id="queue_1", candidate_id="candidate_1", provider="github"),
        queue_item(queue_item_id="queue_2", candidate_id="candidate_2", provider="sec"),
        queue_item(queue_item_id="queue_3", candidate_id="candidate_3", provider="docs", operator_status="rejected"),
    ]
    (out / "operator_review_queue.json").write_text(json.dumps(queue), encoding="utf-8")
    return {
        "ok": True,
        "queue_items": 3,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
    }


def test_import_module():
    assert plan_module is not None


def test_build_promotion_plan_item_exists():
    assert callable(build_promotion_plan_item)


def test_run_promotion_plan_dry_run_exists():
    assert callable(run_promotion_plan_dry_run)


def test_valid_queue_item_creates_promotion_plan_item():
    item = build_promotion_plan_item(queue_item())
    assert item["candidate_id"] == "candidate_1"
    assert item["promotion_status"] == "planned_dry_run_only"


def test_missing_or_non_pending_queue_item_rejected():
    try:
        build_promotion_plan_item(queue_item(operator_status="approved"))
    except ValueError as exc:
        assert "pending_operator_review" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_non_pending_queue_item_excluded():
    plan = build_promotion_plan([queue_item(), queue_item(operator_status="rejected")])
    assert len(plan) == 1


def test_memory_write_planned_false():
    item = build_promotion_plan_item(queue_item())
    assert item["write_plan"]["memory_write_planned"] is False


def test_faiss_write_planned_false():
    item = build_promotion_plan_item(queue_item())
    assert item["write_plan"]["faiss_write_planned"] is False


def test_real_write_planned_false():
    item = build_promotion_plan_item(queue_item())
    assert item["write_plan"]["real_write_planned"] is False


def test_runtime_integration_planned_false():
    item = build_promotion_plan_item(queue_item())
    assert item["write_plan"]["runtime_integration_planned"] is False


def test_promotion_status_planned_dry_run_only():
    item = build_promotion_plan_item(queue_item())
    assert item["promotion_status"] == "planned_dry_run_only"


def test_target_layer_curated_external_knowledge():
    item = build_promotion_plan_item(queue_item())
    assert item["target_layer"] == "curated_external_knowledge"


def test_forbidden_now_includes_write_memory():
    item = build_promotion_plan_item(queue_item())
    assert "write_memory" in item["forbidden_now"]


def test_forbidden_now_includes_write_faiss():
    item = build_promotion_plan_item(queue_item())
    assert "write_faiss" in item["forbidden_now"]


def test_forbidden_now_includes_trading_use():
    item = build_promotion_plan_item(queue_item())
    assert "trading_use" in item["forbidden_now"]


def test_forbidden_now_includes_auto_promote():
    item = build_promotion_plan_item(queue_item())
    assert "auto_promote" in item["forbidden_now"]


def test_summarize_promotion_plan_counts_items():
    summary = summarize_promotion_plan([build_promotion_plan_item(queue_item())])
    assert summary["promotion_plan_items"] == 1


def test_runner_writes_json(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        run_promotion_plan_dry_run(td)
        assert Path(td, "promotion_plan.json").exists()


def test_runner_writes_jsonl(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        run_promotion_plan_dry_run(td)
        assert Path(td, "promotion_plan.jsonl").exists()


def test_runner_writes_summary(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        run_promotion_plan_dry_run(td)
        assert Path(td, "promotion_plan_summary.json").exists()


def test_runner_writes_md(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        run_promotion_plan_dry_run(td)
        assert Path(td, "promotion_plan.md").exists()


def test_runner_returns_two_plan_items(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_promotion_plan_dry_run(td)
        assert result["promotion_plan_items"] == 2


def test_no_token_leak(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        run_promotion_plan_dry_run(td)
        combined = "\n".join(p.read_text(encoding="utf-8") for p in Path(td).glob("promotion_plan*") if p.is_file())
        assert "github_pat_" not in combined
        assert "ghp_" not in combined
        assert "Authorization:" not in combined
        assert "FRED_API_KEY" not in combined


def test_no_memory_semantic_write(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    before = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    with tempfile.TemporaryDirectory() as td:
        result = run_promotion_plan_dry_run(td)
    after = set(Path("memory/semantic").glob("*")) if Path("memory/semantic").exists() else set()
    assert before == after
    assert result["memory_write_performed"] is False


def test_no_faiss_write(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_promotion_plan_dry_run(td)
    assert result["faiss_write_performed"] is False


def test_no_real_write(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_promotion_plan_dry_run(td)
    assert result["real_write_performed"] is False


def test_no_promotion(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_promotion_plan_dry_run(td)
    assert result["promotion_performed"] is False


def test_no_trading_or_b8_touch(monkeypatch):
    monkeypatch.setattr(plan_module, "run_operator_review_queue_dry_run", fake_queue_runner)
    with tempfile.TemporaryDirectory() as td:
        result = run_promotion_plan_dry_run(td)
    assert result["trading_used"] is False
    assert result["b8_touched"] is False
