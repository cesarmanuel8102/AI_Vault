from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

import brain_v9.trading.post_trade_hypotheses as pth


def test_post_trade_hypothesis_base_flags_missing_validated_edge(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)
    pth.POST_TRADE_PATH = state_dir / "post_trade_analysis_latest.json"
    pth.EDGE_PATH = state_dir / "edge_validation_latest.json"
    pth.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    pth.OUTPUT_PATH = state_dir / "post_trade_hypotheses_latest.json"

    post_trade = {
        "summary": {
            "recent_resolved_trades": 10,
            "wins": 2,
            "losses": 8,
            "win_rate": 0.2,
            "net_profit": -55.0,
            "duplicate_anomaly_count": 1,
            "next_focus": "audit_duplicate_execution",
        },
        "by_strategy": [{"strategy_id": "po_test", "resolved": 10, "net_profit": -55.0}],
        "by_venue": [{"venue": "pocket_option", "resolved": 10, "net_profit": -55.0}],
        "by_symbol": [{"symbol": "AUDNZD_otc", "resolved": 10, "net_profit": -55.0}],
        "anomalies": [{"strategy_id": "po_test", "type": "duplicate_execution_burst"}],
    }
    edge = {"summary": {"validated_count": 0, "probation_count": 1, "best_probation": {"strategy_id": "po_test"}}}
    ranking = {"top_action": "run_probation_carefully", "probation_candidate": {"strategy_id": "po_test"}}

    pth.POST_TRADE_PATH.write_text(json.dumps(post_trade), encoding="utf-8")
    pth.EDGE_PATH.write_text(json.dumps(edge), encoding="utf-8")
    pth.RANKING_PATH.write_text(json.dumps(ranking), encoding="utf-8")

    payload = pth.build_post_trade_hypothesis_base()
    assert payload["summary"]["finding_count"] >= 2
    assert payload["summary"]["hypothesis_count"] >= 2
    assert payload["summary"]["next_focus"] == "audit_duplicate_execution"
    assert any(item["type"] == "edge_gap" for item in payload["findings"])


@pytest.mark.asyncio
async def test_post_trade_hypothesis_snapshot_uses_llm_when_available(isolated_base_path):
    state_dir = isolated_base_path / "tmp_agent" / "state" / "strategy_engine"
    state_dir.mkdir(parents=True, exist_ok=True)
    pth.POST_TRADE_PATH = state_dir / "post_trade_analysis_latest.json"
    pth.EDGE_PATH = state_dir / "edge_validation_latest.json"
    pth.RANKING_PATH = state_dir / "strategy_ranking_v2_latest.json"
    pth.OUTPUT_PATH = state_dir / "post_trade_hypotheses_latest.json"

    pth.POST_TRADE_PATH.write_text(json.dumps({"summary": {"next_focus": "continue_probation"}, "by_strategy": [], "by_venue": [], "by_symbol": [], "anomalies": []}), encoding="utf-8")
    pth.EDGE_PATH.write_text(json.dumps({"summary": {"validated_count": 0, "probation_count": 1}}), encoding="utf-8")
    pth.RANKING_PATH.write_text(json.dumps({"top_action": "run_probation_carefully"}), encoding="utf-8")

    with patch("brain_v9.trading.post_trade_hypotheses.LLMManager.query", new=AsyncMock(return_value={
        "success": True,
        "content": "1. Estado real\n2. Riesgo principal\n3. Siguiente experimento",
        "model_used": "llama3.1:8b",
    })):
        payload = await pth.build_post_trade_hypothesis_snapshot(include_llm=True)

    assert payload["llm_summary"]["available"] is True
    assert "Estado real" in payload["llm_summary"]["text"]
    assert payload["base_only"] is False
