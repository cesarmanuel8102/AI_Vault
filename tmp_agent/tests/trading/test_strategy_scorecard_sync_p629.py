from __future__ import annotations

import json

import brain_v9.trading.strategy_scorecard as sc


def _strategy() -> dict:
    return {
        "strategy_id": "po_breakout_v1",
        "family": "breakout",
        "venue": "pocket_option",
        "status": "paper_candidate",
        "universe": ["AUDNZD_otc"],
        "timeframes": ["1m"],
        "setup_variants": ["momentum_break"],
        "linked_hypotheses": [],
        "success_criteria": {
            "min_resolved_trades": 20,
            "min_expectancy": 0.05,
            "min_win_rate": 0.55,
        },
    }


def test_ensure_scorecards_aggregate_reconciles_full_ledger_even_if_spec_changed(tmp_path, monkeypatch):
    engine_path = tmp_path / "tmp_agent" / "state" / "strategy_engine"
    engine_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "tmp_agent" / "state")
    monkeypatch.setattr(sc, "ENGINE_PATH", engine_path)
    monkeypatch.setattr(sc, "SCORECARDS_PATH", engine_path / "strategy_scorecards.json")

    ledger = {
        "entries": [
            {
                "timestamp": "2026-03-27T03:53:21Z",
                "resolved_utc": "2026-03-27T03:54:21Z",
                "strategy_id": "po_breakout_v1",
                "venue": "pocket_option",
                "symbol": "AUDNZD_otc",
                "timeframe": "1m",
                "setup_variant": "momentum_break",
                "direction": "call",
                "result": "loss",
                "profit": -10.0,
                "resolved": True,
            },
            {
                "timestamp": "2026-03-27T03:56:21Z",
                "resolved_utc": "2026-03-27T03:57:21Z",
                "strategy_id": "po_breakout_v1",
                "venue": "pocket_option",
                "symbol": "AUDNZD_otc",
                "timeframe": "1m",
                "setup_variant": "legacy_variant",
                "direction": "call",
                "result": "win",
                "profit": 8.5,
                "resolved": True,
            },
        ]
    }
    (engine_path / "signal_paper_execution_ledger.json").write_text(
        json.dumps(ledger),
        encoding="utf-8",
    )

    payload = sc.ensure_scorecards([_strategy()])

    aggregate = payload["scorecards"]["po_breakout_v1"]
    symbol = payload["symbol_scorecards"]["pocket_option::po_breakout_v1::AUDNZD_otc"]
    context = payload["context_scorecards"]["pocket_option::po_breakout_v1::AUDNZD_otc::1m::momentum_break"]

    assert aggregate["entries_taken"] == 2
    assert aggregate["entries_resolved"] == 2
    assert aggregate["wins"] == 1
    assert aggregate["losses"] == 1
    assert symbol["entries_taken"] == 1
    assert symbol["entries_resolved"] == 1
    assert context["entries_taken"] == 1
    assert context["entries_resolved"] == 1


def test_ensure_scorecards_aggregate_reconciles_symbol_drift_without_recreating_symbol_scope(tmp_path, monkeypatch):
    engine_path = tmp_path / "tmp_agent" / "state" / "strategy_engine"
    engine_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "tmp_agent" / "state")
    monkeypatch.setattr(sc, "ENGINE_PATH", engine_path)
    monkeypatch.setattr(sc, "SCORECARDS_PATH", engine_path / "strategy_scorecards.json")

    ledger = {
        "entries": [
            {
                "timestamp": "2026-03-27T03:53:21Z",
                "resolved_utc": "2026-03-27T03:54:21Z",
                "strategy_id": "po_breakout_v1",
                "venue": "pocket_option",
                "symbol": "AUDUSD_otc",
                "timeframe": "1m",
                "setup_variant": "momentum_break",
                "direction": "call",
                "result": "loss",
                "profit": -10.0,
                "resolved": True,
            }
        ]
    }
    (engine_path / "signal_paper_execution_ledger.json").write_text(
        json.dumps(ledger),
        encoding="utf-8",
    )

    payload = sc.ensure_scorecards([_strategy()])

    aggregate = payload["scorecards"]["po_breakout_v1"]
    assert aggregate["entries_taken"] == 1
    assert aggregate["entries_resolved"] == 1
    assert aggregate["losses"] == 1
    assert "pocket_option::po_breakout_v1::AUDUSD_otc" not in payload["symbol_scorecards"]


def test_ensure_scorecards_clears_stale_aggregate_when_strategy_has_no_ledger_entries(tmp_path, monkeypatch):
    engine_path = tmp_path / "tmp_agent" / "state" / "strategy_engine"
    engine_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sc, "STATE_PATH", tmp_path / "tmp_agent" / "state")
    monkeypatch.setattr(sc, "ENGINE_PATH", engine_path)
    monkeypatch.setattr(sc, "SCORECARDS_PATH", engine_path / "strategy_scorecards.json")

    stale_payload = {
        "schema_version": "strategy_scorecards_v3",
        "updated_utc": "2026-03-27T00:00:00Z",
        "scorecards": {
            "po_breakout_v1": {
                **sc._blank_scorecard(_strategy()),
                "entries_taken": 5,
                "entries_resolved": 5,
                "entries_open": 0,
                "wins": 2,
                "losses": 3,
                "net_pnl": -10.0,
                "governance_state": "paper_watch",
                "promotion_state": "paper_watch",
            }
        },
        "symbol_scorecards": {
            "pocket_option::po_breakout_v1::AUDNZD_otc": {
                **sc._blank_symbol_scorecard(_strategy(), "AUDNZD_otc"),
                "entries_taken": 5,
                "entries_resolved": 5,
                "wins": 2,
                "losses": 3,
            }
        },
        "context_scorecards": {},
    }
    (engine_path / "strategy_scorecards.json").write_text(json.dumps(stale_payload), encoding="utf-8")
    (engine_path / "signal_paper_execution_ledger.json").write_text(json.dumps({"entries": []}), encoding="utf-8")

    payload = sc.ensure_scorecards([_strategy()])
    aggregate = payload["scorecards"]["po_breakout_v1"]
    symbol = payload["symbol_scorecards"]["pocket_option::po_breakout_v1::AUDNZD_otc"]

    assert aggregate["entries_taken"] == 0
    assert aggregate["entries_resolved"] == 0
    assert symbol["entries_taken"] == 0
    assert symbol["entries_resolved"] == 0
