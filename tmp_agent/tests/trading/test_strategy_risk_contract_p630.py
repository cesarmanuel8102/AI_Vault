from __future__ import annotations

import pytest

import brain_v9.trading.strategy_engine as se


@pytest.mark.asyncio
async def test_execute_candidate_blocks_on_risk_contract_violation(monkeypatch):
    monkeypatch.setattr(
        se,
        "refresh_strategy_engine",
        lambda: {
            "ranking": {
                "ranked": [
                    {
                        "strategy_id": "po_breakout_v1",
                        "venue": "pocket_option",
                        "execution_ready": True,
                        "freeze_recommended": False,
                        "governance_state": "paper_active",
                        "context_governance_state": None,
                    }
                ]
            },
            "signals": {"items": []},
            "features": {"items": []},
            "archive": {"archived": []},
        },
    )
    monkeypatch.setattr(
        se,
        "_signal_maps",
        lambda payload: ({"po_breakout_v1": {"best_signal": {"symbol": "AUDNZD_otc", "timeframe": "1m", "setup_variant": "base"}}}, {}),
    )
    monkeypatch.setattr(
        se,
        "_normalize_strategy_specs",
        lambda: {
            "strategies": [
                {
                    "strategy_id": "po_breakout_v1",
                    "venue": "pocket_option",
                    "family": "breakout",
                    "preferred_symbol": "AUDNZD_otc",
                    "preferred_timeframe": "1m",
                    "preferred_setup_variant": "base",
                }
            ]
        },
    )
    monkeypatch.setattr(
        se,
        "enforce_risk_contract_for_execution",
        lambda source="strategy_execution": {
            "status": "critical",
            "execution_allowed": False,
            "hard_violations": ["max_total_exposure_exceeded"],
            "control_layer": {"mode": "FROZEN", "reason": "risk_contract_violation:max_total_exposure_exceeded"},
        },
    )

    called = {"execute": False}

    async def _should_not_run(*args, **kwargs):
        called["execute"] = True
        return {"success": True}

    monkeypatch.setattr(se, "_execute_strategy_trade", _should_not_run)

    result = await se.execute_candidate("po_breakout_v1")

    assert result["success"] is False
    assert result["error"] == "risk_contract_violation"
    assert result["risk_status"]["status"] == "critical"
    assert called["execute"] is False
