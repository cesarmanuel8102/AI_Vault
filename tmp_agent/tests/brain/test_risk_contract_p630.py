from __future__ import annotations

import json

import brain_v9.brain.risk_contract as rc


def test_build_risk_contract_status_healthy(monkeypatch, tmp_path):
    state_path = tmp_path / "tmp_agent" / "state"
    metrics_path = tmp_path / "60_METRICS"
    contract_path = tmp_path / "workspace" / "brainlab" / "brainlab" / "contracts"
    state_path.mkdir(parents=True, exist_ok=True)
    metrics_path.mkdir(parents=True, exist_ok=True)
    contract_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(rc, "STATE_PATH", state_path)
    monkeypatch.setattr(rc, "RISK_STATE_DIR", state_path / "risk")
    rc.RISK_STATE_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rc, "RISK_STATUS_PATH", rc.RISK_STATE_DIR / "risk_contract_status_latest.json")
    monkeypatch.setattr(rc, "LEDGER_PATH", state_path / "strategy_engine" / "signal_paper_execution_ledger.json")
    monkeypatch.setattr(rc, "CAPITAL_PATH", metrics_path / "capital_state.json")
    monkeypatch.setattr(rc, "BRIDGE_PATH", state_path / "rooms" / "bridge_latest.json")
    monkeypatch.setattr(rc, "MISSION_PATH", state_path / "financial_mission.json")
    monkeypatch.setattr(rc, "UTILITY_PATH", state_path / "utility_u_latest.json")
    monkeypatch.setattr(rc, "CONTRACT_PATH", contract_path / "financial_motor_contract_v1.json")
    monkeypatch.setattr(rc, "PAPER_ONLY", True)
    monkeypatch.setattr(rc, "get_control_layer_status_latest", lambda: {"mode": "ACTIVE", "reason": "ok"})

    (state_path / "strategy_engine").mkdir(parents=True, exist_ok=True)
    rc.LEDGER_PATH.write_text(json.dumps({"entries": [{"resolved": True, "profit": 5.0, "resolved_utc": "2026-03-27T20:00:00Z"}]}), encoding="utf-8")
    rc.CAPITAL_PATH.write_text(json.dumps({"starting_capital": 500, "current_cash": 425, "committed_cash": 75}), encoding="utf-8")
    rc.MISSION_PATH.write_text(json.dumps({"guardrails": {"require_validation_before_scaling": True}}), encoding="utf-8")
    rc.UTILITY_PATH.write_text(json.dumps({"u_score": -0.2, "verdict": "no_promote", "blockers": []}), encoding="utf-8")
    rc.CONTRACT_PATH.write_text(
        json.dumps(
            {
                "risk": {
                    "limits": {
                        "max_daily_loss_frac": 0.02,
                        "max_weekly_drawdown_frac": 0.06,
                        "max_total_exposure_frac": 0.70,
                        "kill_switch": False,
                    },
                    "kill_switch_policy": {"auto_on_violation": True},
                }
            }
        ),
        encoding="utf-8",
    )

    payload = rc.build_risk_contract_status()

    assert payload["status"] == "healthy"
    assert payload["execution_allowed"] is True
    assert payload["hard_violations"] == []


def test_enforce_risk_contract_freezes_on_hard_violation(monkeypatch, tmp_path):
    state_path = tmp_path / "tmp_agent" / "state"
    metrics_path = tmp_path / "60_METRICS"
    contract_path = tmp_path / "workspace" / "brainlab" / "brainlab" / "contracts"
    state_path.mkdir(parents=True, exist_ok=True)
    metrics_path.mkdir(parents=True, exist_ok=True)
    contract_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(rc, "STATE_PATH", state_path)
    monkeypatch.setattr(rc, "RISK_STATE_DIR", state_path / "risk")
    rc.RISK_STATE_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rc, "RISK_STATUS_PATH", rc.RISK_STATE_DIR / "risk_contract_status_latest.json")
    monkeypatch.setattr(rc, "LEDGER_PATH", state_path / "strategy_engine" / "signal_paper_execution_ledger.json")
    monkeypatch.setattr(rc, "CAPITAL_PATH", metrics_path / "capital_state.json")
    monkeypatch.setattr(rc, "BRIDGE_PATH", state_path / "rooms" / "bridge_latest.json")
    monkeypatch.setattr(rc, "MISSION_PATH", state_path / "financial_mission.json")
    monkeypatch.setattr(rc, "UTILITY_PATH", state_path / "utility_u_latest.json")
    monkeypatch.setattr(rc, "CONTRACT_PATH", contract_path / "financial_motor_contract_v1.json")
    monkeypatch.setattr(rc, "PAPER_ONLY", True)
    monkeypatch.setattr(rc, "get_control_layer_status_latest", lambda: {"mode": "ACTIVE", "reason": "ok"})

    (state_path / "strategy_engine").mkdir(parents=True, exist_ok=True)
    # Use a very large loss that exceeds even paper_only relaxed limits (15%)
    # and set resolved_utc to "now" so it falls within the calendar-day window.
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rc.LEDGER_PATH.write_text(
        json.dumps({"entries": [{"resolved": True, "profit": -200.0, "resolved_utc": now_iso}]}),
        encoding="utf-8",
    )
    rc.CAPITAL_PATH.write_text(json.dumps({"starting_capital": 500, "current_cash": 425, "committed_cash": 125}), encoding="utf-8")
    rc.MISSION_PATH.write_text(json.dumps({"guardrails": {"require_validation_before_scaling": True}}), encoding="utf-8")
    rc.UTILITY_PATH.write_text(json.dumps({"u_score": -0.5, "verdict": "no_promote", "blockers": []}), encoding="utf-8")
    rc.CONTRACT_PATH.write_text(
        json.dumps(
            {
                "risk": {
                    "limits": {
                        "max_daily_loss_frac": 0.02,
                        "max_weekly_drawdown_frac": 0.06,
                        "max_total_exposure_frac": 0.20,
                        "kill_switch": False,
                    },
                    "kill_switch_policy": {"auto_on_violation": True},
                }
            }
        ),
        encoding="utf-8",
    )

    freeze_calls = []

    def _freeze(reason: str, source: str = "user"):
        freeze_calls.append((reason, source))
        return {"mode": "FROZEN", "reason": reason}

    monkeypatch.setattr(rc, "freeze_control_layer", _freeze)

    payload = rc.enforce_risk_contract_for_execution(source="test")

    assert payload["execution_allowed"] is False
    # With paper_only relaxed limits (15% daily), a $200 loss on $550 capital
    # = 36.4% which exceeds even the relaxed limit.
    assert "max_daily_loss_exceeded" in payload["hard_violations"]
    assert freeze_calls
    assert payload["kill_switch_activated"] is True
