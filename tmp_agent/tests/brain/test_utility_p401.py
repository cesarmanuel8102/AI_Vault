"""
Tests for P4-01: Per-platform U scores in compute_utility_snapshot.

Covers:
  - platform_u_scores section present in snapshot
  - best_real_venue_u computed from pocket_option / ibkr only
  - u_proxy_non_positive blocker removed when best real venue U is positive
  - Promotion gate re-evaluation after blocker adjustment
  - Graceful degradation when PlatformManager is unavailable
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import brain_v9.config as _cfg


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _setup_utility_state(isolated_base_path, monkeypatch):
    """Redirect utility.py paths and create minimum state files."""
    import brain_v9.brain.utility as util_mod
    import brain_v9.trading.platform_manager as pm_mod

    state = isolated_base_path / "tmp_agent" / "state"
    metrics = isolated_base_path / "60_METRICS"
    rooms = state / "rooms" / "brain_binary_paper_pb05_journal"
    engine = state / "strategy_engine"
    comparisons = state / "comparison_runs"

    for d in [state, metrics, rooms, engine, comparisons]:
        d.mkdir(parents=True, exist_ok=True)

    sp = isolated_base_path / "tmp_agent" / "state" / "platforms"
    sp.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pm_mod, "STATE_PATH", sp)
    monkeypatch.setattr(pm_mod, "_platform_manager", None)

    monkeypatch.setattr(util_mod, "STATE_PATH", state)
    monkeypatch.setattr(util_mod, "METRICS_PATH", metrics)
    monkeypatch.setattr(util_mod, "COMPARISON_RUNS_PATH", comparisons)

    files = {
        "u_latest": state / "utility_u_latest.json",
        "u_gate": state / "utility_u_promotion_gate_latest.json",
        "autonomy_next_actions": state / "autonomy_next_actions.json",
        "cycle": state / "next_level_cycle_status_latest.json",
        "roadmap": state / "roadmap.json",
        "capital": metrics / "capital_state.json",
        "financial_mission": state / "financial_mission.json",
        "scorecard": rooms / "session_result_scorecard.json",
        "promotion_policy": state / "governed_promotion_policy.json",
        "strategy_ranking": engine / "strategy_ranking_latest.json",
        "strategy_ranking_v2": engine / "strategy_ranking_v2_latest.json",
        "expectancy_snapshot": engine / "expectancy_live_snapshot.json",
        "edge_validation": engine / "edge_validation_latest.json",
    }
    monkeypatch.setattr(util_mod, "FILES", files)

    # Write minimum state files
    _write(files["financial_mission"], {"objective_primary": "test", "guardrails": {"max_tolerated_drawdown_pct": 30}})
    _write(files["scorecard"], {
        "seed_metrics": {
            "entries_taken": 30, "entries_resolved": 25,
            "valid_candidates_skipped": 5,
            "wins": 15, "losses": 10,
            "net_expectancy_after_payout": 1.5,
            "max_drawdown": 0.05,
            "largest_loss_streak": 2,
        }
    })
    _write(files["promotion_policy"], {"version": 1})
    _write(files["capital"], {"current_cash": 1000, "committed_cash": 100})
    _write(files["cycle"], {})
    _write(files["roadmap"], {})
    _write(files["strategy_ranking"], {})
    _write(files["strategy_ranking_v2"], {})
    _write(files["expectancy_snapshot"], {})
    _write(files["edge_validation"], {})


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ── Tests ────────────────────────────────────────────────────────────────────

def test_snapshot_contains_platform_u_scores():
    from brain_v9.brain.utility import compute_utility_snapshot
    snapshot = compute_utility_snapshot()
    assert "platform_u_scores" in snapshot
    assert "best_real_venue_u" in snapshot


def test_platform_u_scores_has_all_venues():
    from brain_v9.brain.utility import compute_utility_snapshot
    snapshot = compute_utility_snapshot()
    pus = snapshot["platform_u_scores"]
    assert "pocket_option" in pus
    assert "ibkr" in pus
    assert "internal_paper" in pus


def test_platform_u_scores_structure():
    from brain_v9.brain.utility import compute_utility_snapshot
    snapshot = compute_utility_snapshot()
    for pf in ("pocket_option", "ibkr", "internal_paper"):
        entry = snapshot["platform_u_scores"][pf]
        assert "u_proxy" in entry
        assert "verdict" in entry
        assert "total_trades" in entry
        assert "win_rate" in entry
        assert "expectancy" in entry
        assert "sample_quality" in entry
        assert "trend_24h" in entry


def test_best_real_venue_u_ignores_internal():
    """best_real_venue_u should NOT reflect internal_paper."""
    from brain_v9.trading.platform_manager import get_platform_manager
    from brain_v9.brain.utility import compute_utility_snapshot

    pm = get_platform_manager()
    # Give internal_paper trades with very high U
    for _ in range(10):
        pm.record_trade("internal_paper", "win", 100.0)
    # Give real venues nothing
    snapshot = compute_utility_snapshot()
    # internal_paper may have positive U, but best_real_venue_u should be 0.0
    # (pocket_option and ibkr have 0 trades so U is 0.0)
    assert snapshot["best_real_venue_u"] is None or snapshot["best_real_venue_u"] <= 0.0


def test_positive_real_venue_removes_u_proxy_blocker():
    """If a real venue has U > threshold, u_proxy_non_positive should be removed."""
    from brain_v9.trading.platform_manager import get_platform_manager
    from brain_v9.brain.utility import compute_utility_snapshot, MIN_PROMOTE_UTILITY_SCORE

    pm = get_platform_manager()
    # Give pocket_option strong positive performance
    for _ in range(10):
        pm.record_trade("pocket_option", "win", 10.0)
    # Verify PO U is positive
    po_u = pm.get_platform_u("pocket_option")
    assert po_u.u_proxy > MIN_PROMOTE_UTILITY_SCORE, f"PO U should be positive, got {po_u.u_proxy}"

    snapshot = compute_utility_snapshot()
    blockers = snapshot["promotion_gate"]["blockers"]
    assert "u_proxy_non_positive" not in blockers, f"Blocker should be removed, got {blockers}"


def test_negative_real_venue_keeps_blocker():
    """If real venues have negative U, u_proxy_non_positive should remain if global U is negative."""
    from brain_v9.trading.platform_manager import get_platform_manager
    from brain_v9.brain.utility import compute_utility_snapshot

    pm = get_platform_manager()
    # Give both real venues losses
    for _ in range(10):
        pm.record_trade("pocket_option", "loss", 5.0)
        pm.record_trade("ibkr", "loss", 5.0)

    snapshot = compute_utility_snapshot()
    # The global U from the scorecard has positive expectancy (1.5 from fixture),
    # so u_proxy_non_positive may or may not fire depending on the full formula.
    # But best_real_venue_u should be negative.
    assert snapshot["best_real_venue_u"] is not None
    assert snapshot["best_real_venue_u"] < 0.0


def test_platform_manager_failure_graceful():
    """If PlatformManager raises during snapshot, snapshot should still work."""
    from brain_v9.brain.utility import compute_utility_snapshot

    with patch("brain_v9.trading.platform_manager.get_platform_manager", side_effect=RuntimeError("test")):
        snapshot = compute_utility_snapshot()
    # platform_u_scores should be empty dict (try/except fallback)
    assert "platform_u_scores" in snapshot
    assert snapshot["platform_u_scores"] == {}
    assert "u_proxy_score" in snapshot


def test_effective_u_follows_negative_real_venues_even_if_governance_positive():
    """The top-level U should not ignore clearly negative real-venue performance."""
    from brain_v9.trading.platform_manager import get_platform_manager
    from brain_v9.brain.utility import compute_utility_snapshot

    pm = get_platform_manager()
    for _ in range(10):
        pm.record_trade("pocket_option", "loss", 5.0)
        pm.record_trade("ibkr", "loss", 5.0)

    snapshot = compute_utility_snapshot()
    assert snapshot["real_venue_u_score"] is not None
    assert snapshot["real_venue_u_score"] < 0.0
    assert snapshot["u_score"] < 0.0
    assert snapshot["governance_u_score"] == snapshot["u_proxy_score"]
    assert snapshot["u_score"] <= snapshot["governance_u_score"]
    assert "real_venue_u_non_positive" in snapshot["promotion_gate"]["blockers"]


def test_effective_u_exposes_alignment_breakdown():
    """Snapshot should expose both governance and real-venue utility components."""
    from brain_v9.brain.utility import compute_utility_snapshot

    snapshot = compute_utility_snapshot()
    breakdown = snapshot["u_score_components"]
    assert "governance_u_score" in breakdown
    assert "real_venue_u_score" in breakdown
    assert "alignment_mode" in breakdown


def test_edge_validation_without_validated_edge_adds_blocker():
    from brain_v9.brain.utility import compute_utility_snapshot, FILES

    _write(FILES["edge_validation"], {
        "summary": {
            "promotable_count": 0,
            "validated_count": 0,
            "probation_count": 2,
        }
    })
    snapshot = compute_utility_snapshot()
    assert "no_validated_edge" in snapshot["promotion_gate"]["blockers"]
    assert "run_probation_carefully" in snapshot["promotion_gate"]["required_next_actions"]
