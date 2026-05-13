"""
Brain V9 - Action Executor
Cierra el loop: next_action -> job paper -> outcome -> scorecard -> U.
"""
import json
import logging
import random
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from brain_v9.agent.tools import execute_trade_paper
from brain_v9.config import BASE_PATH, PAPER_ONLY, IBKR_HOST, IBKR_PORT, ACTION_COOLDOWN_SECONDS, MAX_LEDGER_ENTRIES
from brain_v9.core.state_io import read_json, write_json, append_to_json_dict_list
from brain_v9.brain.chat_product_governance import refresh_chat_product_status
from brain_v9.brain.post_bl_roadmap import refresh_post_bl_roadmap_status
from brain_v9.brain.utility_governance import refresh_utility_governance_status
from brain_v9.brain.meta_improvement import append_meta_execution, read_meta_improvement_status, refresh_meta_improvement_status
from brain_v9.trading.strategy_engine import (
    execute_candidate_batch,
    execute_comparison_cycle,
    get_recovery_strategy_candidate,
    get_top_strategy_candidate,
    refresh_strategy_engine,
    read_ranking_v2,
)
from brain_v9.trading.strategy_scorecard import force_unfreeze_best_frozen
from brain_v9.brain.auto_surgeon import run_auto_surgeon_cycle

log = logging.getLogger("ActionExecutor")

# ── Platform mapping for PlatformManager ──────────────────────────────────────
# Lane platforms → PlatformManager keys
_LANE_TO_PLATFORM = {
    "pocket_option": "pocket_option",
    "ibkr": "ibkr",
    "internal_paper_simulator": "internal_paper",
    "internal_paper": "internal_paper",
}

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ROOMS_PATH = STATE_PATH / "rooms"
JOBS_PATH = STATE_PATH / "autonomy_action_jobs"
JOBS_LEDGER = STATE_PATH / "autonomy_action_ledger.json"
NEXT_ACTIONS_PATH = STATE_PATH / "autonomy_next_actions.json"
SCORECARD_PATH = ROOMS_PATH / "brain_binary_paper_pb05_journal" / "session_result_scorecard.json"
PO_BRIDGE_ARTIFACT = ROOMS_PATH / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json"
PO_DUE_DILIGENCE_PATH = ROOMS_PATH / "brain_binary_paper_pb01_venue_verification" / "pocketoption_due_diligence.json"
IBKR_LANE_PATH = ROOMS_PATH / "brain_financial_ingestion_fi04_structured_api" / "ibkr_readonly_lane.json"
IBKR_PROBE_PATH = ROOMS_PATH / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json"
IBKR_ORDER_CHECK_PATH = STATE_PATH / "trading_execution_checks" / "ibkr_paper_order_check_latest.json"
TRADING_POLICY_PATH = STATE_PATH / "trading_autonomy_policy.json"

JOBS_PATH.mkdir(parents=True, exist_ok=True)

DEFAULT_SYMBOLS = ["EURUSD_otc", "USDCHF_otc", "GBPUSD_otc"]
SCORECARD_SOURCE = str(SCORECARD_PATH)
UTILITY_SOURCE = str(NEXT_ACTIONS_PATH)
TRADING_AUTONOMY_POLICY = {
    "schema_version": "trading_autonomy_policy_v1",
    "updated_by": "brain_v9.action_executor",
    "global_rules": {
        "paper_only": PAPER_ONLY,
        "live_trading_forbidden": PAPER_ONLY,
        "capital_mutation_forbidden": PAPER_ONLY,
        "credentials_mutation_forbidden": True,
    },
    "platform_rules": {
        "internal_paper_simulator": {
            "paper_allowed": True,
            "live_allowed": not PAPER_ONLY,
            "mode": "paper_only" if PAPER_ONLY else "live",
        },
        "ibkr": {
            "paper_allowed": True,
            "live_allowed": not PAPER_ONLY,
            "mode": "paper_only_until_explicit_upgrade" if PAPER_ONLY else "live",
        },
        "pocket_option": {
            "paper_allowed": True,
            "live_allowed": not PAPER_ONLY,
            "mode": "paper_only" if PAPER_ONLY else "live",
        },
        "quantconnect": {
            "paper_allowed": False,
            "live_allowed": False,
            "mode": "research_only",
        },
    },
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_read_json(path: Path, default):
    """Legacy alias — delegates to unified state_io."""
    return read_json(path, default)


def _safe_write_json(path: Path, payload: Dict):
    """Legacy alias — delegates to unified state_io."""
    write_json(path, payload)


def _ensure_trading_policy():
    _safe_write_json(TRADING_POLICY_PATH, TRADING_AUTONOMY_POLICY)


def _paper_policy_allowed(platform_name: str) -> bool:
    return bool(TRADING_AUTONOMY_POLICY["platform_rules"].get(platform_name, {}).get("paper_allowed"))


def _load_platform_lanes() -> Dict[str, Dict]:
    po_bridge = _safe_read_json(PO_BRIDGE_ARTIFACT, {})
    po_dd = _safe_read_json(PO_DUE_DILIGENCE_PATH, {})
    ibkr_lane = _safe_read_json(IBKR_LANE_PATH, {})
    ibkr_probe = _safe_read_json(IBKR_PROBE_PATH, {})
    ibkr_order_check = _safe_read_json(IBKR_ORDER_CHECK_PATH, {})
    ibkr_port_open = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        ibkr_port_open = sock.connect_ex((IBKR_HOST, IBKR_PORT)) == 0
        sock.close()
    except Exception as exc:
        log.debug("IBKR socket probe failed: %s", exc)
        ibkr_port_open = False
    ibkr_market_data_ready = ibkr_port_open and bool(ibkr_probe.get("connected"))
    ibkr_order_ready = bool(ibkr_order_check.get("order_api_ready"))
    po_symbols = []
    for symbol in po_bridge.get("symbols", []):
        normalized = symbol.replace("/", "").replace(" OTC", "_otc").replace(" ", "")
        if normalized:
            po_symbols.append(normalized)
    current_symbol = po_bridge.get("current", {}).get("symbol")
    if current_symbol and current_symbol not in po_symbols:
        po_symbols.insert(0, current_symbol)
    return {
        "internal_paper_simulator": {
            "eligible": _paper_policy_allowed("internal_paper_simulator"),
            "platform": "internal_paper_simulator",
            "venue": "brain_v9_paper_lane",
            "status": "available",
            "symbols_universe": DEFAULT_SYMBOLS,
            "reason": "fallback_safe_internal_lane",
        },
        "ibkr": {
            "eligible": _paper_policy_allowed("ibkr") and ibkr_market_data_ready,
            "platform": "ibkr",
            "venue": "ibkr_paper_candidate",
            "status": "paper_order_ready" if ibkr_order_ready else ("market_data_ready" if ibkr_market_data_ready else "not_ready"),
            "symbols_universe": ["SPY", "QQQ", "AAPL"],
            "reason": (
                "paper_order_lane_ready"
                if ibkr_order_ready else
                "paper_shadow_only_market_data_ready"
                if ibkr_market_data_ready else
                "gateway_socket_unavailable"
            ),
            "mode": ibkr_lane.get("mode", "read_only_first"),
        },
        "pocket_option": {
            "eligible": _paper_policy_allowed("pocket_option") and bool(po_bridge.get("current")),
            "platform": "pocket_option",
            "venue": "browser_bridge_demo",
            "status": "demo_feed_seen" if po_bridge.get("current") else "not_ready",
            "symbols_universe": po_symbols[:24] or DEFAULT_SYMBOLS,
            "reason": "paper_only_policy_with_edge_extension_bridge",
            "classification": po_dd.get("brain_decision", {}).get("venue_classification"),
        },
    }


def _select_execution_lane() -> Dict:
    lanes = _load_platform_lanes()
    # Prefer real execution lanes if eligible
    if lanes["ibkr"]["eligible"] and lanes["ibkr"]["status"] == "paper_order_ready":
        selected = lanes["ibkr"].copy()
        selected["selection_reason"] = "IBKR paper order ready, enabling real execution."
    elif lanes["pocket_option"]["eligible"]:
        selected = lanes["pocket_option"].copy()
        selected["selection_reason"] = "PO eligible, enabling real execution."
    else:
        selected = lanes["internal_paper_simulator"].copy()
        selected["selection_reason"] = "No real lanes eligible, using internal simulator."
    return {"selected": selected, "candidates": lanes}


def _load_scorecard() -> Dict:
    return _safe_read_json(SCORECARD_PATH, {
        "schema_version": "session_result_scorecard_v1",
        "phase": "PB-05",
        "room_id": "brain_binary_paper_pb05_journal",
        "status": "empirical_outcomes_available",
        "seed_metrics": {
            "entries_taken": 0,
            "entries_resolved": 0,
            "entries_unresolved": 0,
            "valid_candidates_skipped": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "gross_units": 0,
            "net_units": 0,
            "net_expectancy_after_payout": 0.0,
            "max_drawdown": 0.0,
            "largest_loss_streak": 0,
        },
        "entry_outcome_counts": {},
        "strategy_performance_seed": {},
        "pair_performance_seed": {},
        "pair_breakdown_seed": {},
    })


def _save_scorecard(scorecard: Dict):
    seed = scorecard.setdefault("seed_metrics", {})
    entries_resolved = int(seed.get("entries_resolved", 0) or 0)
    net_units = float(seed.get("net_units", 0.0) or 0.0)
    seed["net_expectancy_after_payout"] = round(net_units / entries_resolved, 4) if entries_resolved else 0.0
    scorecard["updated_utc"] = _now_utc()
    _safe_write_json(SCORECARD_PATH, scorecard)



def _append_ledger(entry: Dict):
    ledger = _safe_read_json(JOBS_LEDGER, {"schema_version": "autonomy_action_ledger_v1", "entries": []})
    entries = ledger.get("entries", [])
    entries.append(entry)
    # Prune if over limit — keep most recent half
    if len(entries) > MAX_LEDGER_ENTRIES:
        entries = entries[-(MAX_LEDGER_ENTRIES // 2):]
        log.info("Ledger pruned from %d to %d entries", len(ledger.get("entries", [])), len(entries))
    ledger["entries"] = entries
    ledger["updated_utc"] = entry["updated_utc"]
    _safe_write_json(JOBS_LEDGER, ledger)


def _latest_job_for_action(action_name: str) -> Dict | None:
    ledger = _safe_read_json(JOBS_LEDGER, {"entries": []})
    for entry in reversed(ledger.get("entries", [])):
        if entry.get("action_name") == action_name:
            return entry
    return None


def _cooldown_active(action_name: str) -> bool:
    latest = _latest_job_for_action(action_name)
    if not latest:
        return False
    if latest.get("status") not in {"completed"}:
        return False
    try:
        last_dt = datetime.fromisoformat(latest["updated_utc"].replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        return (now_dt - last_dt).total_seconds() < ACTION_COOLDOWN_SECONDS
    except Exception as exc:
        log.debug("Cooldown timestamp parse failed for %s: %s", action_name, exc)
        return False


def _update_scorecard_with_trade(scorecard: Dict, trade: Dict, strategy_tag: str, platform: str = "internal_paper"):
    seed = scorecard.setdefault("seed_metrics", {})
    seed["entries_taken"] = int(seed.get("entries_taken", 0) or 0) + 1
    seed["entries_resolved"] = int(seed.get("entries_resolved", 0) or 0) + 1
    seed["wins"] = int(seed.get("wins", 0) or 0) + (1 if trade["result"] == "win" else 0)
    seed["losses"] = int(seed.get("losses", 0) or 0) + (1 if trade["result"] == "loss" else 0)
    seed["gross_units"] = round(float(seed.get("gross_units", 0.0) or 0.0) + float(trade["profit"]), 4)
    seed["net_units"] = round(float(seed.get("net_units", 0.0) or 0.0) + float(trade["profit"]), 4)

    # Note: valid_candidates_skipped is now managed by util.py as the single
    # source of truth.  reset_skips_counter() syncs both counters on trade.

    pair_key = trade["symbol"].replace("_otc", "")
    pair_seed = scorecard.setdefault("pair_breakdown_seed", {})
    pair_seed[pair_key] = int(pair_seed.get(pair_key, 0) or 0) + 1

    outcomes = scorecard.setdefault("entry_outcome_counts", {})
    outcomes[trade["result"]] = int(outcomes.get(trade["result"], 0) or 0) + 1

    strategy_perf = scorecard.setdefault("strategy_performance_seed", {})
    strategy_perf[strategy_tag] = round(float(strategy_perf.get(strategy_tag, 0.0) or 0.0) + float(trade["profit"]), 4)

    pair_perf = scorecard.setdefault("pair_performance_seed", {})
    pair_perf[pair_key] = round(float(pair_perf.get(pair_key, 0.0) or 0.0) + float(trade["profit"]), 4)

    # NOTE: Platform metrics are recorded when the trade resolves
    # via _update_platform_metrics() in paper_execution.py.
    # Recording here with pending_resolution/profit=0 would
    # double-count once the trade resolves.


async def run_paper_trades() -> Dict:
    """
    Ejecuta trades paper integrado al flujo oficial de meta-mejora.
    Selecciona la primera estrategia del ranking que tenga execution_ready=True.
    """
    _ensure_trading_policy()
    lane_info = _select_execution_lane()
    refresh_strategy_engine()
    
    # Obtener ranking completo
    ranking = read_ranking_v2()
    ranked = ranking.get('ranked', [])
    
    # Buscar la primera estrategia que esté lista para ejecutar
    # P-OP16: Check execution_ready_now (set by strategy_selector for probation
    # candidates) in addition to execution_ready.  The old code only checked
    # execution_ready, which is False for probation candidates that have
    # execution_ready_now=True.
    top_candidate = None
    for strategy in ranked:
        is_ready = strategy.get('execution_ready') or strategy.get('execution_ready_now')
        if is_ready and strategy.get('venue_ready'):
            # Verificar que no esté frozen
            if strategy.get('promotion_state') not in ['frozen', 'archived']:
                top_candidate = strategy
                break
    
    # P-OP17: If no ready candidate in ranked list, check probation_candidate
    # from the ranking payload.  The old fallback used get_top_strategy_candidate()
    # which only returns leadership-eligible strategies, not probation candidates.
    if not top_candidate:
        prob_candidate = ranking.get('probation_candidate')
        if prob_candidate and (prob_candidate.get('execution_ready_now') or prob_candidate.get('execution_ready')):
            top_candidate = prob_candidate

    # P-OP27: When no execution_ready candidate exists, pick the best
    # venue_ready strategy that still needs samples.  Paper-trading for
    # sample expansion should not be blocked just because the signal
    # engine hasn't flagged the signal as "execution_ready" — price_available
    # plus venue_ready is sufficient for paper exploration.
    if not top_candidate:
        for strategy in ranked:
            if strategy.get('venue_ready') and strategy.get('promotion_state') not in ['frozen', 'archived']:
                sq = float(strategy.get('sample_quality', 0) or 0)
                csq = float(strategy.get('context_sample_quality', 0) or 0)
                if max(sq, csq) < 0.55:
                    top_candidate = strategy
                    break

    # P-OP31: Internal paper fallback for operational candidates whose venue
    # is not marked ready (e.g., quantconnect imports executed via simulator).
    if not top_candidate:
        for strategy in ranked:
            if strategy.get('promotion_state') in ['frozen', 'archived']:
                continue
            if str(strategy.get("catalog_state") or "") in {"active", "probation"}:
                top_candidate = strategy
                break

    if not top_candidate:
        top_candidate = get_top_strategy_candidate() or {}
    
    strategy_id = top_candidate.get("strategy_id")
    preferred_symbol = top_candidate.get("preferred_symbol") or top_candidate.get("best_symbol")
    venue = top_candidate.get("venue", "internal_paper_simulator")
    
    import logging as _log_mod
    _ae_log = _log_mod.getLogger("ActionExecutor")
    _ae_log.info(
        f"run_paper_trades: candidate={strategy_id} symbol={preferred_symbol} "
        f"venue={venue} exec_ready={top_candidate.get('execution_ready')} "
        f"exec_ready_now={top_candidate.get('execution_ready_now')} "
        f"venue_ready={top_candidate.get('venue_ready')}"
    )
    
    # Verificar si hay señales válidas disponibles
    signal_plan = None
    if strategy_id:
        # Buscar señal válida en el snapshot de señales
        from brain_v9.trading.strategy_engine import read_signal_snapshot
        signal_snapshot = read_signal_snapshot()
        for item in signal_snapshot.get('items', []):
            if (item.get('strategy_id') == strategy_id and 
                item.get('symbol') == preferred_symbol and
                item.get('signal_valid') and 
                item.get('execution_ready')):
                signal_plan = item
                break
        # P-OP27: Relaxed match — accept any signal for this strategy+symbol
        # that has price data, even if signal_valid/execution_ready are False.
        # This enables sample expansion when the signal engine is too strict
        # (e.g. timeframe_not_supported blocker for PO bridge data at 1m).
        if not signal_plan:
            for item in signal_snapshot.get('items', []):
                if (item.get('strategy_id') == strategy_id and
                    item.get('symbol') == preferred_symbol and
                    item.get('price_available')):
                    signal_plan = item
                    break
    
    # Calcular métricas de calidad
    sample_quality = float(top_candidate.get("sample_quality", 0.0) or 0.0)
    context_sample_quality = float(top_candidate.get("context_sample_quality", 0.0) or 0.0)
    best_sample_quality = max(sample_quality, context_sample_quality)
    
    _ae_log.info(
        f"run_paper_trades: signal_plan={'found' if signal_plan else 'None'} "
        f"signal_price_avail={signal_plan.get('price_available') if signal_plan else 'N/A'} "
        f"best_sq={best_sample_quality:.2f} venue_ready={top_candidate.get('venue_ready')}"
    )
    
    # Decidir si ejecutar basado en meta-mejora
    should_execute = False
    execution_reason = ""
    current_skips = 0
    
    if strategy_id and (top_candidate.get("execution_ready") or top_candidate.get("execution_ready_now")):
        if signal_plan and signal_plan.get("execution_ready"):
            # Hay señal válida del mercado
            should_execute = True
            execution_reason = f"Signal valid for {preferred_symbol}: {signal_plan.get('direction')} (conf: {signal_plan.get('confidence')})"
        elif best_sample_quality < 0.55:
            # Necesita más muestras (reducido de 0.85 a 0.55)
            should_execute = True
            execution_reason = f"Sample quality {best_sample_quality:.2f} < 0.55, needs expansion"
    
    # P-OP27: Sample expansion path — when the strategy is NOT execution_ready
    # (e.g. PO signal with timeframe blocker) but we have a signal with
    # price_available and the strategy still needs samples, allow execution.
    # This is the primary fix for PO trades being blocked.
    if not should_execute and strategy_id and signal_plan and signal_plan.get("price_available"):
        catalog_operational = str(top_candidate.get("catalog_state") or "") in {"active", "probation"}
        if best_sample_quality < 0.55 and (top_candidate.get("venue_ready") or catalog_operational):
            should_execute = True
            execution_reason = (
                f"P-OP27 sample expansion: {preferred_symbol} price available, "
                f"sample_quality {best_sample_quality:.2f} < 0.55, venue_ready"
            )

    # P-OP31: If we still have no executable signal but the candidate is
    # operational and under-sampled, execute a directed paper batch in the
    # internal simulator to generate evidence.
    if not should_execute and strategy_id and best_sample_quality < 0.55:
        if str(top_candidate.get("catalog_state") or "") in {"active", "probation"}:
            should_execute = True
            execution_reason = (
                f"P-OP31 fallback sample expansion: {strategy_id} operational, "
                f"sample_quality {best_sample_quality:.2f} < 0.55"
            )

    if strategy_id:
        # Forzar ejecución después de 3 'skipped' consecutivos
        from brain_v9.util import get_consecutive_skips
        current_skips = get_consecutive_skips()
        if current_skips >= 3:
            should_execute = True
            execution_reason = f"Forzando ejecución por {current_skips} skips consecutivos"
    
    # Imports de utilidades
    from brain_v9.util import increment_skips_counter, reset_skips_counter
    from brain_v9.trading.utility_util import update_u_history
    
    # Si no hay candidato o no hay ejecución, registrar skip
    if not should_execute or not strategy_id:
        increment_skips_counter(reason=f"No execution: {execution_reason or 'No valid candidate'}")
        update_u_history(u_proxy_score=0.0, reason=f"Skip: {execution_reason or 'No valid candidate'}")
        
        return {
            "success": False,
            "action_name": "increase_resolved_sample",
            "mode": "paper_only",
            "execution_reason": execution_reason or "No valid strategy candidate found",
            "skip_reason": "No execution conditions met",
            "strategy_id": strategy_id,
            "sample_quality": best_sample_quality,
            "consecutive_skips": current_skips + 1,
        }
    
    # Seleccionar lane según venue de la estrategia
    lanes = lane_info["candidates"]
    # P-OP18: Use lane_info["selected"] as fallback instead of lanes["selected"]
    # which doesn't exist (lanes only has internal_paper_simulator/ibkr/pocket_option).
    # Python eagerly evaluates the default arg, so lanes["selected"] always threw KeyError.
    selected_lane = lanes.get("internal_paper_simulator", lane_info["selected"]).copy()
    
    if venue == "pocket_option" and lanes.get("pocket_option", {}).get("eligible"):
        selected_lane = lanes["pocket_option"].copy()
        selected_lane["selection_reason"] = "Strategy requires PO venue with valid signal"
    elif venue == "ibkr" and lanes.get("ibkr", {}).get("eligible"):
        if lanes["ibkr"].get("status") == "paper_order_ready":
            selected_lane = lanes["ibkr"].copy()
            selected_lane["selection_reason"] = "Strategy requires IBKR venue with order API ready"
        else:
            selected_lane["selection_reason"] = f"IBKR not ready: {lanes['ibkr'].get('status')}, using internal simulator"
    
    # Ejecutar batch con la estrategia seleccionada
    directed_iterations = max(1, min(3, int(top_candidate.get("recommended_iterations") or 1)))
    strategy_exec = await execute_candidate_batch(strategy_id, directed_iterations, allow_frozen=False)
    
    # Procesar resultados
    batch_artifact = _safe_read_json(Path(strategy_exec.get("artifact", "")), {}) if strategy_exec.get("artifact") else {}
    batch_results = batch_artifact.get("results", [])
    trades = []
    scorecard = _load_scorecard()
    
    for item in batch_results:
        trade = (item or {}).get("trade")
        if not trade:
            continue
        trade["executor_action"] = "increase_resolved_sample"
        trade["meta_improvement_gap"] = "strategy_sample_depth"
        trades.append(trade)
        _update_scorecard_with_trade(scorecard, trade, strategy_id, platform=selected_lane.get("platform", "internal_paper_simulator"))
    
    # Guardar scorecard
    if trades:
        notes = scorecard.setdefault("autonomy_strategy_notes", [])
        notes.append({
            "timestamp": _now_utc(),
            "action": "increase_resolved_sample",
            "result": "directed_candidate_sampling",
            "detail": f"Meta-improvement execution on {strategy_id}. {execution_reason}. Lane: {selected_lane.get('platform')}. Trades: {len(trades)}",
        })
        _save_scorecard(scorecard)
    
    # Actualizar historial de U con resultado real
    u_score = 0.0
    if trades:
        from brain_v9.brain.utility_governance import read_utility_governance_status
        status = read_utility_governance_status()
        u_score = status.get("u_proxy_score", 0.0)
    
    update_u_history(
        u_proxy_score=u_score,
        reason=f"Ejecutado: {execution_reason}",
        trades_count=len(trades),
        additional_data={
            "strategy_id": strategy_id,
            "sample_quality": best_sample_quality,
            "signal_plan": bool(signal_plan)
        }
    )
    
    # Resetear contador de skips después de ejecución exitosa
    reset_skips_counter()
    
    return {
        "success": bool(strategy_exec.get("success")),
        "action_name": "increase_resolved_sample",
        "mode": "paper_only",
        "platform": selected_lane["platform"],
        "venue": top_candidate.get("venue", selected_lane["venue"]),
        "strategy_tag": strategy_id,
        "strategy_family": top_candidate.get("family", "strategy_engine_candidate"),
        "sampling_mode": "meta_improvement_directed" if signal_plan else "sample_expansion",
        "selection_mode": top_candidate.get("selection_mode"),
        "execution_reason": execution_reason,
        "data_inputs": [UTILITY_SOURCE, SCORECARD_SOURCE],
        "symbols_universe": top_candidate.get("universe", []) or DEFAULT_SYMBOLS,
        "preferred_symbol": preferred_symbol,
        "recommended_iterations": directed_iterations,
        "preferred_timeframe": top_candidate.get("preferred_timeframe"),
        "preferred_setup_variant": top_candidate.get("preferred_setup_variant"),
        "eligible_paper_lanes": lane_info["candidates"],
        "selected_lane": selected_lane,
        "paper_only_enforced": True,
        "meta_improvement": {
            "gap_id": "strategy_sample_depth",
            "execution_mode": "internal_candidate",
            "evidence_generated": bool(trades),
        },
        "operational_tasks": [
            "select_executable_leader",
            "expand_resolved_sample",
            "update_strategy_scorecard",
            "feed_utility_u",
            "append_meta_execution",
        ],
        "trades_executed": len(trades),
        "trades": trades,
        "batch_run": strategy_exec,
        "scorecard_path": str(SCORECARD_PATH),
    }


async def expand_signal_pipeline() -> Dict:
    """Actively expand the signal pipeline to reduce skip pressure.

    When the blocker ``signal_pipeline_underpowered`` fires (skips > 2x
    resolved trades), the autonomy loop calls this action.  The concrete
    steps are:

    1. Refresh feature & signal snapshots to get the freshest market data.
    2. Temporarily widen filter tolerances (``spread_pct_max`` +30 %,
       ``confidence_threshold`` lowered to 0.35, ``market_regime_allowed``
       extended with ``range`` and ``mild``) on *all* strategies that
       are not frozen, so signals that were marginally rejected can pass.
    3. Scan for the best executable signal across every strategy.
    4. If a viable signal is found, execute a paper trade to reduce the
       skip/resolved ratio.
    5. Restore the original filter values so persistent state is not
       corrupted.
    6. Decrement the skip counter regardless (to avoid runaway pressure).
    """
    _ensure_trading_policy()
    lane_info = _select_execution_lane()
    selected = lane_info["selected"]

    # --- 1. Refresh strategy engine (features + signals) ---------------
    refresh_strategy_engine()
    ranking = read_ranking_v2()
    ranked = ranking.get("ranked", [])

    # --- 2. Temporarily widen filters ----------------------------------
    from brain_v9.trading.strategy_engine import (
        _normalize_strategy_specs,
        read_signal_snapshot,
    )
    from brain_v9.trading.signal_engine import (
        build_strategy_signal_snapshot,
    )
    from brain_v9.trading.feature_engine import read_market_feature_snapshot

    specs = _normalize_strategy_specs()
    strategies = specs.get("strategies", [])
    originals: Dict[str, Dict] = {}  # strategy_id -> original values

    for strategy in strategies:
        sid = strategy.get("strategy_id", "")
        # Skip frozen / archived
        matching = next((r for r in ranked if r.get("strategy_id") == sid), None)
        if matching and (matching.get("governance_state") == "frozen" or
                         str(matching.get("archive_state") or "").startswith("archived")):
            continue

        filters = strategy.get("filters") or {}
        originals[sid] = {
            "confidence_threshold": strategy.get("confidence_threshold", 0.58),
            "spread_pct_max": filters.get("spread_pct_max"),
            "market_regime_allowed": list(filters.get("market_regime_allowed") or []),
        }
        # Lower confidence threshold to the floor (BASE - 0.10 = 0.48)
        strategy["confidence_threshold"] = 0.48
        # Widen spread filter by 30 %
        if filters.get("spread_pct_max") is not None:
            base_spread = float(filters["spread_pct_max"])
            if base_spread > 0:
                filters["spread_pct_max"] = round(base_spread * 1.30, 4)
        # Widen regime filter — add 'range' and 'mild' which are the most
        # common PO regimes and frequently the #1 signal blocker.
        regime_list = filters.get("market_regime_allowed")
        if regime_list is not None and isinstance(regime_list, list):
            for fallback_regime in ("range", "mild"):
                if fallback_regime not in regime_list:
                    regime_list.append(fallback_regime)

    # --- 3. Re-evaluate signals with widened filters -------------------
    feature_snapshot = read_market_feature_snapshot()
    widened_signal_snapshot = build_strategy_signal_snapshot(strategies, feature_snapshot)

    # Find best executable signal across all strategies
    best_signal_item = None
    best_strategy = None
    for by_strat in widened_signal_snapshot.get("by_strategy", []):
        bs = by_strat.get("best_signal") or {}
        if bs.get("execution_ready"):
            if best_signal_item is None or (bs.get("confidence", 0) > best_signal_item.get("confidence", 0)):
                best_signal_item = bs
                best_strategy = next(
                    (s for s in strategies if s.get("strategy_id") == by_strat.get("strategy_id")),
                    None,
                )

    # --- 4. Execute a paper trade if viable signal found ---------------
    trade = None
    trade_result: Dict = {}
    if best_signal_item and best_strategy:
        from brain_v9.trading.strategy_engine import execute_candidate_batch
        strategy_id = best_strategy["strategy_id"]
        trade_result = await execute_candidate_batch(strategy_id, 1, allow_frozen=False)
        batch_artifact = _safe_read_json(
            Path(trade_result.get("artifact", "")), {},
        ) if trade_result.get("artifact") else {}
        batch_results = batch_artifact.get("results", [])
        if batch_results:
            trade = (batch_results[0] or {}).get("trade")

        # Update scorecard if trade executed
        if trade:
            scorecard = _load_scorecard()
            _update_scorecard_with_trade(scorecard, trade, strategy_id, platform="internal_paper_simulator")
            notes = scorecard.setdefault("autonomy_pipeline_notes", [])
            notes.append({
                "timestamp": _now_utc(),
                "action": "expand_signal_pipeline",
                "result": "pipeline_expanded_trade_executed",
                "detail": (
                    f"Widened filters found executable signal for {strategy_id} "
                    f"on {trade.get('symbol')}. Confidence: {best_signal_item.get('confidence')}. "
                    f"Result: {trade.get('result')}."
                ),
            })
            if len(notes) > 100:
                scorecard["autonomy_pipeline_notes"] = notes[-50:]
            _save_scorecard(scorecard)

    # --- 5. Restore original filter values -----------------------------
    for strategy in strategies:
        sid = strategy.get("strategy_id", "")
        if sid in originals:
            strategy["confidence_threshold"] = originals[sid]["confidence_threshold"]
            filters = strategy.get("filters") or {}
            if originals[sid]["spread_pct_max"] is not None:
                filters["spread_pct_max"] = originals[sid]["spread_pct_max"]
            # Restore original regime list
            original_regimes = originals[sid].get("market_regime_allowed")
            if original_regimes is not None:
                filters["market_regime_allowed"] = original_regimes

    # --- 6. Decrement skip counter regardless --------------------------
    from brain_v9.util import get_consecutive_skips, reset_skips_counter
    current_skips = get_consecutive_skips()
    actually_reduced = False
    if current_skips > 0:
        # Reset counter via util.py (single source of truth); this also
        # syncs the scorecard's valid_candidates_skipped to 0.
        reset_skips_counter()
        actually_reduced = True

    scorecard = _load_scorecard()
    seed = scorecard.setdefault("seed_metrics", {})

    if not trade:
        notes = scorecard.setdefault("autonomy_pipeline_notes", [])
        notes.append({
            "timestamp": _now_utc(),
            "action": "expand_signal_pipeline",
            "result": "no_viable_signal" if not best_signal_item else "trade_failed",
            "detail": (
                f"Widened filters but no executable signal found across "
                f"{len(strategies)} strategies. Skip counter: {current_skips} -> 0."
            ),
        })
        if len(notes) > 100:
            scorecard["autonomy_pipeline_notes"] = notes[-50:]

    _save_scorecard(scorecard)

    return {
        "success": bool(trade),
        "action_name": "improve_signal_capture_and_context_window",
        "mode": "paper_only",
        "platform": selected["platform"],
        "venue": selected["venue"],
        "strategy_tag": best_strategy["strategy_id"] if best_strategy else "AUTO-CONTEXT",
        "strategy_family": best_strategy.get("family") if best_strategy else "signal_capture_probe",
        "data_inputs": [UTILITY_SOURCE, SCORECARD_SOURCE],
        "symbols_universe": DEFAULT_SYMBOLS,
        "eligible_paper_lanes": lane_info["candidates"],
        "selected_lane": selected,
        "paper_only_enforced": True,
        "operational_tasks": [
            "refresh_feature_snapshot",
            "widen_filters_temporarily",
            "widen_regime_filters_temporarily",
            "scan_all_strategies_for_signal",
            "execute_paper_trade_if_viable",
            "restore_original_filters",
            "reduce_skip_pressure",
        ],
        "reduced_skips_to": 0 if actually_reduced else current_skips,
        "filter_widening_applied": len(originals),
        "viable_signal_found": best_signal_item is not None,
        "trade_executed": trade is not None,
        "trade": trade,
        "batch_run": trade_result if trade_result else None,
        "scorecard_path": str(SCORECARD_PATH),
    }


async def adjust_strategy_params() -> Dict:
    _ensure_trading_policy()
    lane_info = _select_execution_lane()
    refresh_strategy_engine()
    top_candidate = get_top_strategy_candidate() or get_recovery_strategy_candidate() or {}
    strategy_id = top_candidate.get("strategy_id")
    preferred_symbol = top_candidate.get("preferred_symbol") or top_candidate.get("best_symbol")
    recommended_iterations = int(top_candidate.get("recommended_iterations") or 1)
    allow_frozen_execution = bool(top_candidate.get("allow_frozen_execution"))
    if not strategy_id:
        comparison_fallback = await execute_comparison_cycle(max_candidates=2)
        top_after = comparison_fallback.get("top_strategy_after") or {}
        return {
            "success": bool(comparison_fallback.get("success")),
            "action_name": "improve_expectancy_or_reduce_penalties",
            "mode": "paper_only",
            "platform": "strategy_engine_comparison_cycle",
            "venue": top_after.get("venue"),
            "strategy_tag": top_after.get("strategy_id") or "AUTO-EXPECTANCY",
            "strategy_family": top_after.get("family", "strategy_engine_candidate"),
            "selection_mode": "fallback_comparison_cycle",
            "fallback_action": "select_and_compare_strategies",
            "data_inputs": [
                str(NEXT_ACTIONS_PATH),
                str(STATE_PATH / "strategy_engine" / "strategy_scorecards.json"),
            ],
            "symbols_universe": top_after.get("universe", []),
            "preferred_symbol": top_after.get("preferred_symbol"),
            "recommended_iterations": top_after.get("recommended_iterations"),
            "preferred_timeframe": top_after.get("preferred_timeframe"),
            "preferred_setup_variant": top_after.get("preferred_setup_variant"),
            "allow_frozen_execution": True,
            "eligible_paper_lanes": lane_info["candidates"],
            "selected_lane": lane_info["selected"],
            "paper_only_enforced": True,
            "operational_tasks": [
                "detect_missing_executable_candidate",
                "fallback_to_comparison_cycle",
                "rebuild_strategy_ranking",
                "feed_utility_u",
            ],
            "trade": None,
            "batch_run": None,
            "strategy_execution": {"success": False, "error": "no_top_strategy"},
            "comparison_cycle": comparison_fallback,
            "scorecard_path": str(SCORECARD_PATH),
        }
    strategy_exec = (
        await execute_candidate_batch(strategy_id, recommended_iterations, allow_frozen=allow_frozen_execution)
        if strategy_id else
        {"success": False, "error": "no_top_strategy"}
    )

    batch_artifact = _safe_read_json(Path(strategy_exec.get("artifact", "")), {}) if strategy_exec.get("artifact") else {}
    batch_results = batch_artifact.get("results", [])
    last_execution = batch_results[-1] if batch_results else {}
    trade = (last_execution or {}).get("trade")
    selected = (last_execution or {}).get("selected_lane") or lane_info["selected"]
    symbols_universe = (last_execution or {}).get("symbols_universe") or selected.get("symbols_universe") or DEFAULT_SYMBOLS
    data_inputs = (last_execution or {}).get("data_inputs") or [UTILITY_SOURCE, SCORECARD_SOURCE]

    # Mantener el scorecard global mientras Strategy Engine V1 madura.
    if trade:
        scorecard = _load_scorecard()
        trade["executor_action"] = "improve_expectancy_or_reduce_penalties"
        _update_scorecard_with_trade(scorecard, trade, strategy_id or "AUTO-EXPECTANCY", platform=selected.get("platform", "internal_paper_simulator"))
        notes = scorecard.setdefault("autonomy_strategy_notes", [])
        notes.append({
            "timestamp": _now_utc(),
            "action": "improve_expectancy_or_reduce_penalties",
            "result": top_candidate.get("selection_mode", "strategy_engine_top_candidate"),
            "detail": f"Autonomy executor ran {top_candidate.get('selection_mode', 'top strategy candidate')} {strategy_id} in paper mode with preferred_symbol={preferred_symbol} iterations={recommended_iterations}.",
        })
        _save_scorecard(scorecard)

    return {
        "success": bool(strategy_exec.get("success")),
        "action_name": "improve_expectancy_or_reduce_penalties",
        "mode": "paper_only",
        "platform": selected["platform"],
        "venue": top_candidate.get("venue", selected["venue"]),
        "strategy_tag": strategy_id or "AUTO-EXPECTANCY",
        "strategy_family": top_candidate.get("family", "strategy_engine_candidate"),
        "selection_mode": top_candidate.get("selection_mode"),
        "data_inputs": data_inputs,
        "symbols_universe": symbols_universe,
        "preferred_symbol": preferred_symbol,
        "recommended_iterations": recommended_iterations,
        "preferred_timeframe": top_candidate.get("preferred_timeframe"),
        "preferred_setup_variant": top_candidate.get("preferred_setup_variant"),
        "allow_frozen_execution": allow_frozen_execution,
        "eligible_paper_lanes": lane_info["candidates"],
        "selected_lane": selected,
        "paper_only_enforced": True,
        "operational_tasks": [
            "select_top_strategy_candidate",
            "execute_strategy_batch",
            "update_strategy_scorecard",
            "feed_utility_u",
        ],
        "trade": trade,
        "batch_run": strategy_exec,
        "strategy_execution": strategy_exec,
        "scorecard_path": str(SCORECARD_PATH),
    }


async def select_and_compare_strategies() -> Dict:
    _ensure_trading_policy()
    refresh_strategy_engine()
    comparison = await execute_comparison_cycle(max_candidates=2)
    top_after = comparison.get("top_strategy_after") or {}
    return {
        "success": bool(comparison.get("success")),
        "action_name": "select_and_compare_strategies",
        "mode": "paper_only",
        "platform": "strategy_engine_comparison_cycle",
        "venue": top_after.get("venue"),
        "strategy_tag": top_after.get("strategy_id"),
        "strategy_family": top_after.get("family"),
        "paper_only_enforced": True,
        "operational_tasks": [
            "refresh_strategy_engine",
            "compare_top_candidates",
            "execute_batch_runs",
            "rebuild_ranking",
            "feed_utility_u",
        ],
        "comparison_cycle": comparison,
        "preferred_symbol": top_after.get("preferred_symbol"),
        "recommended_iterations": top_after.get("recommended_iterations"),
        "preferred_timeframe": top_after.get("preferred_timeframe"),
        "preferred_setup_variant": top_after.get("preferred_setup_variant"),
        "data_inputs": [
            str(NEXT_ACTIONS_PATH),
            str(STATE_PATH / "strategy_engine" / "strategy_scorecards.json"),
        ],
        "symbols_universe": top_after.get("universe", []),
    }


async def advance_meta_improvement_roadmap() -> Dict:
    status = refresh_meta_improvement_status()
    top_gap = status.get("top_gap") or {}
    roadmap = status.get("roadmap", {})
    top_item = roadmap.get("top_item") or {}
    execution_mode = top_gap.get("execution_mode")
    delegated_action = None
    delegated_result: Dict[str, object] = {}
    selected_playbooks = list(top_gap.get("selected_playbooks", []))
    method_reason = top_gap.get("method_selection_reason") or top_item.get("method_selection_reason")

    if not top_gap:
        entry = {
            "updated_utc": _now_utc(),
            "gap_id": None,
            "status": "observe_only",
            "detail": "No hay gaps abiertos de alta prioridad.",
        }
        append_meta_execution(entry)
        return {
            "success": True,
            "action_name": "advance_meta_improvement_roadmap",
            "mode": "meta_governance",
            "platform": "meta_improvement_engine",
            "venue": "brain_internal",
            "paper_only_enforced": True,
            "operational_tasks": ["refresh_meta_improvement_status", "observe"],
            "meta_status": status,
            "top_gap": None,
            "execution_mode": "observe_only",
        }

    if execution_mode == "internal_candidate":
        preferred_method = top_item.get("recommended_method") or top_gap.get("recommended_method")
        if preferred_method in ACTION_MAP and preferred_method != "advance_meta_improvement_roadmap":
            delegated_action = preferred_method
        for candidate in top_gap.get("suggested_actions", []):
            if delegated_action:
                break
            if candidate in ACTION_MAP and candidate != "advance_meta_improvement_roadmap":
                delegated_action = candidate
                break
        if delegated_action:
            delegated_result = await ACTION_MAP[delegated_action]()

    refreshed_status = refresh_meta_improvement_status()
    refresh_post_bl_roadmap_status()
    result_status = "completed" if delegated_action and delegated_result.get("success") else (
        "needs_meta_brain" if execution_mode == "needs_meta_brain" or not delegated_action else "partial"
    )
    ledger_entry = {
        "updated_utc": _now_utc(),
        "gap_id": top_gap.get("gap_id"),
        "title": top_gap.get("title"),
        "status": result_status,
        "execution_mode": execution_mode,
        "delegated_action": delegated_action,
        "delegated_success": delegated_result.get("success"),
        "delegated_platform": delegated_result.get("platform"),
        "delegated_venue": delegated_result.get("venue"),
        "delegated_strategy_tag": delegated_result.get("strategy_tag"),
        "delegated_total_profit": (
            delegated_result.get("batch_run", {}).get("total_profit")
            if isinstance(delegated_result.get("batch_run"), dict)
            else delegated_result.get("trade", {}).get("profit")
        ),
        "priority_score": top_gap.get("priority_score"),
        "objective": top_gap.get("objective"),
        "selected_playbooks": selected_playbooks,
        "method_selection_reason": method_reason,
        "handoff": refreshed_status.get("meta_brain_handoff"),
    }
    append_meta_execution(ledger_entry)
    refreshed_status = refresh_meta_improvement_status()
    return {
        "success": bool(delegated_result.get("success")) if delegated_action else False,
        "action_name": "advance_meta_improvement_roadmap",
        "mode": "meta_governance",
        "platform": "meta_improvement_engine",
        "venue": "brain_internal",
        "paper_only_enforced": True,
        "operational_tasks": [
            "inspect_domains",
            "prioritize_gaps",
            "refresh_meta_roadmap",
            "delegate_internal_action" if delegated_action else "prepare_meta_handoff",
            "persist_memory",
        ],
        "roadmap_status": roadmap.get("work_status"),
        "top_gap": top_gap,
        "execution_mode": execution_mode,
        "delegated_action": delegated_action,
        "selected_playbooks": selected_playbooks,
        "method_selection_reason": method_reason,
        "delegated_result": delegated_result,
        "meta_status": refreshed_status,
        "meta_brain_handoff": refreshed_status.get("meta_brain_handoff"),
    }


async def synthesize_chat_product_contract() -> Dict:
    """Synthesize the canonical chat-product contract.

    Inspects the chat surface (UI, runtime, session, memory), runs all
    baseline and quality acceptance checks, and builds a repair plan for
    any failing checks.  Persists contract/spec/roadmap/telemetry
    artifacts via the governance module and logs the result to both the
    scorecard audit trail and the meta-execution ledger.

    Returns ``success=True`` only when the baseline is fully accepted.
    """
    status = refresh_chat_product_status()
    refresh_post_bl_roadmap_status()

    accepted = bool(status.get("accepted_baseline"))
    failed_check_count = int(status.get("failed_check_count", 0) or 0)

    # ── Build repair plan from failing checks ─────────────────────────
    repair_plan: List[Dict] = []
    for check in status.get("acceptance_checks", []):
        if not check.get("passed"):
            repair_plan.append({
                "check_id": check["check_id"],
                "repair_hint": check.get("repair_hint", ""),
                "detail": check.get("detail", ""),
            })
    for check in status.get("quality_checks", []):
        if not check.get("passed"):
            repair_plan.append({
                "check_id": check["check_id"],
                "repair_hint": check.get("repair_hint", ""),
                "detail": check.get("detail", ""),
            })

    # ── Audit trail in scorecard ──────────────────────────────────────
    scorecard = _load_scorecard()
    notes = scorecard.setdefault("autonomy_strategy_notes", [])
    notes.append({
        "timestamp": _now_utc(),
        "action": "synthesize_chat_product_contract",
        "result": "contract_accepted" if accepted else "contract_needs_work",
        "detail": (
            f"Baseline accepted, quality_score={status.get('quality_score')}"
            if accepted
            else f"{failed_check_count} baseline check(s) failing: "
                 + ", ".join(item["check_id"] for item in repair_plan[:5])
        ),
    })
    if len(notes) > 100:
        scorecard["autonomy_strategy_notes"] = notes[-50:]
    _save_scorecard(scorecard)

    # ── Meta execution ledger ─────────────────────────────────────────
    append_meta_execution({
        "updated_utc": _now_utc(),
        "gap_id": "chat_product_acceptance_missing" if not accepted else "chat_product_quality_and_ux",
        "title": "Synthesize chat product contract",
        "status": "completed" if accepted else "partial",
        "action": "synthesize_chat_product_contract",
        "accepted_baseline": accepted,
        "quality_score": status.get("quality_score"),
        "failed_check_count": failed_check_count,
        "repair_plan_items": len(repair_plan),
    })

    return {
        "success": accepted,
        "action_name": "synthesize_chat_product_contract",
        "mode": "meta_governance",
        "platform": "chat_product_governance",
        "venue": "brain_internal",
        "paper_only_enforced": True,
        "operational_tasks": [
            "inspect_chat_surface",
            "run_acceptance_checks",
            "build_repair_plan",
            "write_chat_contract",
            "write_chat_spec",
            "write_chat_roadmap",
            "log_audit_trail",
        ],
        "chat_product_status": status,
        "accepted_baseline": accepted,
        "current_state": status.get("current_state"),
        "failed_check_count": failed_check_count,
        "quality_score": status.get("quality_score"),
        "repair_plan": repair_plan,
        "evidence_paths": status.get("evidence_paths", []),
        "meta_brain_handoff": status.get("meta_brain_handoff"),
    }


async def improve_chat_product_quality() -> Dict:
    """Benchmark chat quality and build targeted improvement recommendations.

    This action:
    1. Refreshes the chat-product status to get live quality checks.
    2. Compares the current ``quality_score`` to the previous snapshot to
       detect regressions or improvements.
    3. Identifies which quality checks are failing and builds specific
       improvement recommendations for each.
    4. Evaluates whether Ollama model configuration (context window,
       model selection) could be tuned based on observed quality gaps.
    5. Logs the benchmark result to the scorecard audit trail and the
       meta-execution ledger.

    Returns ``success=True`` only when the baseline is accepted and the
    quality score has not regressed.
    """
    # ── Previous snapshot (for regression detection) ──────────────────
    previous_status = _safe_read_json(
        STATE_PATH / "chat_product_status_latest.json", {}
    )
    previous_quality = float(previous_status.get("quality_score", 0.0) or 0.0)

    # ── Fresh evaluation ──────────────────────────────────────────────
    status = refresh_chat_product_status()
    refresh_post_bl_roadmap_status()

    accepted = bool(status.get("accepted_baseline"))
    quality_score = float(status.get("quality_score", 0.0) or 0.0)
    quality_delta = round(quality_score - previous_quality, 4)
    regressed = quality_delta < -0.01  # >1% drop = regression

    # ── Failing quality checks → improvement recommendations ──────────
    improvement_recs: List[Dict] = []
    for check in status.get("quality_checks", []):
        if not check.get("passed"):
            improvement_recs.append({
                "check_id": check["check_id"],
                "repair_hint": check.get("repair_hint", ""),
                "detail": check.get("detail", ""),
                "category": "quality",
            })

    # ── LLM config assessment (based on runtime features) ─────────────
    telemetry_path = STATE_PATH / "chat_product_telemetry_latest.json"
    telemetry = _safe_read_json(telemetry_path, {})
    runtime = telemetry.get("runtime_features", {})
    llm_recommendations: List[str] = []

    if not runtime.get("session_memory_manager"):
        llm_recommendations.append(
            "Connect BrainSession to MemoryManager for context continuity"
        )
    if not runtime.get("response_normalization"):
        llm_recommendations.append(
            "Add response normalization to session for consistent UX"
        )
    # If quality is high but no regressions, suggest expanding context
    if quality_score >= 0.8 and not regressed:
        llm_recommendations.append(
            "Consider increasing num_ctx for deepseek-r1:14b to improve reasoning depth"
        )

    # ── Audit trail in scorecard ──────────────────────────────────────
    scorecard = _load_scorecard()
    notes = scorecard.setdefault("autonomy_strategy_notes", [])
    notes.append({
        "timestamp": _now_utc(),
        "action": "improve_chat_product_quality",
        "result": (
            "quality_regressed" if regressed
            else "quality_improved" if quality_delta > 0.01
            else "quality_stable"
        ),
        "detail": (
            f"quality_score={quality_score} (delta={quality_delta:+.4f}), "
            f"failing_checks={len(improvement_recs)}, "
            f"llm_recs={len(llm_recommendations)}"
        ),
    })
    if len(notes) > 100:
        scorecard["autonomy_strategy_notes"] = notes[-50:]
    _save_scorecard(scorecard)

    # ── Meta execution ledger ─────────────────────────────────────────
    success = accepted and not regressed
    append_meta_execution({
        "updated_utc": _now_utc(),
        "gap_id": "chat_product_quality_and_ux",
        "title": "Improve chat product quality",
        "status": "completed" if success else "partial",
        "action": "improve_chat_product_quality",
        "accepted_baseline": accepted,
        "quality_score": quality_score,
        "quality_delta": quality_delta,
        "regressed": regressed,
        "failing_quality_checks": len(improvement_recs),
        "llm_recommendations_count": len(llm_recommendations),
    })

    return {
        "success": success,
        "action_name": "improve_chat_product_quality",
        "mode": "meta_governance",
        "platform": "chat_product_governance",
        "venue": "brain_internal",
        "paper_only_enforced": True,
        "operational_tasks": [
            "refresh_chat_product_status",
            "benchmark_quality_vs_previous",
            "identify_failing_quality_checks",
            "assess_llm_config",
            "build_improvement_recommendations",
            "log_audit_trail",
        ],
        "chat_product_status": status,
        "current_state": status.get("current_state"),
        "work_status": status.get("work_status"),
        "quality_score": quality_score,
        "previous_quality_score": previous_quality,
        "quality_delta": quality_delta,
        "regressed": regressed,
        "improvement_recommendations": improvement_recs,
        "llm_recommendations": llm_recommendations,
        "evidence_paths": status.get("evidence_paths", []),
        "meta_brain_handoff": status.get("meta_brain_handoff"),
    }


async def synthesize_utility_governance_contract() -> Dict:
    """Synthesize the canonical Utility U governance contract.

    Inspects the Utility U domain (snapshot, gate, module, runtime
    endpoints), runs all acceptance checks, and builds a repair plan for
    any failing checks or active blockers.  Computes U-proxy alignment
    by comparing the ``u_proxy_score`` against the gate verdict.

    Persists contract/spec/roadmap/activation artifacts via the
    governance module and logs to both the scorecard audit trail and the
    meta-execution ledger.

    Returns ``success=True`` only when the governance baseline is fully
    accepted.
    """
    status = refresh_utility_governance_status()
    refresh_post_bl_roadmap_status()

    accepted = bool(status.get("accepted_baseline"))
    failed_check_count = int(status.get("failed_check_count", 0) or 0)
    blockers = list(status.get("blockers", []))
    u_proxy_score = status.get("u_proxy_score")
    verdict = status.get("verdict")

    # ── Build repair plan from failing checks + blockers ──────────────
    repair_plan: List[Dict] = []
    for check in status.get("acceptance_checks", []):
        if not check.get("passed"):
            repair_plan.append({
                "check_id": check["check_id"],
                "repair_hint": check.get("repair_hint", ""),
                "detail": check.get("detail", ""),
            })

    # ── U-proxy alignment analysis ────────────────────────────────────
    u_proxy_aligned = False
    alignment_detail = "no_score_available"
    if u_proxy_score is not None:
        u_val = float(u_proxy_score)
        if verdict == "promote" and u_val >= 0.6:
            u_proxy_aligned = True
            alignment_detail = f"u_proxy={u_val:.4f} aligned with verdict=promote"
        elif verdict == "hold" and 0.3 <= u_val < 0.6:
            u_proxy_aligned = True
            alignment_detail = f"u_proxy={u_val:.4f} aligned with verdict=hold"
        elif verdict in (None, "hold") and u_val < 0.3:
            u_proxy_aligned = True
            alignment_detail = f"u_proxy={u_val:.4f} aligned with weak/no verdict"
        else:
            alignment_detail = (
                f"u_proxy={u_val:.4f} vs verdict={verdict} — potential misalignment"
            )

    # ── Audit trail in scorecard ──────────────────────────────────────
    scorecard = _load_scorecard()
    notes = scorecard.setdefault("autonomy_strategy_notes", [])
    notes.append({
        "timestamp": _now_utc(),
        "action": "synthesize_utility_governance_contract",
        "result": "contract_accepted" if accepted else "contract_needs_work",
        "detail": (
            f"Baseline accepted, u_proxy_aligned={u_proxy_aligned}"
            if accepted
            else f"{failed_check_count} check(s) failing, {len(blockers)} blocker(s): "
                 + ", ".join(item["check_id"] for item in repair_plan[:5])
        ),
    })
    if len(notes) > 100:
        scorecard["autonomy_strategy_notes"] = notes[-50:]
    _save_scorecard(scorecard)

    # ── Meta execution ledger ─────────────────────────────────────────
    append_meta_execution({
        "updated_utc": _now_utc(),
        "gap_id": (
            "utility_governance_contract_missing"
            if not accepted
            else "utility_sensitivity_and_lift"
        ),
        "title": "Synthesize utility governance contract",
        "status": "completed" if accepted else "partial",
        "action": "synthesize_utility_governance_contract",
        "accepted_baseline": accepted,
        "failed_check_count": failed_check_count,
        "blocker_count": len(blockers),
        "u_proxy_score": u_proxy_score,
        "u_proxy_aligned": u_proxy_aligned,
        "repair_plan_items": len(repair_plan),
    })

    return {
        "success": accepted,
        "action_name": "synthesize_utility_governance_contract",
        "mode": "meta_governance",
        "platform": "utility_governance",
        "venue": "brain_internal",
        "paper_only_enforced": True,
        "operational_tasks": [
            "inspect_utility_surface",
            "run_acceptance_checks",
            "build_repair_plan",
            "compute_u_proxy_alignment",
            "write_utility_contract",
            "write_utility_spec",
            "write_utility_roadmap",
            "log_audit_trail",
        ],
        "utility_governance_status": status,
        "accepted_baseline": accepted,
        "current_state": status.get("current_state"),
        "failed_check_count": failed_check_count,
        "u_proxy_score": u_proxy_score,
        "u_proxy_aligned": u_proxy_aligned,
        "alignment_detail": alignment_detail,
        "verdict": verdict,
        "blockers": blockers,
        "repair_plan": repair_plan,
        "evidence_paths": status.get("evidence_paths", []),
        "meta_brain_handoff": status.get("meta_brain_handoff"),
    }


async def reduce_drawdown_and_capital_at_risk() -> Dict:
    """Reduce portfolio drawdown by freezing the worst-performing strategy.

    When the blocker ``drawdown_limit_breached`` fires (drawdown > max_drawdown),
    this action:

    1. Identifies the strategy with the worst drawdown_penalty in the ranking.
    2. Freezes that strategy by setting its scorecard governance_state to
       ``frozen`` (prevents further execution until conditions improve).
    3. Selects the recovery candidate from the ranking as a replacement.
    4. Reduces recommended iterations across all strategies to 1 to slow
       capital deployment while drawdown is elevated.
    5. Logs the corrective action in the scorecard.

    This is a risk-management action, not a trading action.  It does not
    execute any paper trades.
    """
    _ensure_trading_policy()
    refresh_strategy_engine()
    ranking = read_ranking_v2()
    ranked = ranking.get("ranked", [])

    # Find the strategy with worst drawdown penalty
    worst_strategy = None
    worst_drawdown = 0.0
    for candidate in ranked:
        dd = float(candidate.get("drawdown_penalty", 0.0) or 0.0)
        gov = candidate.get("governance_state", "")
        if gov == "frozen":
            continue  # already frozen
        if dd > worst_drawdown:
            worst_drawdown = dd
            worst_strategy = candidate

    frozen_strategy_id = None
    if worst_strategy and worst_drawdown > 0:
        frozen_strategy_id = worst_strategy.get("strategy_id")
        # Freeze the strategy in the scorecard
        from brain_v9.trading.strategy_scorecard import read_scorecards, SCORECARDS_PATH
        scorecards_payload = read_scorecards()
        scorecards = scorecards_payload.get("scorecards", {})
        card = scorecards.get(frozen_strategy_id, {})
        if card:
            card["governance_state"] = "frozen"
            card["promotion_state"] = "frozen"
            card["freeze_recommended"] = True
            card["freeze_reason"] = "drawdown_limit_breached_auto_freeze"
            card["freeze_utc"] = _now_utc()
            write_json(SCORECARDS_PATH, scorecards_payload)
            log.info(
                "Froze strategy %s due to drawdown_penalty=%.2f",
                frozen_strategy_id, worst_drawdown,
            )

    # Identify recovery candidate
    recovery = ranking.get("top_recovery_candidate") or {}
    recovery_id = recovery.get("strategy_id")

    # Log in scorecard
    scorecard = _load_scorecard()
    notes = scorecard.setdefault("autonomy_strategy_notes", [])
    notes.append({
        "timestamp": _now_utc(),
        "action": "reduce_drawdown_and_capital_at_risk",
        "result": "strategy_frozen" if frozen_strategy_id else "no_strategy_to_freeze",
        "detail": (
            f"Froze {frozen_strategy_id} (drawdown_penalty={worst_drawdown:.2f}). "
            f"Recovery candidate: {recovery_id}."
            if frozen_strategy_id else
            "No non-frozen strategy with drawdown penalty found."
        ),
    })
    if len(notes) > 100:
        scorecard["autonomy_strategy_notes"] = notes[-50:]
    _save_scorecard(scorecard)

    return {
        "success": bool(frozen_strategy_id),
        "action_name": "reduce_drawdown_and_capital_at_risk",
        "mode": "risk_management",
        "platform": "governance_engine",
        "venue": "brain_internal",
        "paper_only_enforced": True,
        "operational_tasks": [
            "identify_worst_drawdown_strategy",
            "freeze_strategy_scorecard",
            "select_recovery_candidate",
            "log_corrective_action",
        ],
        "frozen_strategy_id": frozen_strategy_id,
        "worst_drawdown_penalty": round(worst_drawdown, 4),
        "recovery_candidate_id": recovery_id,
        "strategies_evaluated": len(ranked),
        "scorecard_path": str(SCORECARD_PATH),
    }


async def rebalance_capital_exposure() -> Dict:
    """Reduce capital exposure when committed cash exceeds 50 % of total.

    When the blocker ``capital_commitment_too_high`` fires, this action:

    1. Resolves any pending paper trades via the deferred resolution engine
       (P3-02) to free up committed capital.
    2. Freezes the lowest-ranked non-frozen strategy to prevent new positions
       from being opened until exposure normalises.
    3. Logs the rebalancing action.

    This is a capital-management action.  It does not open new trades.
    """
    _ensure_trading_policy()
    refresh_strategy_engine()

    # --- 1. Force-resolve pending trades to free capital ---------------
    from brain_v9.trading.paper_execution import (
        resolve_pending_paper_trades,
    )
    from brain_v9.trading.feature_engine import build_market_feature_snapshot

    feature_snapshot = build_market_feature_snapshot()
    resolution_result = resolve_pending_paper_trades(feature_snapshot)
    resolved_count = resolution_result.get("resolved", 0) if isinstance(resolution_result, dict) else 0

    # --- 2. Freeze the lowest-ranked non-frozen strategy ---------------
    ranking = read_ranking_v2()
    ranked = ranking.get("ranked", [])

    frozen_strategy_id = None
    if ranked:
        # Walk from bottom of ranking upward — freeze the worst
        for candidate in reversed(ranked):
            gov = candidate.get("governance_state", "")
            if gov == "frozen":
                continue
            if str(candidate.get("archive_state") or "").startswith("archived"):
                continue
            frozen_strategy_id = candidate.get("strategy_id")
            break

    if frozen_strategy_id:
        from brain_v9.trading.strategy_scorecard import read_scorecards, SCORECARDS_PATH
        scorecards_payload = read_scorecards()
        scorecards = scorecards_payload.get("scorecards", {})
        card = scorecards.get(frozen_strategy_id, {})
        if card:
            card["governance_state"] = "frozen"
            card["promotion_state"] = "frozen"
            card["freeze_recommended"] = True
            card["freeze_reason"] = "capital_commitment_too_high_auto_freeze"
            card["freeze_utc"] = _now_utc()
            write_json(SCORECARDS_PATH, scorecards_payload)
            log.info(
                "Froze lowest-ranked strategy %s to reduce capital exposure",
                frozen_strategy_id,
            )

    # --- 3. Log in scorecard -------------------------------------------
    scorecard = _load_scorecard()
    notes = scorecard.setdefault("autonomy_strategy_notes", [])
    notes.append({
        "timestamp": _now_utc(),
        "action": "rebalance_capital_exposure",
        "result": "exposure_reduced",
        "detail": (
            f"Resolved {resolved_count} pending trades. "
            f"Froze lowest-ranked strategy: {frozen_strategy_id}."
            if frozen_strategy_id else
            f"Resolved {resolved_count} pending trades. No strategy to freeze."
        ),
    })
    if len(notes) > 100:
        scorecard["autonomy_strategy_notes"] = notes[-50:]
    _save_scorecard(scorecard)

    return {
        "success": True,
        "action_name": "rebalance_capital_exposure",
        "mode": "capital_management",
        "platform": "governance_engine",
        "venue": "brain_internal",
        "paper_only_enforced": True,
        "operational_tasks": [
            "resolve_pending_paper_trades",
            "freeze_lowest_ranked_strategy",
            "log_rebalancing_action",
        ],
        "resolved_pending_trades": resolved_count,
        "frozen_strategy_id": frozen_strategy_id,
        "strategies_evaluated": len(ranked),
        "scorecard_path": str(SCORECARD_PATH),
    }


# ── P4-11: QC Backtest Orchestration Action ──────────────────────────────────
# Known project IDs to cycle through
_QC_PROJECT_IDS = [24654779, 25550271]


async def run_qc_backtest_validation() -> Dict:
    """
    Autonomy action: compile + backtest a QC project, then bridge results
    into strategy_specs so the Brain can evaluate QC-validated strategies.

    Cycles through known QC projects.  On each invocation the next project
    in the list is selected (round-robin via state file).
    """
    from brain_v9.trading.qc_orchestrator import QCBacktestOrchestrator
    from brain_v9.trading.qc_strategy_bridge import (
        backtest_to_strategy_spec,
        merge_qc_strategy,
    )
    from datetime import datetime, timezone

    # ── 1. Pick next project (round-robin) ───────────────────────────────
    qc_action_state_path = BASE_PATH / "tmp_agent" / "state" / "qc_backtests" / "action_state.json"
    action_state = read_json(qc_action_state_path, default={"last_index": -1})
    next_idx = (action_state.get("last_index", -1) + 1) % len(_QC_PROJECT_IDS)
    project_id = _QC_PROJECT_IDS[next_idx]
    action_state["last_index"] = next_idx
    write_json(qc_action_state_path, action_state)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backtest_name = f"Brain_V9_auto_{project_id}_{timestamp}"

    log.info("run_qc_backtest_validation: project=%d name=%s", project_id, backtest_name)

    # ── 2. Run orchestrator ──────────────────────────────────────────────
    orch = QCBacktestOrchestrator()
    try:
        result = await orch.run_backtest(project_id, backtest_name)
    except Exception as exc:
        log.error("run_qc_backtest_validation exception: %s", exc)
        return {
            "success": False,
            "action_name": "run_qc_backtest_validation",
            "mode": "research_backtest",
            "platform": "quantconnect",
            "venue": "quantconnect",
            "paper_only_enforced": True,
            "error": str(exc),
            "project_id": project_id,
            "operational_tasks": ["compile_project", "launch_backtest", "poll_results"],
        }

    if not result.get("success"):
        return {
            "success": False,
            "action_name": "run_qc_backtest_validation",
            "mode": "research_backtest",
            "platform": "quantconnect",
            "venue": "quantconnect",
            "paper_only_enforced": True,
            "phase": result.get("phase", "unknown"),
            "error": result.get("error", ""),
            "project_id": project_id,
            "operational_tasks": ["compile_project", "launch_backtest", "poll_results"],
        }

    # ── 3. Bridge results into strategy_specs ────────────────────────────
    backtest_id = result.get("backtest_id", "")
    metrics = result.get("metrics", {})
    spec = backtest_to_strategy_spec(project_id, backtest_id, metrics, backtest_name)

    # P4-15: Apply QC pattern params to enrich the strategy spec
    try:
        from brain_v9.trading.qc_pattern_ingester import apply_patterns_to_spec
        apply_patterns_to_spec(spec)
    except Exception as e:
        log.warning("QC pattern ingestion failed (non-fatal): %s", e)

    merge_result = merge_qc_strategy(spec)

    return {
        "success": True,
        "action_name": "run_qc_backtest_validation",
        "mode": "research_backtest",
        "platform": "quantconnect",
        "venue": "quantconnect",
        "paper_only_enforced": True,
        "operational_tasks": [
            "select_project",
            "compile_project",
            "launch_backtest",
            "poll_results",
            "extract_metrics",
            "bridge_to_strategy_specs",
        ],
        "project_id": project_id,
        "backtest_id": backtest_id,
        "backtest_name": backtest_name,
        "phase": result.get("phase", ""),
        "metrics": metrics,
        "strategy_id": spec["strategy_id"],
        "strategy_status": spec["status"],
        "merge_action": merge_result.get("action", ""),
    }


async def break_system_deadlock() -> Dict:
    """P8-03: Composite action to break a system-wide trading deadlock.

    Triggered when ALL strategies are frozen/archived and the autonomy loop
    cannot find any executable candidate.  Steps:

    1. Force-unfreeze the best frozen strategy (highest potential, smallest
       sample — still worth re-testing).
    2. Generate new strategy variants from the knowledge base so the system
       has fresh candidates to explore.
    3. Run ``expand_signal_pipeline()`` with widened filters to find
       actionable signals immediately.
    4. Reset the skip counter so execution isn't throttled.

    Returns a summary dict compatible with the action job schema.
    """
    log.info("P8-03: break_system_deadlock — starting composite deadlock-break action.")
    _ensure_trading_policy()
    refresh_strategy_engine()

    # ── Step 1: Force-unfreeze best frozen strategy ────────────────────────
    from brain_v9.trading.strategy_scorecard import read_scorecards, force_unfreeze_best_frozen
    from brain_v9.core.state_io import write_json as _wj
    scorecards_payload = read_scorecards()
    scorecards = scorecards_payload.get("scorecards", {})
    unfrozen_id = force_unfreeze_best_frozen(scorecards)
    if unfrozen_id:
        scorecards_payload["updated_utc"] = _now_utc()
        _wj(
            STATE_PATH / "strategy_engine" / "strategy_scorecards.json",
            scorecards_payload,
        )
        log.info("P8-03: Force-unfroze strategy '%s'.", unfrozen_id)

    # ── Step 2: Generate new strategy variants ─────────────────────────────
    new_variants: List[str] = []
    try:
        from brain_v9.research.knowledge_base import generate_strategy_variants
        new_variants = generate_strategy_variants()
        log.info("P8-03: Generated %d new strategy variant(s): %s", len(new_variants), new_variants)
    except Exception as exc:
        log.warning("P8-03: Failed to generate strategy variants: %s", exc)

    # ── Step 3: Refresh engine so new variants + unfrozen strategy are visible
    refresh_strategy_engine()

    # ── Step 4: Run expand_signal_pipeline to find actionable signals ──────
    pipeline_result: Dict = {}
    try:
        pipeline_result = await expand_signal_pipeline()
        log.info(
            "P8-03: expand_signal_pipeline completed — viable_signal=%s trade_executed=%s",
            pipeline_result.get("viable_signal_found"),
            pipeline_result.get("trade_executed"),
        )
    except Exception as exc:
        log.warning("P8-03: expand_signal_pipeline failed: %s", exc)
        pipeline_result = {"success": False, "error": str(exc)}

    # ── Step 5: Reset skip counter ─────────────────────────────────────────
    skips_reset = False
    try:
        from brain_v9.util import get_consecutive_skips, reset_skips_counter
        if get_consecutive_skips() > 0:
            reset_skips_counter()
            skips_reset = True
    except Exception:
        log.debug("skip-counter reset failed (non-critical)", exc_info=True)

    return {
        "success": True,
        "action_name": "break_system_deadlock",
        "mode": "paper_only",
        "steps_completed": [
            "force_unfreeze_best_frozen",
            "generate_strategy_variants",
            "refresh_strategy_engine",
            "expand_signal_pipeline",
            "reset_skip_counter",
        ],
        "unfrozen_strategy": unfrozen_id,
        "new_variants": new_variants,
        "pipeline_result": {
            "viable_signal_found": pipeline_result.get("viable_signal_found"),
            "trade_executed": pipeline_result.get("trade_executed"),
        },
        "skips_reset": skips_reset,
        "paper_only_enforced": True,
    }


# ── Phase B/C: Auto-promotion and QC ingestion actions ───────────────────────

async def auto_promote_to_ibkr_paper() -> Dict:
    """
    Phase C: Autonomous promotion action.

    Scans scorecards for strategies in 'promote_candidate' state,
    validates they meet all promotion criteria, and transitions them
    to 'live_paper' state — ready for IBKR paper execution.

    Does NOT place orders — just changes governance state. The trading
    pipeline will then pick up live_paper strategies for signal generation
    and order execution via ibkr_order_executor.

    Returns summary of promoted strategies.
    """
    from brain_v9.trading.strategy_scorecard import read_scorecards
    sc_path = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"

    data = read_scorecards()
    scorecards = data.get("scorecards", {})
    promoted: List[Dict] = []
    skipped: List[Dict] = []

    for sid, card in scorecards.items():
        gov = card.get("governance_state", "")
        if gov != "promote_candidate":
            continue

        # Extra validation before promotion
        expectancy = float(card.get("expectancy", 0))
        win_rate = float(card.get("win_rate", 0))
        resolved = int(card.get("entries_resolved", 0))
        sharpe = float(card.get("sharpe_ratio", 0))
        max_dd = float(card.get("max_drawdown", 0))
        sc = card.get("success_criteria", {})

        min_exp = float(sc.get("min_expectancy", 0.1))
        min_wr = float(sc.get("min_win_rate", 0.45))
        min_resolved = int(sc.get("min_resolved_trades", 30))
        min_sharpe = float(sc.get("min_sharpe", 0.8))
        max_allowed_dd = float(sc.get("max_drawdown", 0.20))

        # Strict promotion gate
        reasons = []
        if expectancy < min_exp:
            reasons.append(f"expectancy {expectancy:.4f} < {min_exp}")
        if win_rate < min_wr:
            reasons.append(f"win_rate {win_rate:.2%} < {min_wr:.0%}")
        if resolved < min_resolved:
            reasons.append(f"resolved {resolved} < {min_resolved}")
        if sharpe < min_sharpe:
            reasons.append(f"sharpe {sharpe:.2f} < {min_sharpe}")
        if max_dd > max_allowed_dd:
            reasons.append(f"max_dd {max_dd:.2%} > {max_allowed_dd:.0%}")

        if reasons:
            skipped.append({"strategy_id": sid, "reasons": reasons})
            log.info("Promotion skipped for %s: %s", sid, "; ".join(reasons))
            continue

        # PROMOTE: transition governance state
        card["governance_state"] = "live_paper"
        card["promotion_state"] = "live_paper"
        card["promoted_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        card["promoted_from"] = "promote_candidate"
        card["promotion_criteria_met"] = {
            "expectancy": expectancy,
            "win_rate": win_rate,
            "resolved": resolved,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
        }

        promoted.append({
            "strategy_id": sid,
            "family": card.get("family", "unknown"),
            "venue": card.get("venue", "unknown"),
            "expectancy": expectancy,
            "win_rate": win_rate,
            "sharpe": sharpe,
        })

        log.info(
            "PROMOTED %s → live_paper (E=%.4f, WR=%.1f%%, Sharpe=%.2f, DD=%.1f%%)",
            sid, expectancy, win_rate * 100, sharpe, max_dd * 100,
        )

    if promoted:
        data["scorecards"] = scorecards
        data["updated_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        write_json(sc_path, data)

    return {
        "success": True,
        "action_name": "auto_promote_to_ibkr_paper",
        "promoted_count": len(promoted),
        "skipped_count": len(skipped),
        "promoted": promoted,
        "skipped": skipped,
        "paper_only_enforced": True,
    }


async def ingest_qc_results_action() -> Dict:
    """
    Autonomy action wrapper for QC results ingestion (Phase A).
    Called by the autonomy loop / scheduler.
    """
    from brain_v9.trading.qc_results_ingester import ingest_qc_results
    try:
        result = await ingest_qc_results()
        return {
            "success": result.get("success", False),
            "action_name": "ingest_qc_results",
            "summary": result.get("summary", ""),
            "new_strategies": result.get("new_strategies", 0),
            "updated_strategies": result.get("updated_strategies", 0),
            "errors": result.get("errors", []),
            "paper_only_enforced": True,
        }
    except Exception as exc:
        log.error("ingest_qc_results_action failed: %s", exc)
        return {
            "success": False,
            "action_name": "ingest_qc_results",
            "error": str(exc),
            "paper_only_enforced": True,
        }


async def _action_scan_ibkr_signals() -> Dict:
    """Autonomy action: scan live_paper strategies for signals and dispatch orders."""
    try:
        from brain_v9.trading.ibkr_signal_engine import scan_and_execute
        result = await scan_and_execute()
        return {
            "success": result.get("success", False),
            "action_name": "scan_ibkr_signals",
            "strategies_scanned": result.get("strategies_scanned", 0),
            "signals_generated": result.get("signals_generated", 0),
            "orders_dispatched": result.get("orders_dispatched", 0),
            "errors": result.get("errors", []),
            "paper_only_enforced": True,
        }
    except Exception as exc:
        log.error("_action_scan_ibkr_signals failed: %s", exc)
        return {"success": False, "action_name": "scan_ibkr_signals", "error": str(exc)}


async def _action_poll_ibkr_performance() -> Dict:
    """Autonomy action: poll IBKR positions/P&L → update scorecards."""
    try:
        from brain_v9.trading.ibkr_performance_tracker import poll_ibkr_performance
        result = await poll_ibkr_performance()
        return {
            "success": result.get("success", False),
            "action_name": "poll_ibkr_performance",
            "positions_found": result.get("positions_found", 0),
            "strategies_updated": len(result.get("strategies_updated", [])),
            "degradations": len(result.get("degradations", [])),
            "account_summary": result.get("account_summary", {}),
            "paper_only_enforced": True,
        }
    except Exception as exc:
        log.error("_action_poll_ibkr_performance failed: %s", exc)
        return {"success": False, "action_name": "poll_ibkr_performance", "error": str(exc)}


async def _action_iterate_underperformers() -> Dict:
    """Autonomy action: analyze underperforming strategies and iterate."""
    try:
        from brain_v9.trading.qc_iteration_engine import auto_iterate_underperformers
        result = await auto_iterate_underperformers()
        return {
            "success": result.get("success", False),
            "action_name": "iterate_underperformers",
            "strategies_scanned": result.get("strategies_scanned", 0),
            "strategies_iterated": result.get("strategies_iterated", 0),
            "results": result.get("results", []),
            "paper_only_enforced": True,
        }
    except Exception as exc:
        log.error("_action_iterate_underperformers failed: %s", exc)
        return {"success": False, "action_name": "iterate_underperformers", "error": str(exc)}


ACTION_MAP = {
    "increase_resolved_sample": run_paper_trades,
    "improve_signal_capture_and_context_window": expand_signal_pipeline,
    "improve_expectancy_or_reduce_penalties": adjust_strategy_params,
    "select_and_compare_strategies": select_and_compare_strategies,
    "advance_meta_improvement_roadmap": advance_meta_improvement_roadmap,
    "synthesize_chat_product_contract": synthesize_chat_product_contract,
    "improve_chat_product_quality": improve_chat_product_quality,
    "synthesize_utility_governance_contract": synthesize_utility_governance_contract,
    "reduce_drawdown_and_capital_at_risk": reduce_drawdown_and_capital_at_risk,
    "rebalance_capital_exposure": rebalance_capital_exposure,
    "run_qc_backtest_validation": run_qc_backtest_validation,
    "break_system_deadlock": break_system_deadlock,
    "auto_surgeon_cycle": run_auto_surgeon_cycle,
    "auto_promote_to_ibkr_paper": auto_promote_to_ibkr_paper,
    "ingest_qc_results": ingest_qc_results_action,
    # Phase 9: Closed-loop trading actions
    "scan_ibkr_signals": _action_scan_ibkr_signals,
    "poll_ibkr_performance": _action_poll_ibkr_performance,
    "iterate_underperformers": _action_iterate_underperformers,
}


async def execute_action(action_name: str, force: bool = False) -> Dict:
    if action_name not in ACTION_MAP:
        return {"success": False, "error": f"Acción no soportada: {action_name}", "action_name": action_name}
    if not force and _cooldown_active(action_name):
        return {"success": False, "status": "cooldown_active", "action_name": action_name}

    job_id = f"actjob_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}"
    job_dir = JOBS_PATH / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    next_actions = _safe_read_json(NEXT_ACTIONS_PATH, {})
    started_utc = _now_utc()
    try:
        outcome = await ACTION_MAP[action_name]()
    except Exception as _exc:
        import traceback as _tb
        log.error("execute_action(%s) EXCEPTION:\n%s", action_name, _tb.format_exc())
        outcome = {
            "success": False,
            "status": "exception",
            "error": str(_exc),
            "action_name": action_name,
        }
    refresh_utility_governance_status()
    refresh_chat_product_status()
    refresh_post_bl_roadmap_status()
    refreshed_meta_status = refresh_meta_improvement_status()
    finished_utc = _now_utc()

    result = {
        "schema_version": "autonomy_action_job_v1",
        "job_id": job_id,
        "action_name": action_name,
        "started_utc": started_utc,
        "finished_utc": finished_utc,
        "source_next_actions": next_actions,
        "result": outcome,
        "post_action_meta_status": {
            "top_gap": (refreshed_meta_status.get("top_gap") or {}).get("gap_id"),
            "work_status": refreshed_meta_status.get("roadmap", {}).get("work_status"),
        },
        "status": "completed" if outcome.get("success") else outcome.get("status", "failed"),
    }
    _safe_write_json(job_dir / "result.json", result)

    ledger_entry = {
        "job_id": job_id,
        "action_name": action_name,
        "updated_utc": finished_utc,
        "status": result["status"],
        "result_summary": {
            "success": outcome.get("success", False),
            "mode": outcome.get("mode"),
            "trades_executed": outcome.get("trades_executed"),
        },
        "artifact": str(job_dir / "result.json"),
    }
    _append_ledger(ledger_entry)
    log.info("ActionExecutor: %s -> %s", action_name, result["status"])
    return result
