from __future__ import annotations

import json

import brain_v9.trading.post_trade_analysis as pta


def test_post_trade_analysis_detects_duplicate_burst(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)
    pta.LEDGER_PATH = state_dir / "signal_paper_execution_ledger.json"
    pta.EDGE_PATH = state_dir / "edge_validation_latest.json"
    pta.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    pta.OUTPUT_PATH = state_dir / "post_trade_analysis_latest.json"

    ledger = {
        "entries": [
            {
                "timestamp": "2026-03-27T10:00:00Z",
                "resolved_utc": "2026-03-27T10:01:00Z",
                "strategy_id": "po_test",
                "venue": "pocket_option",
                "symbol": "AUDNZD_otc",
                "direction": "put",
                "entry_price": 1.18001,
                "result": "win",
                "profit": 7.1,
                "resolved": True,
            },
            {
                "timestamp": "2026-03-27T10:00:01Z",
                "resolved_utc": "2026-03-27T10:01:01Z",
                "strategy_id": "po_test",
                "venue": "pocket_option",
                "symbol": "AUDNZD_otc",
                "direction": "put",
                "entry_price": 1.18001,
                "result": "loss",
                "profit": -10.0,
                "resolved": True,
            },
        ]
    }
    edge = {"summary": {"validated_count": 0, "probation_count": 1}}
    ranking = {"top_action": "run_probation_carefully"}

    (state_dir / "signal_paper_execution_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (state_dir / "edge_validation_latest.json").write_text(json.dumps(edge), encoding="utf-8")
    (state_dir / "strategy_ranking_v2_latest.json").write_text(json.dumps(ranking), encoding="utf-8")

    payload = pta.build_post_trade_analysis_snapshot(limit=10)
    assert payload["summary"]["duplicate_anomaly_count"] == 1
    assert payload["summary"]["next_focus"] == "audit_duplicate_execution"
    assert payload["anomalies"][0]["type"] == "duplicate_execution_burst"


def test_post_trade_analysis_summarizes_strategy_and_venue(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)
    pta.LEDGER_PATH = state_dir / "signal_paper_execution_ledger.json"
    pta.EDGE_PATH = state_dir / "edge_validation_latest.json"
    pta.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    pta.OUTPUT_PATH = state_dir / "post_trade_analysis_latest.json"

    ledger = {
        "entries": [
            {
                "timestamp": "2026-03-27T10:00:00Z",
                "resolved_utc": "2026-03-27T10:01:00Z",
                "strategy_id": "ibkr_test",
                "venue": "ibkr",
                "symbol": "SPY",
                "direction": "call",
                "entry_price": 620.0,
                "result": "win",
                "profit": 5.0,
                "resolved": True,
            },
            {
                "timestamp": "2026-03-27T10:02:00Z",
                "resolved_utc": "2026-03-27T10:03:00Z",
                "strategy_id": "ibkr_test",
                "venue": "ibkr",
                "symbol": "SPY",
                "direction": "call",
                "entry_price": 621.0,
                "result": "loss",
                "profit": -4.0,
                "resolved": True,
            },
        ]
    }
    (state_dir / "signal_paper_execution_ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    (state_dir / "edge_validation_latest.json").write_text(json.dumps({"summary": {"validated_count": 1, "probation_count": 0}}), encoding="utf-8")
    (state_dir / "strategy_ranking_v2_latest.json").write_text(json.dumps({"top_action": "hold"}), encoding="utf-8")

    payload = pta.build_post_trade_analysis_snapshot(limit=10)
    assert payload["summary"]["recent_resolved_trades"] == 2
    assert payload["summary"]["wins"] == 1
    assert payload["summary"]["losses"] == 1
    assert payload["by_strategy"][0]["strategy_id"] == "ibkr_test"
    assert payload["by_venue"][0]["venue"] == "ibkr"
