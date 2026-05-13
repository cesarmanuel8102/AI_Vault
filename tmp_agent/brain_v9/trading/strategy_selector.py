"""
Brain V9 - Strategy selector
Ranking cuantitativo v2 sobre expectancy, sample, contexto y salud de venue.
"""
from __future__ import annotations

import logging
from typing import Dict, List

MIN_SAMPLE_QUALITY_FOR_LEADER = 0.30
MIN_CONTEXT_SAMPLE_QUALITY_FOR_LEADER = 0.30
MIN_ENTRIES_FOR_LEADER = 8
MAX_EXPECTANCY_DRAWDOWN_FOR_PROBATION = -1.25
# P-OP20: Raised from 0.45 to 0.55, then to 0.58 (aligned with _BASE_CONFIDENCE_THRESHOLD).
# Signal must pass confidence >= 0.58 to be eligible for probation trade.
# 0.60 is appropriate for live.
MIN_SIGNAL_CONFIDENCE_FOR_PROBATION = 0.58
RECENT_LOSS_PENALTY = 0.08
log = logging.getLogger("strategy_selector")


def _signal_ready(candidate: Dict) -> bool:
    return bool(candidate.get("signal_ready", candidate.get("execution_ready")))


def _execution_ready_now(candidate: Dict) -> bool:
    return bool(candidate.get("execution_ready_now", candidate.get("execution_ready")))


def _current_context_execution_allowed(candidate: Dict) -> bool:
    return bool(candidate.get("current_context_execution_allowed", True))


def _probation_eligibility(candidate: Dict) -> Dict:
    governance_state = str(candidate.get("governance_state") or "")
    archive_state = str(candidate.get("archive_state") or "")
    expectancy = _safe_float(candidate.get("expectancy"), 0.0)
    context_expectancy = _safe_float(candidate.get("context_expectancy"), 0.0)
    symbol_expectancy = _safe_float(candidate.get("symbol_expectancy"), 0.0)
    signal_confidence = _safe_float(candidate.get("signal_confidence"), 0.0)
    leadership = _leadership_eligibility(candidate)
    best_entries = leadership["best_entries_resolved"]
    best_sample = leadership["best_sample_quality"]

    probation_eligible = True
    if archive_state.startswith("archived"):
        probation_eligible = False
    elif governance_state in {"frozen", "retired", "rejected"}:
        probation_eligible = False
    elif candidate.get("freeze_recommended"):
        probation_eligible = False
    elif not candidate.get("paper_only"):
        probation_eligible = False
    elif not candidate.get("venue_ready"):
        probation_eligible = False
    elif not _execution_ready_now(candidate):
        probation_eligible = False
    elif str(candidate.get("current_context_edge_state") or "") == "contradicted":
        probation_eligible = False
    # P-OP54a: Fix governance catch-22. Previously, leadership_eligible
    # (entries >= 8 AND sample >= 0.30) blocked probation entirely — even
    # when the strategy was LOSING money. A strategy with negative
    # expectancy needs to stay in probation to receive budget for
    # iteration. Only graduate out of probation when leadership eligible
    # AND the strategy actually has positive expectancy.
    elif leadership["leadership_eligible"] and max(expectancy, context_expectancy, symbol_expectancy) > 0:
        probation_eligible = False
    elif signal_confidence < MIN_SIGNAL_CONFIDENCE_FOR_PROBATION:
        probation_eligible = False
    elif max(expectancy, context_expectancy, symbol_expectancy) <= MAX_EXPECTANCY_DRAWDOWN_FOR_PROBATION:
        probation_eligible = False

    probation_budget = 0
    if probation_eligible:
        if best_entries <= 0:
            probation_budget = 3
        elif best_entries < 5 or best_sample < 0.20:
            probation_budget = 3
        elif best_entries < MIN_ENTRIES_FOR_LEADER or best_sample < MIN_SAMPLE_QUALITY_FOR_LEADER:
            probation_budget = 2
        else:
            probation_budget = 1

    return {
        "probation_eligible": probation_eligible,
        "probation_budget": probation_budget,
        "governance_lane": "probation" if probation_eligible else "standard",
    }


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception as exc:
        log.debug("_safe_float conversion failed for %r: %s", value, exc)
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _governance_bonus(state: str | None) -> float:
    state = str(state or "")
    if state == "promote_candidate":
        return 0.12
    if state == "paper_watch":
        return 0.06
    if state == "paper_active":
        return 0.05
    if state == "paper_candidate":
        return 0.02
    if state == "paper_probe":
        return -0.02
    if state == "frozen":
        return -0.18
    if state == "retired":
        return -0.50
    if state == "rejected":
        return -0.3
    return 0.0


def _reason(reasons: List[str], condition: bool, label: str):
    if condition:
        reasons.append(label)


def _sample_damping(best_sample_quality: float, best_entries_resolved: int) -> float:
    if best_entries_resolved <= 0:
        return 0.10
    if best_sample_quality < 0.10:
        return 0.18
    if best_sample_quality < 0.20:
        return 0.32
    if best_sample_quality < 0.30:
        return 0.52
    if best_sample_quality < 0.50:
        return 0.76
    return 1.0


def _recent_loss_penalty(recent_outcomes: List[str]) -> float:
    if not recent_outcomes:
        return 0.0
    latest = str(recent_outcomes[-1] or "").strip().lower()
    return RECENT_LOSS_PENALTY if latest == "loss" else 0.0


def _leadership_eligibility(candidate: Dict) -> Dict:
    sample_quality = _safe_float(candidate.get("sample_quality"), 0.0)
    context_sample_quality = _safe_float(candidate.get("context_sample_quality"), 0.0)
    symbol_sample_quality = _safe_float(candidate.get("symbol_sample_quality"), 0.0)
    entries_resolved = int(candidate.get("entries_resolved") or 0)
    context_entries_resolved = int(candidate.get("context_entries_resolved") or 0)
    symbol_entries_resolved = int(candidate.get("symbol_entries_resolved") or 0)
    best_sample_quality = max(sample_quality, context_sample_quality, symbol_sample_quality)
    best_entries_resolved = max(entries_resolved, context_entries_resolved, symbol_entries_resolved)
    leadership_sample_ready = (
        sample_quality >= MIN_SAMPLE_QUALITY_FOR_LEADER
        or context_sample_quality >= MIN_CONTEXT_SAMPLE_QUALITY_FOR_LEADER
    )
    leadership_entries_ready = best_entries_resolved >= MIN_ENTRIES_FOR_LEADER
    leadership_eligible = leadership_sample_ready and leadership_entries_ready
    return {
        "best_sample_quality": round(best_sample_quality, 4),
        "best_entries_resolved": best_entries_resolved,
        "leadership_sample_ready": leadership_sample_ready,
        "leadership_entries_ready": leadership_entries_ready,
        "leadership_eligible": leadership_eligible,
        "sample_damping": _sample_damping(best_sample_quality, best_entries_resolved),
    }


def compute_rank_score(candidate: Dict, top_action: str | None) -> Dict:
    expectancy_score = _safe_float(candidate.get("expectancy_score"), 0.0)
    win_rate_score = _safe_float(candidate.get("win_rate_score"), 0.0)
    profit_factor_score = _safe_float(candidate.get("profit_factor_score"), 0.0)
    sample_quality = _safe_float(candidate.get("sample_quality"), 0.0)
    consistency_score = _safe_float(candidate.get("consistency_score"), 0.0)
    drawdown_penalty = _safe_float(candidate.get("drawdown_penalty"), 0.0)
    venue_health_score = _safe_float(candidate.get("venue_health_score"), 0.0)
    regime_alignment_score = _safe_float(candidate.get("regime_alignment_score"), 0.0)

    context_expectancy_score = _safe_float(candidate.get("context_expectancy_score"), 0.0)
    context_sample_quality = _safe_float(candidate.get("context_sample_quality"), 0.0)
    context_consistency_score = _safe_float(candidate.get("context_consistency_score"), 0.0)
    symbol_expectancy_score = _safe_float(candidate.get("symbol_expectancy_score"), 0.0)
    symbol_sample_quality = _safe_float(candidate.get("symbol_sample_quality"), 0.0)

    governance_state = candidate.get("governance_state")
    context_governance_state = candidate.get("context_governance_state")
    execution_ready_score = 1.0 if _execution_ready_now(candidate) else 0.0
    signal_valid_score = 1.0 if candidate.get("signal_valid") else 0.0
    signal_confidence = _safe_float(candidate.get("signal_confidence"), 0.0)
    signal_blockers = candidate.get("signal_blockers") or []
    signal_blocker_penalty = min(len(signal_blockers) * 0.12, 0.36)
    archived_penalty = 1.0 if str(candidate.get("archive_state") or "").startswith("archived") else 0.0
    active_strategy_health_score = 1.0 if governance_state in {"paper_active", "paper_watch", "promote_candidate"} else 0.4
    frozen_penalty = 1.0 if candidate.get("freeze_recommended") or governance_state == "frozen" else 0.0
    retired_penalty = 1.0 if governance_state == "retired" else 0.0
    leadership = _leadership_eligibility(candidate)
    probation = _probation_eligibility(candidate)
    recent_loss_penalty = _recent_loss_penalty(candidate.get("recent_5_outcomes") or [])
    current_context_edge_state = str(candidate.get("current_context_edge_state") or "")
    current_context_expectancy = _safe_float(candidate.get("current_context_expectancy"), 0.0)
    current_context_sample_quality = _safe_float(candidate.get("current_context_sample_quality"), 0.0)
    current_context_entries_resolved = int(candidate.get("current_context_entries_resolved") or 0)
    current_context_execution_allowed = _current_context_execution_allowed(candidate)
    current_context_bias = 0.0
    if current_context_edge_state == "validated":
        current_context_bias += 0.14
    elif current_context_edge_state == "supportive":
        current_context_bias += 0.08
    elif current_context_edge_state == "contradicted":
        current_context_bias -= 0.22
    elif current_context_edge_state == "unproven" and _execution_ready_now(candidate):
        current_context_bias -= 0.04

    raw_rank_score = (
        0.24 * expectancy_score +
        0.16 * win_rate_score +
        0.14 * profit_factor_score +
        0.14 * sample_quality +
        0.12 * consistency_score +
        0.06 * venue_health_score +
        0.04 * regime_alignment_score +
        0.16 * context_expectancy_score +
        0.08 * context_sample_quality +
        0.06 * context_consistency_score +
        0.04 * symbol_expectancy_score +
        0.03 * symbol_sample_quality +
        0.08 * execution_ready_score +
        0.05 * signal_valid_score +
        0.06 * signal_confidence +
        0.04 * active_strategy_health_score +
        current_context_bias
        - 0.18 * drawdown_penalty
        - 0.10 * frozen_penalty
        - signal_blocker_penalty
        - recent_loss_penalty
        - 0.25 * archived_penalty
        - 0.50 * retired_penalty
        + _governance_bonus(governance_state)
        + (0.05 if context_governance_state == "promote_candidate" else 0.03 if context_governance_state == "paper_watch" else 0.0)
    )

    if candidate.get("paper_only"):
        raw_rank_score += 0.04
    if candidate.get("venue_ready"):
        raw_rank_score += 0.05
    else:
        raw_rank_score -= 0.12

    if top_action == "increase_resolved_sample":
        raw_rank_score += 0.06 * max(context_sample_quality, sample_quality)
    elif top_action == "improve_expectancy_or_reduce_penalties":
        raw_rank_score += 0.08 * max(context_expectancy_score, expectancy_score)
    elif top_action == "select_and_compare_strategies":
        raw_rank_score += 0.05
    elif top_action == "improve_signal_capture_and_context_window":
        raw_rank_score += 0.03

    raw_rank_score = round(_clamp(raw_rank_score, -1.0, 1.5), 4)
    rank_score = round(_clamp(raw_rank_score * leadership["sample_damping"], -1.0, 1.5), 4)

    reasons: List[str] = []
    _reason(reasons, candidate.get("paper_only"), "paper_safe")
    _reason(reasons, candidate.get("venue_ready"), "venue_ready")
    _reason(reasons, _signal_ready(candidate), "signal_ready")
    _reason(reasons, _execution_ready_now(candidate), "execution_ready_now")
    _reason(reasons, current_context_execution_allowed, "current_context_execution_allowed")
    _reason(reasons, candidate.get("signal_valid"), "signal_valid")
    _reason(reasons, not _signal_ready(candidate), "signal_not_ready")
    _reason(reasons, _signal_ready(candidate) and not _execution_ready_now(candidate), "governance_blocked")
    _reason(reasons, bool(signal_blockers), "signal_blocked")
    _reason(reasons, not candidate.get("venue_ready"), "venue_not_ready")
    _reason(reasons, expectancy_score > 0, "expectancy_positive")
    _reason(reasons, context_expectancy_score > 0, "best_context_positive_expectancy")
    _reason(reasons, symbol_expectancy_score > 0, "best_symbol_positive_expectancy")
    _reason(reasons, sample_quality > 0.25, "uses_existing_sample")
    _reason(reasons, context_sample_quality > 0.1, "best_context_sample")
    _reason(reasons, symbol_sample_quality > 0.1, "best_symbol_sample")
    _reason(reasons, consistency_score > 0, "consistency_support")
    _reason(reasons, drawdown_penalty >= 0.5, "drawdown_pressure")
    _reason(reasons, governance_state == "frozen", "strategy_frozen")
    _reason(reasons, governance_state == "retired", "strategy_retired")
    _reason(reasons, archived_penalty > 0, "strategy_archived")
    _reason(reasons, governance_state == "paper_watch", "strategy_watch")
    _reason(reasons, governance_state == "promote_candidate", "strategy_promote_candidate")
    _reason(reasons, context_governance_state == "frozen", "context_frozen")
    _reason(reasons, context_governance_state == "promote_candidate", "context_promote_candidate")
    _reason(reasons, top_action == "select_and_compare_strategies", "comparison_cycle_priority")
    _reason(reasons, leadership["leadership_eligible"], "leadership_eligible")
    _reason(reasons, not leadership["leadership_eligible"], "leadership_sample_gated")
    _reason(reasons, probation["probation_eligible"], "probation_eligible")
    _reason(reasons, recent_loss_penalty > 0, "recent_loss_penalty")
    _reason(reasons, current_context_edge_state == "validated", "current_context_validated")
    _reason(reasons, current_context_edge_state == "supportive", "current_context_supportive")
    _reason(reasons, current_context_edge_state == "unproven", "current_context_unproven")
    _reason(reasons, current_context_edge_state == "contradicted", "current_context_contradicted")

    return {
        "rank_score": rank_score,
        "raw_rank_score": raw_rank_score,
        "reasons": reasons,
        "score_breakdown": {
            "expectancy_score": expectancy_score,
            "win_rate_score": win_rate_score,
            "profit_factor_score": profit_factor_score,
            "sample_quality": sample_quality,
            "consistency_score": consistency_score,
            "drawdown_penalty": drawdown_penalty,
            "venue_health_score": venue_health_score,
            "regime_alignment_score": regime_alignment_score,
            "context_expectancy_score": context_expectancy_score,
            "context_sample_quality": context_sample_quality,
            "context_consistency_score": context_consistency_score,
            "symbol_expectancy_score": symbol_expectancy_score,
            "symbol_sample_quality": symbol_sample_quality,
            "active_strategy_health_score": active_strategy_health_score,
            "frozen_penalty": frozen_penalty,
            "execution_ready_score": execution_ready_score,
            "signal_valid_score": signal_valid_score,
            "signal_confidence": signal_confidence,
            "signal_blocker_penalty": round(signal_blocker_penalty, 4),
            "recent_loss_penalty": round(recent_loss_penalty, 4),
            "sample_damping": leadership["sample_damping"],
            "best_sample_quality": leadership["best_sample_quality"],
            "best_entries_resolved": leadership["best_entries_resolved"],
            "current_context_edge_state": current_context_edge_state or "unknown",
            "current_context_expectancy": current_context_expectancy,
            "current_context_sample_quality": current_context_sample_quality,
            "current_context_entries_resolved": current_context_entries_resolved,
            "current_context_bias": round(current_context_bias, 4),
            "archived_penalty": archived_penalty,
            "retired_penalty": retired_penalty,
        },
        "leadership": leadership,
        "probation": probation,
    }


def build_ranking(candidates: List[Dict], top_action: str | None) -> List[Dict]:
    ranked = []
    for candidate in candidates:
        ranked_candidate = dict(candidate)
        scoring = compute_rank_score(ranked_candidate, top_action)
        ranked_candidate["rank_score"] = scoring["rank_score"]
        ranked_candidate["raw_rank_score"] = scoring["raw_rank_score"]
        ranked_candidate["priority_score"] = scoring["rank_score"]
        ranked_candidate["reasons"] = scoring["reasons"]
        ranked_candidate["score_breakdown"] = scoring["score_breakdown"]
        ranked_candidate.update(scoring["leadership"])
        ranked_candidate.update(scoring["probation"])
        ranked.append(ranked_candidate)

    ranked.sort(
        key=lambda x: (
            x.get("rank_score", 0.0),
            x.get("context_sample_quality", 0.0),
            x.get("sample_quality", 0.0),
            x.get("context_expectancy", 0.0),
            x.get("expectancy", 0.0),
            x.get("symbol_expectancy", 0.0),
        ),
        reverse=True,
    )
    return ranked


def choose_top_candidate(ranked: List[Dict], allow_frozen: bool = False) -> Dict | None:
    if not ranked:
        return None
    if allow_frozen:
        for candidate in ranked:
            if str(candidate.get("archive_state") or "").startswith("archived"):
                continue
            if str(candidate.get("governance_state") or "") == "retired":
                continue
            if not _signal_ready(candidate):
                continue
            if not _current_context_execution_allowed(candidate):
                continue
            return candidate
        return None
    for candidate in ranked:
        governance_state = candidate.get("governance_state")
        context_governance_state = candidate.get("context_governance_state")
        if governance_state == "retired":
            continue
        if candidate.get("freeze_recommended") or governance_state == "frozen":
            continue
        if context_governance_state == "frozen":
            continue
        if not candidate.get("leadership_eligible"):
            continue
        if not _execution_ready_now(candidate):
            continue
        if not _current_context_execution_allowed(candidate):
            continue
        if str(candidate.get("archive_state") or "").startswith("archived"):
            continue
        return candidate
    return None


def choose_recovery_candidate(ranked: List[Dict]) -> Dict | None:
    top_candidate = choose_top_candidate(ranked, allow_frozen=False)
    if top_candidate:
        return top_candidate

    for candidate in ranked:
        if candidate.get("probation_eligible"):
            continue
        if not candidate.get("paper_only"):
            continue
        if not candidate.get("venue_ready"):
            continue
        if str(candidate.get("archive_state") or "").startswith("archived"):
            continue
        if str(candidate.get("governance_state") or "") == "retired":
            continue

        governance_state = str(candidate.get("governance_state") or "")
        context_governance_state = str(candidate.get("context_governance_state") or "")
        context_expectancy_score = _safe_float(candidate.get("context_expectancy_score"), 0.0)
        context_sample_quality = _safe_float(candidate.get("context_sample_quality"), 0.0)
        symbol_expectancy_score = _safe_float(candidate.get("symbol_expectancy_score"), 0.0)
        symbol_sample_quality = _safe_float(candidate.get("symbol_sample_quality"), 0.0)

        if context_governance_state == "frozen":
            continue

        has_recoverable_context = context_expectancy_score > 0 and context_sample_quality >= 0.10
        has_recoverable_symbol = symbol_expectancy_score > 0 and symbol_sample_quality >= 0.20

        if governance_state == "frozen" and not (has_recoverable_context or has_recoverable_symbol):
            continue

        if _execution_ready_now(candidate):
            if not _current_context_execution_allowed(candidate):
                continue
            return candidate

        if has_recoverable_context or has_recoverable_symbol:
            return candidate

    return None


def choose_exploit_candidate(ranked: List[Dict]) -> Dict | None:
    top_candidate = choose_top_candidate(ranked, allow_frozen=False)
    if top_candidate:
        return top_candidate

    for candidate in ranked:
        if str(candidate.get("archive_state") or "").startswith("archived"):
            continue
        if candidate.get("freeze_recommended"):
            continue
        if str(candidate.get("governance_state") or "") == "rejected":
            continue
        if str(candidate.get("governance_state") or "") == "retired":
            continue
        if str(candidate.get("context_governance_state") or "") == "rejected":
            continue
        if not candidate.get("paper_only"):
            continue
        if not candidate.get("venue_ready"):
            continue
        if not _execution_ready_now(candidate):
            continue
        if not _current_context_execution_allowed(candidate):
            continue
        if not candidate.get("signal_valid"):
            continue
        if candidate.get("leadership_eligible"):
            return candidate

    return None


def choose_explore_candidate(ranked: List[Dict], exclude_strategy_id: str | None = None) -> Dict | None:
    exploratory = []
    excluded = str(exclude_strategy_id or "").strip()

    for candidate in ranked:
        strategy_id = str(candidate.get("strategy_id") or "").strip()
        if excluded and strategy_id == excluded:
            continue
        if str(candidate.get("archive_state") or "").startswith("archived"):
            continue
        if not candidate.get("paper_only"):
            continue
        if not candidate.get("venue_ready"):
            continue
        if not _execution_ready_now(candidate):
            continue
        if str(candidate.get("current_context_edge_state") or "") == "contradicted":
            continue

        governance_state = str(candidate.get("governance_state") or "")
        context_governance_state = str(candidate.get("context_governance_state") or "")
        if governance_state == "rejected" or context_governance_state == "rejected":
            continue
        if governance_state == "retired":
            continue
        if governance_state == "frozen":
            context_expectancy = max(
                _safe_float(candidate.get("context_expectancy"), 0.0),
                _safe_float(candidate.get("context_expectancy_score"), 0.0),
            )
            symbol_expectancy = max(
                _safe_float(candidate.get("symbol_expectancy"), 0.0),
                _safe_float(candidate.get("symbol_expectancy_score"), 0.0),
            )
            sample_quality = _safe_float(candidate.get("sample_quality"), 0.0)
            context_sample_quality = _safe_float(candidate.get("context_sample_quality"), 0.0)
            symbol_sample_quality = _safe_float(candidate.get("symbol_sample_quality"), 0.0)
            if (
                max(context_expectancy, symbol_expectancy) <= 0.0
                or max(sample_quality, context_sample_quality, symbol_sample_quality) < 0.10
            ):
                continue

        expectancy_bias = max(
            _safe_float(candidate.get("expectancy"), 0.0),
            _safe_float(candidate.get("context_expectancy"), 0.0),
            _safe_float(candidate.get("symbol_expectancy"), 0.0),
        )
        exploratory.append((
            1 if not candidate.get("leadership_eligible") else 0,
            1 if governance_state not in {"frozen", "rejected"} and context_governance_state != "frozen" else 0,
            round(expectancy_bias, 4),
            _safe_float(candidate.get("signal_confidence"), 0.0),
            _safe_float(candidate.get("raw_rank_score"), 0.0),
            candidate,
        ))

    if not exploratory:
        return None

    exploratory.sort(reverse=True)
    return exploratory[0][-1]


def choose_probation_candidate(ranked: List[Dict], exclude_strategy_id: str | None = None) -> Dict | None:
    excluded = str(exclude_strategy_id or "").strip()
    probationary = []

    for candidate in ranked:
        strategy_id = str(candidate.get("strategy_id") or "").strip()
        if excluded and strategy_id == excluded:
            continue
        if not candidate.get("probation_eligible"):
            continue
        if str(candidate.get("current_context_edge_state") or "") == "contradicted":
            continue
        probationary.append((
            candidate.get("probation_budget", 0),
            _safe_float(candidate.get("signal_confidence"), 0.0),
            _safe_float(candidate.get("rank_score"), 0.0),
            candidate,
        ))

    if not probationary:
        return None

    probationary.sort(reverse=True)
    return probationary[0][-1]


# ---------------------------------------------------------------------------
# P4-12: Multi-candidate selection with cross-venue diversity
# ---------------------------------------------------------------------------

def _is_eligible(candidate: Dict, allow_frozen: bool = False) -> bool:
    """Shared eligibility check used by multi-candidate selectors."""
    if str(candidate.get("archive_state") or "").startswith("archived"):
        return False
    if str(candidate.get("governance_state") or "") == "retired":
        return False
    if not _execution_ready_now(candidate):
        return False
    if not _current_context_execution_allowed(candidate):
        return False
    if allow_frozen:
        return True
    governance = candidate.get("governance_state")
    context_governance = candidate.get("context_governance_state")
    if candidate.get("freeze_recommended") or governance == "frozen":
        return False
    if context_governance == "frozen":
        return False
    if not candidate.get("leadership_eligible"):
        return False
    return True


def choose_top_n_candidates(
    ranked: List[Dict],
    n: int = 2,
    *,
    allow_frozen: bool = False,
    exclude_strategy_ids: List[str] | None = None,
) -> List[Dict]:
    """Return up to *n* eligible candidates, preferring cross-venue diversity.

    Algorithm
    ---------
    1. First pass: pick the **best eligible candidate per venue** (preserving
       the pre-sorted rank order).  This guarantees cross-venue diversity
       whenever the ranked list contains strategies from different venues.
    2. Second pass: if fewer than *n* slots are filled, backfill from the
       remaining eligible candidates regardless of venue.
    3. The returned list is re-sorted by ``rank_score`` descending so callers
       can rely on a consistent ordering.
    """
    if n <= 0 or not ranked:
        return []

    excluded = set(str(sid) for sid in (exclude_strategy_ids or []) if sid)
    eligible = [
        c for c in ranked
        if _is_eligible(c, allow_frozen=allow_frozen)
        and str(c.get("strategy_id") or "") not in excluded
    ]

    selected: List[Dict] = []
    selected_ids: set = set()

    # --- Pass 1: best per venue -------------------------------------------
    seen_venues: set = set()
    for candidate in eligible:
        venue = str(candidate.get("venue") or "unknown")
        if venue in seen_venues:
            continue
        selected.append(candidate)
        selected_ids.add(candidate.get("strategy_id"))
        seen_venues.add(venue)
        if len(selected) >= n:
            break

    # --- Pass 2: backfill remaining slots ---------------------------------
    if len(selected) < n:
        for candidate in eligible:
            sid = candidate.get("strategy_id")
            if sid in selected_ids:
                continue
            selected.append(candidate)
            selected_ids.add(sid)
            if len(selected) >= n:
                break

    # Re-sort by rank_score descending so the caller gets a consistent order
    selected.sort(key=lambda c: _safe_float(c.get("rank_score"), 0.0), reverse=True)
    return selected
