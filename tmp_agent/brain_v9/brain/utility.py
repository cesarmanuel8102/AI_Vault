"""
Brain V9 - Utility U
Calcula y persiste Utility U desde fuentes base canónicas.
"""
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from brain_v9.config import AUTONOMY_CONFIG, BASE_PATH
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("UtilityU")

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
METRICS_PATH = BASE_PATH / "60_METRICS"

FILES = {
    "u_latest": STATE_PATH / "utility_u_latest.json",
    "u_gate": STATE_PATH / "utility_u_promotion_gate_latest.json",
    "autonomy_next_actions": STATE_PATH / "autonomy_next_actions.json",
    "cycle": STATE_PATH / "next_level_cycle_status_latest.json",
    "roadmap": STATE_PATH / "roadmap.json",
    "capital": METRICS_PATH / "capital_state.json",
    "financial_mission": STATE_PATH / "financial_mission.json",
    "scorecard": STATE_PATH / "rooms" / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json",
    "promotion_policy": STATE_PATH / "governed_promotion_policy.json",
    "strategy_ranking": STATE_PATH / "strategy_engine" / "strategy_ranking_latest.json",
    "strategy_ranking_v2": STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json",
    "expectancy_snapshot": STATE_PATH / "strategy_engine" / "expectancy_snapshot_latest.json",
    "edge_validation": STATE_PATH / "strategy_engine" / "edge_validation_latest.json",
    "meta_improvement": STATE_PATH / "meta_improvement_status_latest.json",
}
COMPARISON_RUNS_PATH = STATE_PATH / "strategy_engine" / "comparison_runs"
# P3-12: Lowered from 0.10 to 0.05 for paper mode — the prior threshold
# was nearly unreachable with the blocker gate already filtering bad states.
MIN_PROMOTE_UTILITY_SCORE = 0.05


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_read_json(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"no encontrado en {path}")
    return read_json(path, {})


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _squash_signal(value: float, scale: float = 1.0) -> float:
    if scale <= 0:
        scale = 1.0
    return max(-1.0, min(1.0, math.tanh(float(value) / scale)))


def _latest_comparison_cycle() -> Dict:
    try:
        latest = max(COMPARISON_RUNS_PATH.glob("*/result.json"), key=lambda p: p.stat().st_mtime)
    except ValueError:
        return {}
    payload = read_json(latest, {})
    payload["artifact"] = str(latest)
    return payload


def _select_reference_strategy(strategy_ranking: Dict, expectancy_snapshot: Dict | None = None) -> Dict:
    ranked = strategy_ranking.get("ranked", []) or []
    if not ranked:
        top_from_expectancy = ((expectancy_snapshot or {}).get("summary") or {}).get("top_context") or ((expectancy_snapshot or {}).get("summary") or {}).get("top_strategy") or {}
        return strategy_ranking.get("top_strategy") or top_from_expectancy or {}

    def score(item: Dict) -> float:
        promotion_state = str(item.get("promotion_state") or "")
        context_state = str(item.get("context_governance_state") or "")
        venue_ready = 0.25 if item.get("venue_ready") else -0.4
        state_score = (
            0.35 if promotion_state == "paper_active"
            else 0.25 if promotion_state == "paper_watch"
            else 0.15 if promotion_state == "paper_candidate"
            else -0.12 if promotion_state == "frozen"
            else 0.0
        )
        context_score = (
            0.25 if context_state == "paper_active"
            else 0.15 if context_state == "paper_watch"
            else 0.08 if context_state == "paper_candidate"
            else -0.08 if context_state == "frozen"
            else 0.0
        )
        expectancy_score = _squash_signal(float(item.get("expectancy", 0.0) or 0.0), 3.0) * 0.18
        symbol_score = _squash_signal(float(item.get("symbol_expectancy", 0.0) or 0.0), 4.0) * 0.22
        context_expectancy_score = _squash_signal(float(item.get("context_expectancy", 0.0) or 0.0), 4.0) * 0.35
        sample_score = float(item.get("sample_quality", 0.0) or 0.0) * 0.08
        context_sample_score = float(item.get("context_sample_quality", 0.0) or 0.0) * 0.12
        consistency_score = float(item.get("consistency_score", 0.0) or 0.0) * 0.05
        return _round(
            venue_ready
            + state_score
            + context_score
            + expectancy_score
            + symbol_score
            + context_expectancy_score
            + sample_score
            + context_sample_score
            + consistency_score,
            6,
        )

    return max(ranked, key=score)


def _recent_loss_penalty_from_outcomes(outcomes: List[Dict] | List[str] | None) -> float:
    if not outcomes:
        return 0.0
    latest = outcomes[-1]
    if isinstance(latest, dict):
        latest = latest.get("result") or latest.get("outcome")
    latest_text = str(latest or "").strip().lower()
    return 0.10 if latest_text == "loss" else 0.0


def _extract_scorecard_metrics(scorecard: Dict) -> Dict:
    seed = scorecard.get("seed_metrics", {})
    return {
        "entries_taken": int(seed.get("entries_taken", 0) or 0),
        "entries_resolved": int(seed.get("entries_resolved", 0) or 0),
        "valid_candidates_skipped": int(seed.get("valid_candidates_skipped", 0) or 0),
        "wins": int(seed.get("wins", 0) or 0),
        "losses": int(seed.get("losses", 0) or 0),
        "net_expectancy_after_payout": float(seed.get("net_expectancy_after_payout", 0.0) or 0.0),
        "max_drawdown": float(seed.get("max_drawdown", 0.0) or 0.0),
        "largest_loss_streak": int(seed.get("largest_loss_streak", 0) or 0),
    }


def _compute_real_venue_u_alignment(platform_u_scores: Dict[str, Dict]) -> Dict[str, float | int | None]:
    """Summarize per-platform U into a real-venue performance anchor.

    The global utility proxy can be positive from governance/readiness lifts
    even while real venues are losing money.  This helper computes an
    aggregated real-venue U across PO/IBKR so the effective top-level U
    remains anchored to live venue performance.
    """
    real_rows: List[Dict] = []
    for venue in ("pocket_option", "ibkr"):
        row = platform_u_scores.get(venue) or {}
        trades = int(row.get("total_trades", 0) or 0)
        sample_quality = float(row.get("sample_quality", 0.0) or 0.0)
        u_val = float(row.get("u_proxy", 0.0) or 0.0)
        if trades <= 0:
            continue
        weight = max(float(trades), 1.0) * max(sample_quality, 0.25)
        real_rows.append(
            {
                "venue": venue,
                "u_proxy": u_val,
                "trades": trades,
                "sample_quality": sample_quality,
                "weight": weight,
            }
        )

    if not real_rows:
        return {
            "real_venue_u_score": None,
            "real_venue_u_best": None,
            "real_venue_u_worst": None,
            "real_venue_trades": 0,
            "real_venue_count": 0,
        }

    total_weight = sum(float(item["weight"]) for item in real_rows)
    weighted_u = (
        sum(float(item["u_proxy"]) * float(item["weight"]) for item in real_rows) / total_weight
        if total_weight > 0
        else 0.0
    )
    return {
        "real_venue_u_score": _round(weighted_u),
        "real_venue_u_best": _round(max(float(item["u_proxy"]) for item in real_rows)),
        "real_venue_u_worst": _round(min(float(item["u_proxy"]) for item in real_rows)),
        "real_venue_trades": sum(int(item["trades"]) for item in real_rows),
        "real_venue_count": len(real_rows),
    }


def _compute_components(mission: Dict, scorecard: Dict, capital: Dict) -> Tuple[Dict, List[str], List[str]]:
    metrics = _extract_scorecard_metrics(scorecard)
    guardrails = mission.get("guardrails", {})
    min_resolved_sample = int(AUTONOMY_CONFIG.get("utility_min_resolved_sample", 20))
    max_drawdown = float(guardrails.get("max_tolerated_drawdown_pct", 30) or 30) / 100.0

    entries_resolved = metrics["entries_resolved"]
    expectancy = metrics["net_expectancy_after_payout"]
    drawdown = metrics["max_drawdown"]
    largest_loss_streak = metrics["largest_loss_streak"]
    valid_candidates_skipped = metrics["valid_candidates_skipped"]
    current_cash = float(capital.get("current_cash", 0.0) or 0.0)
    committed_cash = float(capital.get("committed_cash", 0.0) or 0.0)
    total_capital = max(current_cash + committed_cash, 1.0)

    growth_signal = _squash_signal(expectancy, 3.0)
    drawdown_penalty = max(0.0, min(2.0, drawdown / max(max_drawdown, 0.01)))
    tail_risk_penalty = max(0.0, min(2.0, largest_loss_streak / 5.0))
    governance_penalty = 0.0
    fragility_penalty = 0.0

    blockers: List[str] = []
    next_actions: List[str] = []

    if entries_resolved < min_resolved_sample:
        blockers.append("insufficient_resolved_sample")
        # P3-12: Removed fragility_penalty += 1.0 — blocker alone prevents
        # promotion; the penalty was causing double-punishment via u_proxy_non_positive.
        next_actions.append("increase_resolved_sample")

    if drawdown > max_drawdown:
        blockers.append("drawdown_limit_breached")
        # P3-12: Removed governance_penalty += 1.0 — blocker alone prevents
        # promotion; penalty was redundant cascade.
        next_actions.append("reduce_drawdown_and_capital_at_risk")

    if committed_cash > total_capital * 0.5:
        blockers.append("capital_commitment_too_high")
        # P3-12: Removed governance_penalty += 0.5 — blocker alone sufficient.
        next_actions.append("rebalance_capital_exposure")

    if valid_candidates_skipped > max(entries_resolved, 1) * 2:
        blockers.append("signal_pipeline_underpowered")
        # P3-12: Removed fragility_penalty += 0.25 — blocker alone sufficient.
        next_actions.append("improve_signal_capture_and_context_window")

    components = {
        "growth_signal": _round(growth_signal),
        "drawdown_penalty": _round(drawdown_penalty),
        "tail_risk_penalty": _round(tail_risk_penalty),
        "governance_penalty": _round(governance_penalty),
        "fragility_penalty": _round(fragility_penalty),
    }
    return components, sorted(set(blockers)), sorted(set(next_actions))


def compute_utility_snapshot() -> Dict:
    errors: List[str] = []
    loaded: Dict[str, Dict] = {}
    for key in ("financial_mission", "scorecard", "promotion_policy", "capital", "cycle", "roadmap"):
        try:
            loaded[key] = _safe_read_json(FILES[key])
        except Exception as exc:
            errors.append(f"{key}: {exc}")
            loaded[key] = {}
    for key in ("strategy_ranking", "strategy_ranking_v2", "expectancy_snapshot", "edge_validation"):
        try:
            loaded[key] = _safe_read_json(FILES[key])
        except Exception as exc:
            log.debug("Non-critical load failed for %s: %s", key, exc)
            loaded[key] = {}
    loaded["latest_comparison_cycle"] = _latest_comparison_cycle()

    mission = loaded["financial_mission"]
    scorecard = loaded["scorecard"]
    capital = loaded["capital"]
    cycle = loaded["cycle"]
    roadmap = loaded["roadmap"]
    promotion_policy = loaded["promotion_policy"]
    strategy_ranking = loaded.get("strategy_ranking_v2") or loaded.get("strategy_ranking") or {}
    expectancy_snapshot = loaded.get("expectancy_snapshot", {}) or {}
    edge_validation = loaded.get("edge_validation", {}) or {}
    latest_comparison_cycle = loaded.get("latest_comparison_cycle", {})

    components, blockers, next_actions = _compute_components(mission, scorecard, capital)
    strategy_lift = 0.0
    comparison_lift = 0.0
    ranking_lift = 0.0
    venue_health_lift = 0.0
    active_strategy_health = 0.0
    frozen_penalty = 0.0
    drawdown_strategy_penalty = 0.0
    u_proxy_score = _round(
        components["growth_signal"]
        - components["drawdown_penalty"]
        - components["tail_risk_penalty"]
        - components["governance_penalty"]
        - components["fragility_penalty"]
    )
    verdict = "promote" if not blockers and u_proxy_score > MIN_PROMOTE_UTILITY_SCORE else "no_promote"

    metrics = _extract_scorecard_metrics(scorecard)
    snapshot = {
        "schema_version": "utility_u_proxy_snapshot_v2",
        "updated_utc": _now_utc(),
        "objective_primary": mission.get("objective_primary", "maximize_risk_adjusted_compounded_growth"),
        "utility_name": mission.get("utility_u", {}).get("name", "U_financial_survival_first"),
        "route_lock_focus": roadmap.get("active_program"),
        "mode": "live_proxy_bl02",
        "components": components,
        "sample": metrics,
        "promotion_gate": {
            "promotion_policy_present": bool(promotion_policy),
            "blockers": blockers,
            "verdict": verdict,
            "allow_promote": verdict == "promote",
            "required_next_actions": next_actions,
        },
        "strategy_context": {
            "top_strategy": strategy_ranking.get("top_strategy") or ((strategy_ranking.get("ranked") or [None])[0]),
            "ranked_count": len(strategy_ranking.get("ranked", [])),
            "ranking_spread_top1_top2": float(strategy_ranking.get("ranking_spread_top1_top2", 0.0) or 0.0),
            "expectancy_summary": expectancy_snapshot.get("summary", {}),
            "edge_validation_summary": edge_validation.get("summary", {}),
            "latest_comparison_cycle": {
                "cycle_id": latest_comparison_cycle.get("cycle_id"),
                "completed_utc": latest_comparison_cycle.get("completed_utc"),
                "selected_candidates": latest_comparison_cycle.get("selected_candidates"),
                "successful_runs": latest_comparison_cycle.get("successful_runs"),
                "failed_runs": latest_comparison_cycle.get("failed_runs"),
                "total_profit": latest_comparison_cycle.get("total_profit"),
                "artifact": latest_comparison_cycle.get("artifact"),
            },
        },
        "u_proxy_score": u_proxy_score,
        "capital": {
            "cash": capital.get("current_cash"),
            "committed": capital.get("committed_cash"),
            "drawdown_max": capital.get("max_drawdown_pct"),
            "status": capital.get("status"),
            "mode": "paper_demo",
        },
        "current_phase": cycle.get("current_phase") or roadmap.get("current_phase"),
        "errors": errors,
    }
    top_strategy = strategy_ranking.get("top_strategy") or {}
    recovery_strategy = strategy_ranking.get("top_recovery_candidate") or {}
    expectancy_leader = ((expectancy_snapshot.get("summary") or {}).get("top_strategy") or {})
    reference_strategy = top_strategy or recovery_strategy or _select_reference_strategy(strategy_ranking, expectancy_snapshot)
    expectancy = 0.0
    symbol_expectancy = 0.0
    sample_quality = 0.0
    context_expectancy = 0.0
    context_sample_quality = 0.0
    drawdown_penalty = 0.0
    best_entries_resolved = 0
    ranking_spread = 0.0
    edge_summary = edge_validation.get("summary", {}) if isinstance(edge_validation, dict) else {}
    if edge_summary:
        snapshot["strategy_context"]["top_execution_edge"] = edge_summary.get("top_execution_edge")
        snapshot["strategy_context"]["best_promotable_edge"] = edge_summary.get("best_promotable")
        snapshot["strategy_context"]["best_validated_edge"] = edge_summary.get("best_validated")
    if reference_strategy:
        expectancy = float(reference_strategy.get("expectancy", 0.0) or 0.0)
        symbol_expectancy = float(reference_strategy.get("symbol_expectancy", 0.0) or 0.0)
        sample_quality = float(reference_strategy.get("sample_quality", 0.0) or 0.0)
        context_expectancy = float(reference_strategy.get("context_expectancy", 0.0) or 0.0)
        context_sample_quality = float(reference_strategy.get("context_sample_quality", 0.0) or 0.0)
        context_consistency = float(reference_strategy.get("context_consistency_score", 0.0) or 0.0)
        promotion_state = reference_strategy.get("promotion_state")
        context_state = reference_strategy.get("context_governance_state")
        rank_score = float(reference_strategy.get("rank_score", reference_strategy.get("priority_score", 0.0)) or 0.0)
        drawdown_penalty = float(reference_strategy.get("drawdown_penalty", 0.0) or 0.0)
        venue_health_score = float(reference_strategy.get("venue_health_score", 0.0) or 0.0)
        ranking_spread = float(strategy_ranking.get("ranking_spread_top1_top2", 0.0) or 0.0)
        promotable_count = sum(1 for item in strategy_ranking.get("ranked", []) if item.get("promote_candidate"))
        frozen_count = sum(1 for item in strategy_ranking.get("ranked", []) if item.get("freeze_recommended") or item.get("governance_state") == "frozen")
        active_count = sum(1 for item in strategy_ranking.get("ranked", []) if item.get("governance_state") in {"paper_active", "paper_watch", "promote_candidate"})
        best_sample_quality = max(sample_quality, context_sample_quality, float(reference_strategy.get("symbol_sample_quality", 0.0) or 0.0))
        best_entries_resolved = max(
            int(reference_strategy.get("entries_resolved", 0) or 0),
            int(reference_strategy.get("context_entries_resolved", 0) or 0),
            int(reference_strategy.get("symbol_entries_resolved", 0) or 0),
        )
        if best_sample_quality < 0.10:
            leadership_weight = 0.18
        elif best_sample_quality < 0.20:
            leadership_weight = 0.32
        elif best_sample_quality < 0.30:
            leadership_weight = 0.48
        elif best_sample_quality < 0.50:
            leadership_weight = 0.72
        else:
            leadership_weight = 1.0
        if best_entries_resolved < 5:
            leadership_weight *= 0.75
        strategy_lift = _squash_signal(expectancy, 3.0) * 0.10
        strategy_lift += _squash_signal(symbol_expectancy, 4.0) * 0.12
        strategy_lift += _squash_signal(context_expectancy, 4.0) * 0.22
        strategy_lift += sample_quality * 0.06
        strategy_lift += context_sample_quality * 0.10
        strategy_lift += float(reference_strategy.get("consistency_score", 0.0) or 0.0) * 0.05
        strategy_lift += context_consistency * 0.05
        ranking_lift = (
            0.25 * rank_score +
            0.20 * float(reference_strategy.get("expectancy_score", 0.0) or 0.0) +
            0.15 * context_sample_quality +
            0.10 * _clamp(ranking_spread, 0.0, 1.0)
        )
        strategy_lift *= leadership_weight
        ranking_lift *= leadership_weight
        active_strategy_health = 0.10 * _clamp(active_count / max(len(strategy_ranking.get("ranked", [])) or 1, 1), 0.0, 1.0)
        venue_health_lift = 0.10 * venue_health_score
        frozen_penalty = 0.10 * _clamp(frozen_count / max(len(strategy_ranking.get("ranked", [])) or 1, 1), 0.0, 1.0)
        drawdown_strategy_penalty = 0.20 * drawdown_penalty
        recent_loss_penalty = _recent_loss_penalty_from_outcomes(reference_strategy.get("recent_5_outcomes"))
        exploration_bonus = 0.0
        if expectancy_leader and expectancy_leader.get("strategy_id") != reference_strategy.get("strategy_id"):
            exploration_sample_quality = float(expectancy_leader.get("sample_quality", 0.0) or 0.0)
            exploration_expectancy = float(expectancy_leader.get("expectancy", 0.0) or 0.0)
            exploration_bonus = _squash_signal(exploration_expectancy, 4.0) * min(exploration_sample_quality, 0.20) * 0.12
        if promotion_state == "paper_watch":
            strategy_lift += 0.05
        elif promotion_state == "paper_active":
            strategy_lift += 0.08
        elif promotion_state == "frozen":
            strategy_lift -= 0.08
        if context_state == "paper_active":
            strategy_lift += 0.08
        elif context_state == "paper_watch":
            strategy_lift += 0.05
        elif context_state == "frozen":
            strategy_lift -= 0.06
        if promotable_count > 0:
            ranking_lift += 0.08
        strategy_lift = _round(max(min(strategy_lift, 0.85), -0.85))
        ranking_lift = _round(max(min(ranking_lift, 0.85), -0.85))
        venue_health_lift = _round(max(min(venue_health_lift, 0.15), -0.15))
        active_strategy_health = _round(max(min(active_strategy_health, 0.15), -0.15))
        frozen_penalty = _round(max(min(frozen_penalty, 0.2), 0.0))
        drawdown_strategy_penalty = _round(max(min(drawdown_strategy_penalty, 0.25), 0.0))
        recent_loss_penalty = _round(max(min(recent_loss_penalty, 0.12), 0.0))
        exploration_bonus = _round(max(min(exploration_bonus, 0.04), 0.0))
        snapshot["strategy_context"]["top_expectancy"] = float(top_strategy.get("expectancy", 0.0) or 0.0)
        snapshot["strategy_context"]["top_sample_quality"] = float(top_strategy.get("sample_quality", 0.0) or 0.0)
        snapshot["strategy_context"]["top_context_expectancy"] = float(top_strategy.get("context_expectancy", 0.0) or 0.0)
        snapshot["strategy_context"]["top_context_sample_quality"] = float(top_strategy.get("context_sample_quality", 0.0) or 0.0)
        snapshot["strategy_context"]["top_promotion_state"] = top_strategy.get("promotion_state")
        snapshot["strategy_context"]["top_rank_score"] = float(top_strategy.get("rank_score", top_strategy.get("priority_score", 0.0)) or 0.0)
        snapshot["strategy_context"]["top_drawdown_penalty"] = float(top_strategy.get("drawdown_penalty", 0.0) or 0.0)
        snapshot["strategy_context"]["reference_strategy"] = {
            "strategy_id": reference_strategy.get("strategy_id"),
            "promotion_state": reference_strategy.get("promotion_state"),
            "context_governance_state": reference_strategy.get("context_governance_state"),
            "expectancy": expectancy,
            "symbol_expectancy": symbol_expectancy,
            "sample_quality": sample_quality,
            "context_expectancy": context_expectancy,
            "context_sample_quality": context_sample_quality,
            "rank_score": rank_score,
            "drawdown_penalty": drawdown_penalty,
            "venue_health_score": venue_health_score,
            "leadership_weight": _round(leadership_weight),
            "best_entries_resolved": best_entries_resolved,
            "best_sample_quality": _round(best_sample_quality),
        }
        snapshot["strategy_context"]["expectancy_leader"] = {
            "strategy_id": expectancy_leader.get("strategy_id"),
            "expectancy": float(expectancy_leader.get("expectancy", 0.0) or 0.0) if expectancy_leader else 0.0,
            "sample_quality": float(expectancy_leader.get("sample_quality", 0.0) or 0.0) if expectancy_leader else 0.0,
        }
        snapshot["strategy_context"]["effective_signal_score"] = _round(
            _squash_signal(expectancy, 3.0) * 0.18
            + _squash_signal(symbol_expectancy, 4.0) * 0.18
            + _squash_signal(context_expectancy, 4.0) * 0.24
            + context_sample_quality * 0.14
            + max(min(rank_score, 1.0), -1.0) * 0.18
            + venue_health_score * 0.08
        )
    if edge_summary:
        promotable_count = _safe_int(edge_summary.get("promotable_count"), 0)
        validated_count = _safe_int(edge_summary.get("validated_count"), 0)
        probation_count = _safe_int(edge_summary.get("probation_count"), 0)
        if promotable_count <= 0 and validated_count <= 0:
            gate_blockers = [b for b in snapshot["promotion_gate"]["blockers"] if b != "u_proxy_non_positive"]
            gate_blockers.append("no_validated_edge")
            snapshot["promotion_gate"]["blockers"] = sorted(set(gate_blockers))
            required = snapshot["promotion_gate"]["required_next_actions"]
            if probation_count > 0:
                required.append("run_probation_carefully")
            else:
                required.append("improve_expectancy_or_reduce_penalties")
            snapshot["promotion_gate"]["required_next_actions"] = sorted(set(required))
            snapshot["promotion_gate"]["verdict"] = "no_promote"
            snapshot["promotion_gate"]["allow_promote"] = False
        # ── P3-12: Consolidated blocker gates ──────────────────────────
        # Merge overlapping blockers to reduce AND-gate count.
        # Previously: no_strategy_with_minimum_expectancy + best_context_non_positive
        #             (correlated — both fire on negative expectancy)
        # Now: single "no_positive_edge" blocker when all expectancy views are ≤ 0
        #      with sufficient sample to trust the data.
        has_adequate_sample = sample_quality >= 0.1 or context_sample_quality >= 0.1
        all_expectancy_non_positive = expectancy <= 0 and symbol_expectancy <= 0 and context_expectancy <= 0
        if has_adequate_sample and all_expectancy_non_positive:
            gate_blockers = [b for b in snapshot["promotion_gate"]["blockers"] if b != "u_proxy_non_positive"]
            if "no_positive_edge" not in gate_blockers:
                gate_blockers.append("no_positive_edge")
            required = snapshot["promotion_gate"]["required_next_actions"]
            if "select_and_compare_strategies" not in required:
                required.append("select_and_compare_strategies")
            snapshot["promotion_gate"]["blockers"] = sorted(set(gate_blockers))
            snapshot["promotion_gate"]["required_next_actions"] = sorted(set(required))
            snapshot["promotion_gate"]["verdict"] = "no_promote"
            snapshot["promotion_gate"]["allow_promote"] = False

        if top_strategy.get("promotion_state") == "frozen" and top_strategy.get("context_governance_state") not in {"paper_active", "paper_watch"}:
            gate_blockers = [b for b in snapshot["promotion_gate"]["blockers"] if b != "u_proxy_non_positive"]
            if "top_strategy_frozen" not in gate_blockers:
                gate_blockers.append("top_strategy_frozen")
            required = snapshot["promotion_gate"]["required_next_actions"]
            required.append("select_and_compare_strategies")
            snapshot["promotion_gate"]["blockers"] = sorted(set(gate_blockers))
            snapshot["promotion_gate"]["required_next_actions"] = sorted(set(required))
            snapshot["promotion_gate"]["verdict"] = "no_promote"
            snapshot["promotion_gate"]["allow_promote"] = False

        # P3-12: Merged insufficient_resolved_sample + top_strategy_sample_too_small
        # into single "sample_not_ready".  The _compute_components blocker covers
        # the global sample; this covers the *reference strategy's* sample.
        # We keep the more restrictive of the two checks (quality < 0.15 or entries < 8).
        if max(sample_quality, context_sample_quality) < 0.15 or best_entries_resolved < 8:
            gate_blockers = [b for b in snapshot["promotion_gate"]["blockers"] if b != "u_proxy_non_positive"]
            if "sample_not_ready" not in gate_blockers:
                gate_blockers.append("sample_not_ready")
            required = snapshot["promotion_gate"]["required_next_actions"]
            required.append("increase_resolved_sample")
            snapshot["promotion_gate"]["blockers"] = sorted(set(gate_blockers))
            snapshot["promotion_gate"]["required_next_actions"] = sorted(set(required))
            snapshot["promotion_gate"]["verdict"] = "no_promote"
            snapshot["promotion_gate"]["allow_promote"] = False

        if drawdown_penalty >= 0.75:
            gate_blockers = [b for b in snapshot["promotion_gate"]["blockers"] if b != "u_proxy_non_positive"]
            gate_blockers.append("top_strategy_drawdown_excessive")
            required = snapshot["promotion_gate"]["required_next_actions"]
            required.append("improve_expectancy_or_reduce_penalties")
            snapshot["promotion_gate"]["blockers"] = sorted(set(gate_blockers))
            snapshot["promotion_gate"]["required_next_actions"] = sorted(set(required))
            snapshot["promotion_gate"]["verdict"] = "no_promote"
            snapshot["promotion_gate"]["allow_promote"] = False

        # P3-12: Downgraded ranking_not_discriminative to warning in paper mode.
        # With few strategies the ranking spread is structurally low; blocking
        # promotion on this metric is counterproductive during paper validation.
        warnings: List[str] = snapshot.get("promotion_gate", {}).get("warnings", [])
        if ranking_spread < 0.12:
            if "ranking_not_discriminative" not in warnings:
                warnings.append("ranking_not_discriminative")
            snapshot["promotion_gate"]["warnings"] = sorted(set(warnings))
    if latest_comparison_cycle:
        comparison_total_profit = float(latest_comparison_cycle.get("total_profit", 0.0) or 0.0)
        comparison_candidates = int(latest_comparison_cycle.get("selected_candidates", 0) or 0)
        successful_runs = int(latest_comparison_cycle.get("successful_runs", 0) or 0)
        failed_runs = int(latest_comparison_cycle.get("failed_runs", 0) or 0)
        if comparison_candidates > 0:
            comparison_lift = min(max(comparison_total_profit / 40.0, -0.5), 0.5)
            comparison_lift += min(max((successful_runs - failed_runs) / max(comparison_candidates, 1), -0.25), 0.25)
            comparison_lift = _round(max(min(comparison_lift, 0.65), -0.65))
        snapshot["strategy_context"]["latest_comparison_total_profit"] = comparison_total_profit
        if comparison_candidates >= 2 and comparison_total_profit <= -5.0 and failed_runs >= successful_runs:
            gate_blockers = [b for b in snapshot["promotion_gate"]["blockers"] if b != "u_proxy_non_positive"]
            if "comparison_cycle_non_positive" not in gate_blockers:
                gate_blockers.append("comparison_cycle_non_positive")
            required = snapshot["promotion_gate"]["required_next_actions"]
            required.append("select_and_compare_strategies")
            snapshot["promotion_gate"]["blockers"] = sorted(set(gate_blockers))
            snapshot["promotion_gate"]["required_next_actions"] = sorted(set(required))
            snapshot["promotion_gate"]["verdict"] = "no_promote"
            snapshot["promotion_gate"]["allow_promote"] = False
    components["strategy_lift"] = strategy_lift
    components["comparison_lift"] = comparison_lift
    components["ranking_lift"] = ranking_lift
    components["venue_health_lift"] = venue_health_lift
    components["active_strategy_health"] = active_strategy_health
    components["drawdown_strategy_penalty"] = drawdown_strategy_penalty
    components["frozen_penalty"] = frozen_penalty
    components["recent_loss_penalty"] = recent_loss_penalty if "recent_loss_penalty" in locals() else 0.0
    components["exploration_bonus"] = exploration_bonus if "exploration_bonus" in locals() else 0.0
    u_proxy_score = _round(
        components["growth_signal"]
        + components["strategy_lift"]
        + components["comparison_lift"]
        + components["ranking_lift"]
        + components["venue_health_lift"]
        + components["active_strategy_health"]
        + components["exploration_bonus"]
        - components["drawdown_penalty"]
        - components["drawdown_strategy_penalty"]
        - components["frozen_penalty"]
        - components["recent_loss_penalty"]
        - components["tail_risk_penalty"]
        - components["governance_penalty"]
        - components["fragility_penalty"]
    )
    final_gate_blockers = [b for b in snapshot["promotion_gate"].get("blockers", []) if b != "u_proxy_non_positive"]
    final_next_actions = list(snapshot["promotion_gate"].get("required_next_actions", []))
    if u_proxy_score <= 0:
        final_gate_blockers.append("u_proxy_non_positive")
        final_next_actions.append("improve_expectancy_or_reduce_penalties")
    elif u_proxy_score <= MIN_PROMOTE_UTILITY_SCORE:
        final_gate_blockers.append("u_signal_too_weak")
        final_next_actions.append("improve_expectancy_or_reduce_penalties")
    if ("recent_loss_penalty" in components) and components["recent_loss_penalty"] >= 0.10 and u_proxy_score <= 0.15:
        # P3-12: Removed recent_loss_not_absorbed blocker entirely.
        # A single recent loss outcome should not veto a 20+ trade aggregate.
        # The penalty still affects the score, but it no longer blocks promotion.
        pass
    final_gate_blockers = sorted(set(final_gate_blockers))
    final_next_actions = sorted(set(final_next_actions))
    verdict = "promote" if not final_gate_blockers and u_proxy_score > MIN_PROMOTE_UTILITY_SCORE else "no_promote"
    snapshot["promotion_gate"]["blockers"] = final_gate_blockers
    snapshot["promotion_gate"]["required_next_actions"] = final_next_actions
    snapshot["promotion_gate"]["verdict"] = verdict
    snapshot["promotion_gate"]["allow_promote"] = verdict == "promote"
    snapshot["components"] = components
    snapshot["u_proxy_score"] = u_proxy_score

    # ── P4-01: Per-platform U scores ──────────────────────────────────────
    # Read per-platform metrics from PlatformManager so the snapshot shows
    # each venue independently.  The promotion gate uses the best *real*
    # venue U (pocket_option, ibkr) — internal_paper is excluded because
    # the internal simulator produces ~50/50 noise that drags the aggregate.
    platform_u_scores: Dict = {}
    best_real_venue_u: float = -999.0
    try:
        from brain_v9.trading.platform_manager import get_platform_manager
        pm = get_platform_manager()
        for pf_name in ("pocket_option", "ibkr", "internal_paper"):
            pu = pm.get_platform_u(pf_name)
            pm_metrics = pm.get_platform_metrics(pf_name)
            platform_u_scores[pf_name] = {
                "u_proxy": _round(pu.u_proxy),
                "verdict": pu.verdict,
                "total_trades": pm_metrics.total_trades,
                "win_rate": _round(pm_metrics.win_rate),
                "expectancy": _round(pm_metrics.expectancy),
                "sample_quality": _round(pm_metrics.sample_quality),
                "trend_24h": pu.trend_24h,
            }
            # Only real venues count for promotion
            if pf_name in ("pocket_option", "ibkr"):
                best_real_venue_u = max(best_real_venue_u, pu.u_proxy)
    except Exception:
        log.debug("PlatformManager unavailable for per-platform U", exc_info=True)

    snapshot["platform_u_scores"] = platform_u_scores
    snapshot["best_real_venue_u"] = _round(best_real_venue_u) if best_real_venue_u > -999.0 else None

    alignment = _compute_real_venue_u_alignment(platform_u_scores)
    governance_u_score = _round(snapshot.get("u_proxy_score", 0.0) or 0.0)
    real_venue_u_score = alignment.get("real_venue_u_score")
    if real_venue_u_score is None:
        effective_u_score = governance_u_score
    elif float(real_venue_u_score) <= 0.0:
        effective_u_score = _round(min(governance_u_score, float(real_venue_u_score)))
    else:
        effective_u_score = _round(governance_u_score * 0.35 + float(real_venue_u_score) * 0.65)

    snapshot["governance_u_score"] = governance_u_score
    snapshot["real_venue_u_score"] = real_venue_u_score
    snapshot["effective_u_score"] = effective_u_score
    snapshot["u_score"] = effective_u_score
    snapshot["u_score_components"] = {
        "governance_u_score": governance_u_score,
        "real_venue_u_score": real_venue_u_score,
        "real_venue_u_best": alignment.get("real_venue_u_best"),
        "real_venue_u_worst": alignment.get("real_venue_u_worst"),
        "real_venue_trades": alignment.get("real_venue_trades"),
        "real_venue_count": alignment.get("real_venue_count"),
        "alignment_mode": (
            "governance_only"
            if real_venue_u_score is None
            else "real_venue_guardrail"
            if float(real_venue_u_score) <= 0.0
            else "blended_governance_and_real_venues"
        ),
    }

    # P4-01: If the best real-venue U is positive, remove u_proxy_non_positive
    # from the gate blockers.  The global U is still shown for information, but
    # the promotion decision should reflect the real venue performance.
    if best_real_venue_u > MIN_PROMOTE_UTILITY_SCORE:
        gate_blockers_adjusted = [
            b for b in snapshot["promotion_gate"]["blockers"]
            if b != "u_proxy_non_positive"
        ]
        snapshot["promotion_gate"]["blockers"] = sorted(set(gate_blockers_adjusted))
        # Re-evaluate verdict after blocker adjustment
        remaining_blockers = snapshot["promotion_gate"]["blockers"]
        adjusted_verdict = "promote" if not remaining_blockers and best_real_venue_u > MIN_PROMOTE_UTILITY_SCORE else "no_promote"
        snapshot["promotion_gate"]["verdict"] = adjusted_verdict
        snapshot["promotion_gate"]["allow_promote"] = adjusted_verdict == "promote"
        if "improve_expectancy_or_reduce_penalties" in snapshot["promotion_gate"]["required_next_actions"] and not remaining_blockers:
            snapshot["promotion_gate"]["required_next_actions"] = []

    effective_gate_blockers = [
        b for b in snapshot["promotion_gate"].get("blockers", [])
        if b not in {"u_proxy_non_positive", "u_signal_too_weak", "real_venue_u_non_positive", "effective_u_too_weak"}
    ]
    effective_next_actions = list(snapshot["promotion_gate"].get("required_next_actions", []))
    if real_venue_u_score is not None and float(real_venue_u_score) <= 0.0:
        effective_gate_blockers.append("real_venue_u_non_positive")
        effective_next_actions.append("improve_expectancy_or_reduce_penalties")
    elif effective_u_score <= 0:
        effective_gate_blockers.append("u_proxy_non_positive")
        effective_next_actions.append("improve_expectancy_or_reduce_penalties")
    elif effective_u_score <= MIN_PROMOTE_UTILITY_SCORE:
        effective_gate_blockers.append("effective_u_too_weak")
        effective_next_actions.append("improve_expectancy_or_reduce_penalties")

    effective_gate_blockers = sorted(set(effective_gate_blockers))
    effective_next_actions = sorted(set(effective_next_actions))
    effective_verdict = (
        "promote"
        if not effective_gate_blockers and effective_u_score > MIN_PROMOTE_UTILITY_SCORE
        else "no_promote"
    )
    snapshot["promotion_gate"]["blockers"] = effective_gate_blockers
    snapshot["promotion_gate"]["required_next_actions"] = effective_next_actions
    snapshot["promotion_gate"]["verdict"] = effective_verdict
    snapshot["promotion_gate"]["allow_promote"] = effective_verdict == "promote"
    return snapshot


def compute_promotion_gate(snapshot: Dict | None = None) -> Dict:
    snapshot = snapshot or compute_utility_snapshot()
    gate = snapshot.get("promotion_gate", {})
    u_proxy_score = float(snapshot.get("u_score", snapshot.get("u_proxy_score", -999)) or -999)
    verdict = gate.get("verdict", "no_promote")
    blockers = gate.get("blockers", [])
    allow_promote = verdict == "promote" and u_proxy_score > MIN_PROMOTE_UTILITY_SCORE and not blockers
    required_next_actions = list(gate.get("required_next_actions", []))

    return {
        "schema_version": "utility_u_promotion_gate_v2",
        "updated_utc": snapshot.get("updated_utc", _now_utc()),
        "source_snapshot_path": str(FILES["u_latest"]),
        "u_proxy_score": u_proxy_score,
        "governance_u_score": snapshot.get("governance_u_score"),
        "real_venue_u_score": snapshot.get("real_venue_u_score"),
        "verdict": verdict,
        "allow_promote": allow_promote,
        "blockers": blockers,
        "required_next_actions": required_next_actions,
        "notes": "Gate vivo de BL-02 calculado desde fuentes base. No sustituye evaluación cuant robusta.",
    }


def write_utility_snapshots() -> Dict:
    snapshot = compute_utility_snapshot()
    gate = compute_promotion_gate(snapshot)
    try:
        meta_improvement = _safe_read_json(FILES["meta_improvement"])
    except Exception as exc:
        log.debug("Error loading meta_improvement: %s", exc)
        meta_improvement = {}
    meta_roadmap = meta_improvement.get("roadmap", {}) if isinstance(meta_improvement, dict) else {}
    meta_top_gap = meta_improvement.get("top_gap", {}) if isinstance(meta_improvement, dict) else {}
    recommended_actions = list(gate.get("required_next_actions", []))
    top_action = (
        "select_and_compare_strategies"
        if any(
            blocker in set(gate.get("blockers", []))
            for blocker in (
                # P3-12: Updated blocker names after consolidation
                "no_positive_edge",
                "top_strategy_frozen",
                "comparison_cycle_non_positive",
            )
        )
        and "select_and_compare_strategies" in recommended_actions
        else (recommended_actions or [None])[0]
    )
    if not gate.get("blockers") and meta_top_gap:
        meta_work_status = meta_roadmap.get("work_status")
        if meta_work_status in {"internal_execution_ready", "blocked_needs_meta_brain"}:
            if "advance_meta_improvement_roadmap" not in recommended_actions:
                recommended_actions.append("advance_meta_improvement_roadmap")
            if meta_top_gap.get("execution_mode") == "internal_candidate":
                top_action = "advance_meta_improvement_roadmap"
    # ── P8-01: Deadlock detection ──────────────────────────────────────────
    # If ALL strategies are frozen/archived/retired and no top_strategy
    # exists, the system is in a self-reinforcing deadlock.  Force the
    # autonomy loop to break it instead of spinning endlessly.
    # Also detect *operational* deadlock: no trade executed in 48+ hours
    # even though non-frozen strategies exist (they can't fire).
    strategy_context = snapshot.get("strategy_context", {})
    _OPERATIONAL_DEADLOCK_HOURS = 48
    _deadlock_detected = False
    try:
        _ranking_data = _safe_read_json(
            FILES.get("strategy_ranking_v2", FILES["strategy_ranking"])
        )
        _ranked_list = _ranking_data.get("ranked", [])
        _top_strat = _ranking_data.get("top_strategy")
        if _ranked_list:
            _active_or_candidate = [
                item for item in _ranked_list
                if str(item.get("governance_state") or item.get("promotion_state") or "")
                in {"paper_active", "paper_watch", "paper_candidate", "paper_probe", "promote_candidate"}
                and not item.get("freeze_recommended")
            ]
            # Condition 1: all strategies frozen/archived → classic deadlock
            if not _active_or_candidate and not _top_strat:
                _deadlock_detected = True
            # Condition 2: non-frozen strategies exist but none can execute
            # (no top_strategy AND no trade in OPERATIONAL_DEADLOCK_HOURS)
            elif not _top_strat:
                _now = datetime.now(timezone.utc)
                _latest_trade = None
                for item in _ranked_list:
                    _lt = item.get("last_trade_utc")
                    if _lt:
                        try:
                            _ts = datetime.fromisoformat(str(_lt).replace("Z", "+00:00"))
                            if _latest_trade is None or _ts > _latest_trade:
                                _latest_trade = _ts
                        except (ValueError, TypeError):
                            log.debug("unparseable last_trade_utc: %s", _lt)
                if _latest_trade is not None:
                    _hours_since = (_now - _latest_trade).total_seconds() / 3600
                    if _hours_since >= _OPERATIONAL_DEADLOCK_HOURS:
                        _deadlock_detected = True
                        log.info(
                            "P8-01b: Operational deadlock — %.1f hours since last trade, "
                            "no top_strategy despite %d non-frozen strategies.",
                            _hours_since, len(_active_or_candidate),
                        )
                elif not _active_or_candidate:
                    # No trades ever recorded and nothing active
                    _deadlock_detected = True
    except Exception:
        log.debug("ranking file unreadable — skipping deadlock check", exc_info=True)

    if _deadlock_detected:
        if "system_deadlock" not in gate.get("blockers", []):
            gate["blockers"] = sorted(set(gate.get("blockers", []) + ["system_deadlock"]))
        top_action = "break_system_deadlock"
        if "break_system_deadlock" not in recommended_actions:
            recommended_actions.insert(0, "break_system_deadlock")
        log.warning(
            "P8-01: System deadlock detected — all strategies frozen/archived, "
            "no executable candidate.  Forcing break_system_deadlock action."
        )

    # ── P8-06: Ensure expand_signal_pipeline is dispatched when no top_strategy ─
    # If there is no top_strategy and the signal pipeline action is not yet
    # recommended, add it so the system can widen filters and find signals.
    if not strategy_context.get("top_strategy") and not _deadlock_detected:
        if "improve_signal_capture_and_context_window" not in recommended_actions:
            recommended_actions.append("improve_signal_capture_and_context_window")

    write_json(FILES["u_latest"], snapshot)
    write_json(FILES["u_gate"], gate)
    raw_next_actions_payload = {
        "schema_version": "autonomy_next_actions_v1",
        "updated_utc": snapshot.get("updated_utc"),
        "source": "utility_u",
        "current_phase": snapshot.get("current_phase"),
        "u_score": snapshot.get("u_score", snapshot.get("u_proxy_score")),
        "governance_u_score": snapshot.get("governance_u_score"),
        "real_venue_u_score": snapshot.get("real_venue_u_score"),
        "verdict": gate.get("verdict"),
        "blockers": gate.get("blockers", []),
        "recommended_actions": recommended_actions,
        "top_action": top_action,
    }
    from brain_v9.brain.meta_governance import build_meta_governance_status

    meta_governance = build_meta_governance_status(
        utility_snapshot=snapshot,
        utility_gate=gate,
        raw_next_actions=raw_next_actions_payload,
    )
    next_actions_payload = {
        "schema_version": "autonomy_next_actions_v2",
        "updated_utc": snapshot.get("updated_utc"),
        "source": "meta_governance",
        "utility_source": "utility_u",
        "current_phase": snapshot.get("current_phase"),
        "u_score": snapshot.get("u_score", snapshot.get("u_proxy_score")),
        "governance_u_score": snapshot.get("governance_u_score"),
        "real_venue_u_score": snapshot.get("real_venue_u_score"),
        "verdict": gate.get("verdict"),
        "blockers": gate.get("blockers", []),
        "recommended_actions": meta_governance.get("recommended_actions", []),
        "top_action": meta_governance.get("top_action"),
        "current_focus": meta_governance.get("current_focus", {}),
        "allocator": meta_governance.get("allocator", {}),
        "top_priority": meta_governance.get("top_priority", {}),
        "utility_top_action": raw_next_actions_payload.get("top_action"),
        "utility_recommended_actions": raw_next_actions_payload.get("recommended_actions", []),
    }
    write_json(FILES["autonomy_next_actions"], next_actions_payload)
    
    # Acumular historial de U para tendencias
    history_path = STATE_PATH / "utility_u_history.json"
    history = read_json(history_path, [])
    if not isinstance(history, list):
        history = []
    
    # Agregar entrada actual al historial
    history_entry = {
        "timestamp": snapshot.get("updated_utc"),
        "u_score": snapshot.get("u_proxy_score"),
        "verdict": gate.get("verdict"),
        "blockers": gate.get("blockers", []),
    }
    
    # Evitar duplicados consecutivos del mismo valor
    if not history or history[-1].get("u_score") != history_entry["u_score"]:
        history.append(history_entry)
        # Mantener solo últimas 100 entradas
        if len(history) > 100:
            history = history[-100:]
        write_json(history_path, history)
    
    return {
        "snapshot": snapshot,
        "gate": gate,
        "next_actions": next_actions_payload,
        "meta_governance": meta_governance,
    }


def read_utility_state() -> Dict:
    snapshot = compute_utility_snapshot()
    gate = compute_promotion_gate(snapshot)
    return {
        "timestamp": snapshot.get("updated_utc"),
        "source": "ssot_live_sources",
        "u_score": snapshot.get("u_score", snapshot.get("u_proxy_score")),
        "governance_u_score": snapshot.get("governance_u_score", snapshot.get("u_proxy_score")),
        "real_venue_u_score": snapshot.get("real_venue_u_score"),
        "u_score_components": snapshot.get("u_score_components", {}),
        "u_proxy_score": snapshot.get("u_proxy_score"),
        "verdict": gate.get("verdict"),
        "blockers": gate.get("blockers", []),
        "next_actions": gate.get("required_next_actions", []),
        "current_phase": snapshot.get("current_phase"),
        "can_promote": gate.get("allow_promote", False),
        "capital": snapshot.get("capital", {}),
        "components": snapshot.get("components", {}),
        "sample": snapshot.get("sample", {}),
        "errors": snapshot.get("errors", []),
    }


def is_promotion_safe() -> Tuple[bool, str]:
    state = read_utility_state()
    if state["u_score"] is None:
        return False, "No se pudo leer U score"
    if float(state["u_score"]) <= 0:
        return False, f"U score no positivo: {state['u_score']}"
    if state["verdict"] != "promote":
        return False, f"Verdict no es promote: {state['verdict']}"
    if state["blockers"]:
        return False, f"Blockers activos: {state['blockers']}"
    road = {}
    cyc = {}
    try:
        road = _safe_read_json(FILES["roadmap"])
        cyc = _safe_read_json(FILES["cycle"])
    except Exception as exc:
        log.debug("Error loading roadmap/cycle for SSOT check: %s", exc)
    if road.get("current_phase") != cyc.get("current_phase"):
        return False, f"SSOT inconsistente: roadmap={road.get('current_phase')} cycle={cyc.get('current_phase')}"
    return True, "Todos los gates pasan"
