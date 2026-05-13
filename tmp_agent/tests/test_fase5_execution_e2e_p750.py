"""
Brain V9 — Fase 5: Ejecución Paper y Verificación E2E

Tests for:
- execution_state field in ledger entries (P750)
- decision_context and gate_audit persistence in ledger
- IBKR vs PO execution_state differentiation
- _verify_execution_e2e() symbol/direction/balance verification
- persist_trade_execution_metadata() state advancement
- resolve_pending_paper_trades() final state transitions
- execute_signal_paper_trade() context/audit passthrough
"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import brain_v9.trading.paper_execution as pe


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _make_strategy(venue="pocket_option", strategy_id="test_strat_1"):
    return {
        "strategy_id": strategy_id,
        "venue": venue,
        "family": "test_family",
        "preferred_symbol": "EURUSD_otc",
    }


def _make_signal(symbol="EURUSD_otc", direction="call", execution_ready=True):
    return {
        "symbol": symbol,
        "direction": direction,
        "timeframe": "1m",
        "setup_variant": "breakout_1m",
        "asset_class": "otc_binary",
        "confidence": 0.75,
        "signal_score": 82.0,
        "execution_ready": execution_ready,
        "reasons": ["rsi_oversold", "bb_squeeze"],
        "blockers": [],
        "feature_key": "po:EURUSD_otc:1m",
    }


def _make_feature(price=1.0850, payout_pct=82.0):
    return {
        "last": price,
        "mid": price,
        "price_available": True,
        "payout_pct": payout_pct,
        "key": "po:EURUSD_otc:1m",
    }


def _make_lane(platform="pocket_option_paper"):
    return {"platform": platform, "ready": True}


def _make_decision_context():
    return {
        "observation": {
            "signal_reasons": ["rsi_oversold", "bb_squeeze"],
            "signal_blockers": [],
            "signal_score": 82.0,
            "confidence": 0.75,
        },
        "why_acted": {
            "governance_state": "active",
            "governance_lane": "promoted",
            "edge_state": "validated",
            "context_edge_state": "aligned",
            "rank_position": 1,
        },
        "expected_validation": {
            "linked_hypotheses": ["H001"],
            "success_criteria": {"min_sample": 8},
        },
        "measurement_plan": {
            "metric": "expectancy_and_win_rate_after_resolved",
            "min_sample_for_verdict": 8,
            "abort_criteria": "expectancy < -2.0 after min_sample",
        },
    }


def _make_gate_audit():
    return {
        "governance_state": "active",
        "context_governance_state": "active",
        "freeze_recommended": False,
        "archive_state": None,
        "risk_contract_execution_allowed": True,
        "risk_contract_kill_switch_active": False,
        "risk_daily_loss_ok": True,
        "risk_weekly_drawdown_ok": True,
        "execution_ready": True,
        "governance_lane": "promoted",
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. _build_deferred_entry — execution_state field
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildDeferredEntryExecutionState:
    """Test that _build_deferred_entry includes execution_state based on venue."""

    def test_po_venue_gets_signal_generated(self):
        entry = pe._build_deferred_entry(
            _make_strategy(venue="pocket_option"),
            _make_signal(),
            _make_feature(),
        )
        assert entry["execution_state"] == "signal_generated"

    def test_ibkr_venue_gets_internal_paper_shadow(self):
        entry = pe._build_deferred_entry(
            _make_strategy(venue="ibkr"),
            _make_signal(),
            _make_feature(),
        )
        assert entry["execution_state"] == "internal_paper_shadow"

    def test_unknown_venue_gets_signal_generated(self):
        entry = pe._build_deferred_entry(
            _make_strategy(venue="binance"),
            _make_signal(),
            _make_feature(),
        )
        assert entry["execution_state"] == "signal_generated"

    def test_empty_venue_gets_signal_generated(self):
        entry = pe._build_deferred_entry(
            _make_strategy(venue=""),
            _make_signal(),
            _make_feature(),
        )
        assert entry["execution_state"] == "signal_generated"

    def test_entry_has_standard_fields(self):
        entry = pe._build_deferred_entry(
            _make_strategy(),
            _make_signal(),
            _make_feature(),
        )
        assert entry["result"] == "pending_resolution"
        assert entry["resolved"] is False
        assert entry["paper_only"] is True
        assert entry["paper_shadow"] is True
        assert entry["resolution_mode"] == "deferred_forward_v1"
        assert "timestamp" in entry


# ═════════════════════════════════════════════════════════════════════════════
# 2. _build_deferred_entry — decision_context and gate_audit
# ═════════════════════════════════════════════════════════════════════════════

class TestBuildDeferredEntryContextAndAudit:
    """Test that decision_context and gate_audit are persisted in entry."""

    def test_decision_context_included(self):
        dc = _make_decision_context()
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
            decision_context=dc,
        )
        assert entry["decision_context"] == dc

    def test_gate_audit_included(self):
        ga = _make_gate_audit()
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
            gate_audit=ga,
        )
        assert entry["gate_audit"] == ga

    def test_both_context_and_audit(self):
        dc = _make_decision_context()
        ga = _make_gate_audit()
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
            decision_context=dc, gate_audit=ga,
        )
        assert "decision_context" in entry
        assert "gate_audit" in entry
        assert entry["decision_context"]["observation"]["confidence"] == 0.75
        assert entry["gate_audit"]["risk_contract_execution_allowed"] is True

    def test_none_context_not_in_entry(self):
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
            decision_context=None,
        )
        assert "decision_context" not in entry

    def test_none_audit_not_in_entry(self):
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
            gate_audit=None,
        )
        assert "gate_audit" not in entry


# ═════════════════════════════════════════════════════════════════════════════
# 3. _verify_execution_e2e
# ═════════════════════════════════════════════════════════════════════════════

class TestVerifyExecutionE2E:
    """Test E2E verification logic for browser evidence matching."""

    def test_verified_match_when_all_checks_pass(self):
        entry = {"symbol": "EURUSD_otc", "direction": "call"}
        trade = {
            "browser_order": {
                "raw": {
                    "command": {
                        "result": {
                            "evidence": {
                                "current_symbol": "EUR/USD (OTC)",
                                "button_text": "Higher / Call",
                                "journal_before": {"balance_demo": 10000.0},
                                "journal_after": {"trades_badge_delta": 1},
                            }
                        }
                    }
                }
            }
        }
        result = pe._verify_execution_e2e(entry, trade)
        assert result["status"] == "verified_match"
        assert "symbol" in result["checks_performed"]
        assert "direction" in result["checks_performed"]
        assert "balance_captured" in result["checks_performed"]
        assert "trade_registered_in_platform" in result["checks_performed"]
        assert result["mismatches"] == []
        assert "verified_utc" in result

    def test_mismatch_symbol(self):
        entry = {"symbol": "EURUSD_otc", "direction": "call"}
        trade = {
            "browser_order": {
                "raw": {
                    "command": {
                        "result": {
                            "evidence": {
                                "current_symbol": "GBP/JPY",
                                "button_text": "Higher / Call",
                            }
                        }
                    }
                }
            }
        }
        result = pe._verify_execution_e2e(entry, trade)
        assert result["status"] == "mismatch_detected"
        assert len(result["mismatches"]) >= 1
        assert result["mismatches"][0]["check"] == "symbol"

    def test_mismatch_direction(self):
        entry = {"symbol": "EURUSD_otc", "direction": "call"}
        trade = {
            "browser_order": {
                "raw": {
                    "command": {
                        "result": {
                            "evidence": {
                                "current_symbol": "EUR/USD (OTC)",
                                "button_text": "Lower / Put",
                            }
                        }
                    }
                }
            }
        }
        result = pe._verify_execution_e2e(entry, trade)
        assert result["status"] == "mismatch_detected"
        mismatch_checks = [m["check"] for m in result["mismatches"]]
        assert "direction" in mismatch_checks

    def test_unverified_when_no_evidence(self):
        entry = {"symbol": "EURUSD_otc", "direction": "call"}
        trade = {}
        result = pe._verify_execution_e2e(entry, trade)
        assert result["status"] == "unverified"
        assert result["checks_performed"] == []

    def test_unverified_when_empty_browser_order(self):
        entry = {"symbol": "EURUSD_otc", "direction": "call"}
        trade = {"browser_order": {}}
        result = pe._verify_execution_e2e(entry, trade)
        assert result["status"] == "unverified"

    def test_put_direction_match(self):
        entry = {"symbol": "AUDNZD_otc", "direction": "put"}
        trade = {
            "browser_order": {
                "raw": {
                    "command": {
                        "result": {
                            "evidence": {
                                "current_symbol": "AUD/NZD (OTC)",
                                "button_text": "Lower / Put",
                            }
                        }
                    }
                }
            }
        }
        result = pe._verify_execution_e2e(entry, trade)
        assert result["status"] == "verified_match"
        assert "direction" in result["checks_performed"]
        assert result["mismatches"] == []


# ═════════════════════════════════════════════════════════════════════════════
# 4. persist_trade_execution_metadata — state advancement
# ═════════════════════════════════════════════════════════════════════════════

class TestPersistMetadataStateAdvancement:
    """Test that persist_trade_execution_metadata advances execution_state."""

    def _setup_ledger_with_entry(self, entry):
        """Write a ledger with one entry for testing."""
        ledger = {
            "schema_version": "signal_paper_execution_ledger_v1",
            "entries": [entry],
            "updated_utc": entry["timestamp"],
        }
        pe._write_ledger(ledger)

    def test_browser_confirmed_advances_state(self):
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
        )
        self._setup_ledger_with_entry(entry)

        trade = {
            "strategy_id": entry["strategy_id"],
            "symbol": entry["symbol"],
            "timestamp": entry["timestamp"],
            "browser_trade_confirmed": True,
            "browser_command_dispatched": True,
            "browser_order": {},
        }
        result = pe.persist_trade_execution_metadata(trade)
        assert result is True

        ledger = pe._read_ledger()
        updated = ledger["entries"][0]
        assert updated["execution_state"] == "browser_confirmed"

    def test_browser_dispatched_advances_state(self):
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
        )
        self._setup_ledger_with_entry(entry)

        trade = {
            "strategy_id": entry["strategy_id"],
            "symbol": entry["symbol"],
            "timestamp": entry["timestamp"],
            "browser_command_dispatched": True,
            "browser_trade_confirmed": False,
            "browser_order": {},
        }
        result = pe.persist_trade_execution_metadata(trade)
        assert result is True

        ledger = pe._read_ledger()
        updated = ledger["entries"][0]
        assert updated["execution_state"] == "browser_dispatched"

    def test_verification_field_added(self):
        entry = pe._build_deferred_entry(
            _make_strategy(), _make_signal(), _make_feature(),
        )
        self._setup_ledger_with_entry(entry)

        trade = {
            "strategy_id": entry["strategy_id"],
            "symbol": entry["symbol"],
            "timestamp": entry["timestamp"],
            "browser_command_dispatched": True,
            "browser_order": {},
        }
        pe.persist_trade_execution_metadata(trade)

        ledger = pe._read_ledger()
        updated = ledger["entries"][0]
        assert "verification" in updated
        assert "status" in updated["verification"]


# ═════════════════════════════════════════════════════════════════════════════
# 5. resolve_pending_paper_trades — resolved_win / resolved_loss
# ═════════════════════════════════════════════════════════════════════════════

class TestResolveExecutionState:
    """Test that resolve sets execution_state to resolved_win / resolved_loss."""

    def _setup_pending_entry(self, direction="call", entry_price=1.0850,
                              feature_key="po:EURUSD_otc:1m"):
        entry = {
            "timestamp": pe._utc_now(),
            "symbol": "EURUSD_otc",
            "direction": direction,
            "result": "pending_resolution",
            "profit": 0.0,
            "entry_price": entry_price,
            "entry_payout_pct": 82.0,
            "paper_shadow": True,
            "paper_only": True,
            "strategy_id": "test_strat",
            "venue": "pocket_option",
            "resolved": False,
            "feature_key": feature_key,
            "resolution_mode": "deferred_forward_v1",
            "execution_state": "signal_generated",
            "confidence": 0.75,
        }
        ledger = {
            "schema_version": "signal_paper_execution_ledger_v1",
            "entries": [entry],
            "updated_utc": entry["timestamp"],
        }
        pe._write_ledger(ledger)
        return entry

    def test_win_sets_resolved_win(self):
        self._setup_pending_entry(direction="call", entry_price=1.0850)
        feature_snapshot = {
            "items": [
                {
                    "key": "po:EURUSD_otc:1m",
                    "last": 1.0900,  # price went up → call wins
                    "price_available": True,
                    "is_stale": False,
                }
            ]
        }
        with patch.object(pe._cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.001), \
             patch.object(pe._cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 99999), \
             patch.object(pe, "_update_platform_metrics", lambda x: None), \
             patch.object(pe, "_update_strategy_scorecards", lambda x: None):
            result = pe.resolve_pending_paper_trades(feature_snapshot)

        assert result["resolved"] == 1
        ledger = pe._read_ledger()
        assert ledger["entries"][0]["execution_state"] == "resolved_win"
        assert ledger["entries"][0]["result"] == "win"

    def test_loss_sets_resolved_loss(self):
        self._setup_pending_entry(direction="call", entry_price=1.0850)
        feature_snapshot = {
            "items": [
                {
                    "key": "po:EURUSD_otc:1m",
                    "last": 1.0800,  # price went down → call loses
                    "price_available": True,
                    "is_stale": False,
                }
            ]
        }
        with patch.object(pe._cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.001), \
             patch.object(pe._cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 99999), \
             patch.object(pe, "_update_platform_metrics", lambda x: None), \
             patch.object(pe, "_update_strategy_scorecards", lambda x: None):
            result = pe.resolve_pending_paper_trades(feature_snapshot)

        assert result["resolved"] == 1
        ledger = pe._read_ledger()
        assert ledger["entries"][0]["execution_state"] == "resolved_loss"
        assert ledger["entries"][0]["result"] == "loss"

    def test_timeout_sets_resolved_loss(self):
        """Expired trades get execution_state resolved_loss."""
        entry = {
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "symbol": "EURUSD_otc",
            "direction": "call",
            "result": "pending_resolution",
            "profit": 0.0,
            "entry_price": 1.0850,
            "entry_payout_pct": 82.0,
            "paper_shadow": True,
            "paper_only": True,
            "strategy_id": "test_strat",
            "venue": "pocket_option",
            "resolved": False,
            "feature_key": "po:EURUSD_otc:1m",
            "resolution_mode": "deferred_forward_v1",
            "execution_state": "signal_generated",
        }
        ledger = {
            "schema_version": "signal_paper_execution_ledger_v1",
            "entries": [entry],
            "updated_utc": entry["timestamp"],
        }
        pe._write_ledger(ledger)

        with patch.object(pe._cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 60), \
             patch.object(pe, "_update_platform_metrics", lambda x: None), \
             patch.object(pe, "_update_strategy_scorecards", lambda x: None):
            result = pe.resolve_pending_paper_trades({"items": []})

        assert result["expired"] == 1
        ledger = pe._read_ledger()
        assert ledger["entries"][0]["execution_state"] == "resolved_loss"
        assert ledger["entries"][0]["resolution_mode"] == "timeout_expired"

    def test_put_win(self):
        self._setup_pending_entry(direction="put", entry_price=1.0850)
        feature_snapshot = {
            "items": [
                {
                    "key": "po:EURUSD_otc:1m",
                    "last": 1.0800,  # price went down → put wins
                    "price_available": True,
                    "is_stale": False,
                }
            ]
        }
        with patch.object(pe._cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.001), \
             patch.object(pe._cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 99999), \
             patch.object(pe, "_update_platform_metrics", lambda x: None), \
             patch.object(pe, "_update_strategy_scorecards", lambda x: None):
            result = pe.resolve_pending_paper_trades(feature_snapshot)

        assert result["resolved"] == 1
        ledger = pe._read_ledger()
        assert ledger["entries"][0]["execution_state"] == "resolved_win"


# ═════════════════════════════════════════════════════════════════════════════
# 6. execute_signal_paper_trade — context/audit passthrough
# ═════════════════════════════════════════════════════════════════════════════

class TestExecuteSignalPaperTradePassthrough:
    """Test that execute_signal_paper_trade passes context and audit to entry."""

    def test_context_and_audit_in_trade(self):
        dc = _make_decision_context()
        ga = _make_gate_audit()

        with patch.object(pe._cfg, "AUTONOMY_CONFIG", {"trade_cooldown_seconds": 0}):
            result = pe.execute_signal_paper_trade(
                _make_strategy(),
                _make_signal(),
                _make_feature(),
                _make_lane(),
                decision_context=dc,
                gate_audit=ga,
            )

        assert result["success"] is True
        trade = result["trade"]
        assert trade["decision_context"] == dc
        assert trade["gate_audit"] == ga

    def test_no_context_when_none(self):
        with patch.object(pe._cfg, "AUTONOMY_CONFIG", {"trade_cooldown_seconds": 0}):
            result = pe.execute_signal_paper_trade(
                _make_strategy(),
                _make_signal(),
                _make_feature(),
                _make_lane(),
            )

        assert result["success"] is True
        assert "decision_context" not in result["trade"]
        assert "gate_audit" not in result["trade"]

    def test_trade_persisted_in_ledger_with_context(self):
        dc = _make_decision_context()
        ga = _make_gate_audit()

        with patch.object(pe._cfg, "AUTONOMY_CONFIG", {"trade_cooldown_seconds": 0}):
            pe.execute_signal_paper_trade(
                _make_strategy(),
                _make_signal(),
                _make_feature(),
                _make_lane(),
                decision_context=dc,
                gate_audit=ga,
            )

        ledger = pe._read_ledger()
        last_entry = ledger["entries"][-1]
        assert last_entry["decision_context"] == dc
        assert last_entry["gate_audit"] == ga
        assert last_entry["execution_state"] == "signal_generated"


# ═════════════════════════════════════════════════════════════════════════════
# 7. IBKR execution path differentiation (5.2)
# ═════════════════════════════════════════════════════════════════════════════

class TestIBKRExecutionPath:
    """Test that IBKR trades follow a different execution_state path."""

    def test_ibkr_entry_stays_internal_paper_shadow(self):
        """IBKR trades never go through browser dispatch — they stay internal."""
        with patch.object(pe._cfg, "AUTONOMY_CONFIG", {"trade_cooldown_seconds": 0}):
            result = pe.execute_signal_paper_trade(
                _make_strategy(venue="ibkr"),
                _make_signal(),
                _make_feature(),
                _make_lane(platform="ibkr_paper"),
            )

        assert result["success"] is True
        trade = result["trade"]
        assert trade["execution_state"] == "internal_paper_shadow"

    def test_ibkr_resolve_sets_correct_final_state(self):
        """After resolution, IBKR trades also get resolved_win/resolved_loss."""
        entry = {
            "timestamp": pe._utc_now(),
            "symbol": "AAPL",
            "direction": "call",
            "result": "pending_resolution",
            "profit": 0.0,
            "entry_price": 150.00,
            "entry_payout_pct": 80.0,
            "paper_shadow": True,
            "paper_only": True,
            "strategy_id": "ibkr_test",
            "venue": "ibkr",
            "resolved": False,
            "feature_key": "ibkr:AAPL:5m",
            "resolution_mode": "deferred_forward_v1",
            "execution_state": "internal_paper_shadow",
            "confidence": 0.7,
        }
        ledger = {
            "schema_version": "signal_paper_execution_ledger_v1",
            "entries": [entry],
            "updated_utc": entry["timestamp"],
        }
        pe._write_ledger(ledger)

        feature_snapshot = {
            "items": [
                {
                    "key": "ibkr:AAPL:5m",
                    "last": 155.00,
                    "price_available": True,
                    "is_stale": False,
                }
            ]
        }
        with patch.object(pe._cfg, "RESOLUTION_PRICE_THRESHOLD_PCT", 0.001), \
             patch.object(pe._cfg, "PENDING_TRADE_TIMEOUT_SECONDS", 99999), \
             patch.object(pe, "_update_platform_metrics", lambda x: None), \
             patch.object(pe, "_update_strategy_scorecards", lambda x: None):
            result = pe.resolve_pending_paper_trades(feature_snapshot)

        assert result["resolved"] == 1
        ledger = pe._read_ledger()
        assert ledger["entries"][0]["execution_state"] == "resolved_win"


# ═════════════════════════════════════════════════════════════════════════════
# 8. Edge cases
# ═════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case tests for Fase 5 features."""

    def test_signal_not_ready_returns_early(self):
        result = pe.execute_signal_paper_trade(
            _make_strategy(),
            _make_signal(execution_ready=False),
            _make_feature(),
            _make_lane(),
        )
        assert result["success"] is False
        assert result["error"] == "signal_not_ready_for_execution"

    def test_no_price_returns_early(self):
        feature = _make_feature()
        feature["price_available"] = False
        result = pe.execute_signal_paper_trade(
            _make_strategy(),
            _make_signal(),
            feature,
            _make_lane(),
        )
        assert result["success"] is False
        assert result["error"] == "no_price_context_for_signal_execution"

    def test_persist_metadata_rejects_non_dict(self):
        assert pe.persist_trade_execution_metadata("not_a_dict") is False
        assert pe.persist_trade_execution_metadata(None) is False

    def test_persist_metadata_rejects_missing_keys(self):
        assert pe.persist_trade_execution_metadata({"strategy_id": "x"}) is False
        assert pe.persist_trade_execution_metadata({"symbol": "y"}) is False

    def test_verify_e2e_partial_evidence(self):
        """Only symbol check available, no direction evidence."""
        entry = {"symbol": "EURUSD_otc", "direction": "call"}
        trade = {
            "browser_order": {
                "raw": {
                    "command": {
                        "result": {
                            "evidence": {
                                "current_symbol": "EUR/USD (OTC)",
                                # no button_text, no journal
                            }
                        }
                    }
                }
            }
        }
        result = pe._verify_execution_e2e(entry, trade)
        # Symbol matches, no direction to check → verified_match
        assert result["status"] == "verified_match"
        assert "symbol" in result["checks_performed"]
        assert "direction" not in result["checks_performed"]
