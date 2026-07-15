"""Read-only strategy engine routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-MEGA-AGGRESSIVE-SWEEP-14B
"""
from __future__ import annotations

from fastapi import APIRouter

from brain_v9.trading.expectancy_engine import (
    build_expectancy_snapshot,
    read_expectancy_by_strategy,
    read_expectancy_by_strategy_context,
    read_expectancy_by_strategy_symbol,
    read_expectancy_by_strategy_venue,
    read_expectancy_snapshot,
)
from brain_v9.trading.post_trade_analysis import build_post_trade_analysis_snapshot
from brain_v9.trading.post_trade_hypotheses import build_post_trade_hypothesis_snapshot
from brain_v9.trading.strategy_engine import (
    read_active_strategy_catalog_state,
    read_candidates as read_strategy_candidates,
    read_context_edge_validation_state,
    read_edge_validation_state,
    read_feature_snapshot as read_strategy_feature_snapshot,
    read_market_history_state as read_strategy_market_history,
    read_pipeline_integrity_state,
    read_ranking as read_strategy_ranking,
    read_ranking_v2 as read_strategy_ranking_v2,
    read_signal_snapshot as read_strategy_signal_snapshot,
    read_strategy_archive_state,
    refresh_strategy_engine,
)

router = APIRouter(tags=["strategy-readonly"])


@router.get("/brain/strategy-engine/summary")
async def brain_strategy_engine_summary():
    return refresh_strategy_engine()["summary"]


@router.get("/brain/strategy-engine/candidates")
async def brain_strategy_engine_candidates():
    refresh_strategy_engine()
    return read_strategy_candidates()


@router.get("/brain/strategy-engine/scorecards")
async def brain_strategy_engine_scorecards():
    return refresh_strategy_engine()["scorecards"]


@router.get("/brain/strategy-engine/ranking")
async def brain_strategy_engine_ranking():
    refresh_strategy_engine()
    return read_strategy_ranking()


@router.get("/brain/strategy-engine/ranking-v2")
async def brain_strategy_engine_ranking_v2():
    refresh_strategy_engine()
    return read_strategy_ranking_v2()


@router.get("/brain/strategy-engine/features")
async def brain_strategy_engine_features():
    refresh_strategy_engine()
    return read_strategy_feature_snapshot()


@router.get("/brain/strategy-engine/history")
async def brain_strategy_engine_history():
    refresh_strategy_engine()
    return read_strategy_market_history()


@router.get("/brain/strategy-engine/signals")
async def brain_strategy_engine_signals():
    refresh_strategy_engine()
    return read_strategy_signal_snapshot()


@router.get("/brain/strategy-engine/archive")
async def brain_strategy_engine_archive():
    refresh_strategy_engine()
    return read_strategy_archive_state()


@router.get("/brain/strategy-engine/expectancy")
async def brain_strategy_engine_expectancy():
    build_expectancy_snapshot()
    return read_expectancy_snapshot()


@router.get("/brain/strategy-engine/expectancy/by-strategy")
async def brain_strategy_engine_expectancy_by_strategy():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy()


@router.get("/brain/strategy-engine/expectancy/by-venue")
async def brain_strategy_engine_expectancy_by_venue():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy_venue()


@router.get("/brain/strategy-engine/expectancy/by-symbol")
async def brain_strategy_engine_expectancy_by_symbol():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy_symbol()


@router.get("/brain/strategy-engine/expectancy/by-context")
async def brain_strategy_engine_expectancy_by_context():
    build_expectancy_snapshot()
    return read_expectancy_by_strategy_context()


@router.get("/brain/strategy-engine/edge-validation")
async def brain_strategy_engine_edge_validation():
    refresh_strategy_engine()
    return read_edge_validation_state()


@router.get("/brain/strategy-engine/context-edge-validation")
async def brain_strategy_engine_context_edge_validation():
    refresh_strategy_engine()
    return read_context_edge_validation_state()


@router.get("/brain/strategy-engine/active-catalog")
async def brain_strategy_engine_active_catalog():
    refresh_strategy_engine()
    return read_active_strategy_catalog_state()


@router.get("/brain/strategy-engine/pipeline-integrity")
async def brain_strategy_engine_pipeline_integrity():
    refresh_strategy_engine()
    return read_pipeline_integrity_state()


@router.get("/brain/strategy-engine/post-trade-analysis")
async def brain_strategy_engine_post_trade_analysis():
    return build_post_trade_analysis_snapshot()


@router.get("/brain/strategy-engine/post-trade-hypotheses")
async def brain_strategy_engine_post_trade_hypotheses(include_llm: bool = True):
    return await build_post_trade_hypothesis_snapshot(include_llm=include_llm)


@router.get("/brain/strategy-engine/learning-loop")
async def brain_strategy_engine_learning_loop():
    from brain_v9.trading.learning_loop import build_learning_loop_snapshot

    return build_learning_loop_snapshot()


@router.get("/brain/strategy-engine/hypotheses")
async def brain_strategy_engine_hypotheses():
    return refresh_strategy_engine()["hypotheses"]


@router.get("/brain/strategy-engine/execution-audit")
async def brain_strategy_engine_execution_audit():
    """Fase 5: Execution audit - execution_state distribution, verification stats, gate audit summaries."""
    from brain_v9.trading.paper_execution import read_signal_paper_execution_ledger

    ledger = read_signal_paper_execution_ledger()
    entries = ledger.get("entries", [])

    state_counts: dict = {}
    verification_stats = {"verified_match": 0, "mismatch_detected": 0, "unverified": 0, "no_verification": 0}
    gate_audit_present = 0
    decision_context_present = 0
    total = len(entries)

    for e in entries:
        state = e.get("execution_state", "legacy_no_state")
        state_counts[state] = state_counts.get(state, 0) + 1

        v = e.get("verification")
        if v and isinstance(v, dict):
            vs = v.get("status", "unverified")
            verification_stats[vs] = verification_stats.get(vs, 0) + 1
        else:
            verification_stats["no_verification"] += 1

        if e.get("gate_audit"):
            gate_audit_present += 1
        if e.get("decision_context"):
            decision_context_present += 1

    return {
        "total_entries": total,
        "execution_state_distribution": state_counts,
        "verification_stats": verification_stats,
        "gate_audit_present": gate_audit_present,
        "decision_context_present": decision_context_present,
        "fase5_coverage_pct": round(
            (sum(1 for e in entries if e.get("execution_state")) / max(total, 1)) * 100, 1
        ),
    }


@router.get("/brain/strategy-engine/adaptation-state")
async def brain_strategy_engine_adaptation_state():
    """P-OP23: Current adaptation state - confidence thresholds + signal thresholds per strategy."""
    from brain_v9.core.state_io import read_json
    import brain_v9.config as _c

    return read_json(
        _c.ADAPTATION_HISTORY_PATH,
        {
            "schema_version": "adaptation_snapshot_v1",
            "items": [],
            "adapted_count": 0,
            "total_strategies": 0,
        },
    )


@router.get("/brain/strategy-engine/session-performance")
async def brain_strategy_engine_session_performance():
    """P-OP22/P-OP24: Session performance tracker - per-session win/loss/win_rate."""
    from brain_v9.core.state_io import read_json
    import brain_v9.config as _c

    perf = read_json(_c.SESSION_PERF_PATH, {})
    return {
        "schema_version": "session_performance_v1",
        "mode": _c.SESSION_FILTER_MODE,
        "block_threshold": _c.SESSION_BLOCK_WIN_RATE_THRESHOLD,
        "min_sample_for_block": _c.SESSION_MIN_SAMPLE_FOR_BLOCK,
        "sessions": perf,
        "session_count": len(perf),
        "windows": {
            name: {"quality": w["quality"], "hours_utc": w["hours_utc"], "label": w["label"]}
            for name, w in _c.SESSION_WINDOWS.items()
        },
    }
