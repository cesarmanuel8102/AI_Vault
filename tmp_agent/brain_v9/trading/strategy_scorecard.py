"""
Brain V9 - Strategy scorecards
Mantiene métricas por estrategia para comparación y selección.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

log = logging.getLogger("strategy_scorecard")

from brain_v9.config import BASE_PATH
import brain_v9.config as _cfg
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

SCORECARDS_PATH = ENGINE_PATH / "strategy_scorecards.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _ledger_path() -> Path:
    return SCORECARDS_PATH.parent / "signal_paper_execution_ledger.json"


def _blank_scorecard(strategy: Dict) -> Dict:
    return {
        "strategy_id": strategy["strategy_id"],
        "family": strategy.get("family"),
        "venue": strategy.get("venue"),
        "status": strategy.get("status", "paper_candidate"),
        "entries_taken": 0,
        "entries_resolved": 0,
        "entries_open": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "net_pnl": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "profit_factor": 0.0,
        "largest_win": 0.0,
        "largest_loss": 0.0,
        "recent_5_outcomes": [],
        "sample_quality": 0.0,
        "consistency_score": 0.0,
        "promotion_state": "paper_candidate",
        "last_trade_utc": None,
        "linked_hypotheses": strategy.get("linked_hypotheses", []),
        "success_criteria": strategy.get("success_criteria", {}),
    }


def _blank_symbol_scorecard(strategy: Dict, symbol: str) -> Dict:
    card = _blank_scorecard(strategy)
    card["symbol"] = symbol
    card["key"] = _symbol_key(strategy, symbol)
    card["scope"] = "venue_strategy_symbol"
    return card


def _blank_context_scorecard(strategy: Dict, symbol: str, timeframe: str, setup_variant: str) -> Dict:
    card = _blank_symbol_scorecard(strategy, symbol)
    card["timeframe"] = timeframe
    card["setup_variant"] = setup_variant
    card["key"] = _context_key(strategy, symbol, timeframe, setup_variant)
    card["scope"] = "venue_strategy_symbol_timeframe_setup"
    return card


def _symbol_key(strategy: Dict, symbol: str) -> str:
    return f'{strategy["venue"]}::{strategy["strategy_id"]}::{symbol}'


def _context_key(strategy: Dict, symbol: str, timeframe: str, setup_variant: str) -> str:
    return f'{strategy["venue"]}::{strategy["strategy_id"]}::{symbol}::{timeframe}::{setup_variant}'


def _aggregate_recent_outcomes(symbol_cards: List[Dict], limit: int = 5) -> List[Dict]:
    items: List[Dict] = []
    for card in symbol_cards:
        for row in card.get("recent_5_outcomes", []) or []:
            if isinstance(row, dict):
                items.append(row)
    items.sort(key=lambda row: str(row.get("timestamp") or ""))
    return items[-limit:]


def _sync_aggregate_from_symbol_cards(card: Dict, symbol_cards: List[Dict]) -> None:
    """Rebuild aggregate strategy counters from symbol scorecards.

    Symbol scorecards are the least ambiguous rollup: each trade should hit
    exactly one symbol card, while context cards can legitimately overlap by
    timeframe/setup. Recomputing aggregate fields from symbol cards prevents
    drift between the aggregate card and the canonical per-symbol state.
    """
    if not symbol_cards:
        return

    card["entries_taken"] = sum(int(c.get("entries_taken", 0) or 0) for c in symbol_cards)
    card["entries_resolved"] = sum(int(c.get("entries_resolved", 0) or 0) for c in symbol_cards)
    card["entries_open"] = sum(int(c.get("entries_open", 0) or 0) for c in symbol_cards)
    card["wins"] = sum(int(c.get("wins", 0) or 0) for c in symbol_cards)
    card["losses"] = sum(int(c.get("losses", 0) or 0) for c in symbol_cards)
    card["draws"] = sum(int(c.get("draws", 0) or 0) for c in symbol_cards)
    card["gross_profit"] = round(sum(float(c.get("gross_profit", 0.0) or 0.0) for c in symbol_cards), 4)
    card["gross_loss"] = round(sum(float(c.get("gross_loss", 0.0) or 0.0) for c in symbol_cards), 4)
    card["net_pnl"] = round(sum(float(c.get("net_pnl", 0.0) or 0.0) for c in symbol_cards), 4)
    card["largest_win"] = max((float(c.get("largest_win", 0.0) or 0.0) for c in symbol_cards), default=0.0)
    card["largest_loss"] = max((float(c.get("largest_loss", 0.0) or 0.0) for c in symbol_cards), default=0.0)
    card["recent_5_outcomes"] = _aggregate_recent_outcomes(symbol_cards)

    last_trade_utc = max(
        (str(c.get("last_trade_utc") or "") for c in symbol_cards if c.get("last_trade_utc")),
        default="",
    )
    card["last_trade_utc"] = last_trade_utc or None


def _reset_trade_metrics(card: Dict) -> None:
    card["entries_taken"] = 0
    card["entries_resolved"] = 0
    card["entries_open"] = 0
    card["wins"] = 0
    card["losses"] = 0
    card["draws"] = 0
    card["gross_profit"] = 0.0
    card["gross_loss"] = 0.0
    card["net_pnl"] = 0.0
    card["avg_win"] = 0.0
    card["avg_loss"] = 0.0
    card["win_rate"] = 0.0
    card["expectancy"] = 0.0
    card["profit_factor"] = 0.0
    card["largest_win"] = 0.0
    card["largest_loss"] = 0.0
    card["recent_5_outcomes"] = []
    card["sample_quality"] = 0.0
    card["consistency_score"] = 0.0
    card["last_trade_utc"] = None


def _append_trade_metrics(card: Dict, trade: Dict) -> None:
    profit = float(trade.get("profit", 0.0) or 0.0)
    result = str(trade.get("result") or "").strip().lower()
    resolved = bool(trade.get("resolved", False))
    symbol = trade.get("symbol") or card.get("symbol") or "UNKNOWN"
    trade_timestamp = trade.get("resolved_utc") or trade.get("timestamp") or _utc_now()

    card["entries_taken"] = int(card.get("entries_taken", 0) or 0) + 1
    if resolved:
        card["entries_resolved"] = int(card.get("entries_resolved", 0) or 0) + 1
    else:
        card["entries_open"] = int(card.get("entries_open", 0) or 0) + 1

    if resolved and result == "win":
        card["wins"] = int(card.get("wins", 0) or 0) + 1
        card["gross_profit"] = round(float(card.get("gross_profit", 0.0) or 0.0) + profit, 4)
        card["largest_win"] = max(float(card.get("largest_win", 0.0) or 0.0), profit)
    elif resolved and result == "loss":
        card["losses"] = int(card.get("losses", 0) or 0) + 1
        card["gross_loss"] = round(float(card.get("gross_loss", 0.0) or 0.0) + abs(profit), 4)
        card["largest_loss"] = max(float(card.get("largest_loss", 0.0) or 0.0), abs(profit))
    elif resolved:
        card["draws"] = int(card.get("draws", 0) or 0) + 1

    if resolved:
        card["net_pnl"] = round(float(card.get("net_pnl", 0.0) or 0.0) + profit, 4)

    recent = list(card.get("recent_5_outcomes", []))
    recent.append({
        "timestamp": trade_timestamp,
        "symbol": symbol,
        "direction": trade.get("direction"),
        "result": trade.get("result"),
        "profit": profit,
        "resolved": resolved,
    })
    card["recent_5_outcomes"] = recent[-5:]
    card["last_trade_utc"] = trade_timestamp

    # P-OP23: Track average resolution price change for signal threshold tuning
    if resolved:
        price_change = float(trade.get("resolution_price_change_pct", 0.0) or 0.0)
        if price_change > 0:
            _total_pct = float(card.get("_total_resolution_pct", 0.0) or 0.0) + price_change
            _count_pct = int(card.get("_count_resolution_pct", 0) or 0) + 1
            card["_total_resolution_pct"] = round(_total_pct, 6)
            card["_count_resolution_pct"] = _count_pct
            card["avg_resolution_price_change_pct"] = round(_total_pct / _count_pct, 6)


def _sync_strategy_from_ledger(
    strategy: Dict,
    aggregate_card: Dict,
    symbol_scorecards: Dict[str, Dict],
    context_scorecards: Dict[str, Dict],
    ledger_entries: List[Dict],
) -> None:
    strategy_id = strategy.get("strategy_id")
    venue = strategy.get("venue")
    if not strategy_id or not venue:
        return

    strategy_symbol_cards = {
        key: card for key, card in symbol_scorecards.items()
        if key.startswith(f"{venue}::{strategy_id}::")
    }
    strategy_context_cards = {
        key: card for key, card in context_scorecards.items()
        if key.startswith(f"{venue}::{strategy_id}::")
    }

    declared_universe = set(strategy.get("universe") or [])
    declared_timeframes = set(strategy.get("timeframes") or [])
    declared_variants = set(strategy.get("setup_variants") or [])
    aggregate_entries = []
    scoped_entries = []
    for trade in ledger_entries:
        if trade.get("strategy_id") != strategy_id or trade.get("venue") != venue:
            continue
        aggregate_entries.append(trade)
        symbol = trade.get("symbol") or "UNKNOWN"
        timeframe = trade.get("timeframe") or "unknown"
        setup_variant = trade.get("setup_variant") or "base"

        if declared_universe and symbol not in declared_universe:
            continue
        if declared_timeframes and timeframe not in declared_timeframes:
            continue
        if declared_variants and setup_variant not in declared_variants:
            continue
        scoped_entries.append(trade)

    if not aggregate_entries:
        aggregate_existing_state = str(aggregate_card.get("governance_state") or "")
        aggregate_existing_promotion = str(aggregate_card.get("promotion_state") or "")
        for card in strategy_symbol_cards.values():
            _reset_trade_metrics(card)
            _recompute(card)
        for card in strategy_context_cards.values():
            _reset_trade_metrics(card)
            _recompute(card)
        if aggregate_existing_state in {"frozen", "retired"}:
            aggregate_card["governance_state"] = aggregate_existing_state
            aggregate_card["promotion_state"] = aggregate_existing_promotion or aggregate_existing_state
            aggregate_card["freeze_recommended"] = aggregate_existing_state == "frozen"
            aggregate_card["promote_candidate"] = False
            aggregate_card["watch_recommended"] = False
        else:
            _reset_trade_metrics(aggregate_card)
            _recompute(aggregate_card)
        return

    _reset_trade_metrics(aggregate_card)
    for card in strategy_symbol_cards.values():
        _reset_trade_metrics(card)
    for card in strategy_context_cards.values():
        _reset_trade_metrics(card)

    for trade in aggregate_entries:
        _append_trade_metrics(aggregate_card, trade)

    for trade in scoped_entries:
        symbol = trade.get("symbol") or "UNKNOWN"
        timeframe = trade.get("timeframe") or "unknown"
        setup_variant = trade.get("setup_variant") or "base"

        symbol_key = _symbol_key(strategy, symbol)
        if symbol_key not in symbol_scorecards:
            symbol_scorecards[symbol_key] = _blank_symbol_scorecard(strategy, symbol)
            strategy_symbol_cards[symbol_key] = symbol_scorecards[symbol_key]
        context_key = _context_key(strategy, symbol, timeframe, setup_variant)
        if context_key not in context_scorecards:
            context_scorecards[context_key] = _blank_context_scorecard(strategy, symbol, timeframe, setup_variant)
            strategy_context_cards[context_key] = context_scorecards[context_key]

        _append_trade_metrics(strategy_symbol_cards[symbol_key], trade)
        _append_trade_metrics(strategy_context_cards[context_key], trade)

    for card in strategy_symbol_cards.values():
        _recompute(card)
    for card in strategy_context_cards.values():
        _recompute(card)
    _recompute(aggregate_card)


def _recompute(card: Dict):
    wins = int(card.get("wins", 0) or 0)
    losses = int(card.get("losses", 0) or 0)
    resolved = int(card.get("entries_resolved", 0) or 0)
    gross_profit = float(card.get("gross_profit", 0.0) or 0.0)
    gross_loss = abs(float(card.get("gross_loss", 0.0) or 0.0))
    net_pnl = float(card.get("net_pnl", 0.0) or 0.0)

    card["win_rate"] = round((wins / resolved), 4) if resolved else 0.0
    card["avg_win"] = round((gross_profit / wins), 4) if wins else 0.0
    card["avg_loss"] = round((gross_loss / losses), 4) if losses else 0.0
    loss_rate = (losses / resolved) if resolved else 0.0
    card["expectancy"] = round((card["win_rate"] * card["avg_win"]) - (loss_rate * card["avg_loss"]), 4)
    card["profit_factor"] = round((gross_profit / gross_loss), 4) if gross_loss else (round(gross_profit, 4) if gross_profit else 0.0)

    min_resolved = float(card.get("success_criteria", {}).get("min_resolved_trades", _cfg.AUTONOMY_CONFIG.get("utility_min_resolved_sample", 20)) or 20)
    card["sample_quality"] = round(min(resolved / max(min_resolved, 1.0), 1.0), 4)

    recent = card.get("recent_5_outcomes", [])[-5:]
    if recent:
        recent_win_rate = sum(1 for item in recent if item.get("result") == "win") / len(recent)
        stability = 1.0 - abs(recent_win_rate - card["win_rate"])
    else:
        stability = 0.0
    expectancy_component = 0.5 if card["expectancy"] > 0 else 0.0
    card["consistency_score"] = round((card["sample_quality"] * 0.5) + (stability * 0.3) + (expectancy_component * 0.2), 4)

    min_expectancy = float(card.get("success_criteria", {}).get("min_expectancy", 0.0) or 0.0)
    min_win_rate = float(card.get("success_criteria", {}).get("min_win_rate", 0.0) or 0.0)
    probation_min_resolved = int(
        card.get("success_criteria", {}).get(
            "probation_min_resolved_trades",
            _cfg.AUTONOMY_CONFIG.get("probation_min_resolved_trades", 5),
        ) or 5
    )
    negative_floor = -abs(max(min_expectancy, 0.05))
    severe_negative_floor = negative_floor * 2.0

    # P5-05: Retired strategies stay retired — never override.
    existing_state = str(card.get("governance_state") or "")
    if existing_state == "retired":
        card["promotion_state"] = "retired"
        card["freeze_recommended"] = False
        card["promote_candidate"] = False
        card["watch_recommended"] = False
        card["min_expectancy_required"] = round(min_expectancy, 4)
        card["min_win_rate_required"] = round(min_win_rate, 4)
        card["negative_expectancy_floor"] = round(negative_floor, 4)
        card["net_pnl"] = round(net_pnl, 4)
        return

    # P5-05: Manual freeze (has freeze_reason) — don't let recompute
    # override until expectancy has genuinely recovered above the severe
    # negative floor.  This prevents the race where a single lucky trade
    # reverses the drawdown-based freeze prematurely.
    # P5-06: Also enforce a minimum cooling period before unfreezing.
    # P8-01: Deadlock-unfrozen strategies get a grace period (default 3 days)
    #        where _recompute will NOT re-freeze them, so they can accumulate
    #        new trade data.
    _deadlock_grace = False
    _dl_unfreeze = card.get("deadlock_unfreeze_utc")
    if _dl_unfreeze:
        from datetime import timedelta
        _grace_days = int(_cfg.AUTONOMY_CONFIG.get("deadlock_unfreeze_grace_days", 3))
        try:
            _dl_dt = datetime.fromisoformat(str(_dl_unfreeze).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < _dl_dt + timedelta(days=_grace_days):
                _deadlock_grace = True
        except (ValueError, TypeError):
            log.debug("unparseable deadlock_unfreeze_utc: %s", _dl_unfreeze)

    if card.get("freeze_reason") and existing_state == "frozen":
        if _deadlock_grace:
            # P8-01: Deadlock grace overrides freeze — let it trade
            card.pop("freeze_reason", None)
            card.pop("freeze_utc", None)
            governance_state = None  # will be set to paper_active below
        elif card["expectancy"] <= severe_negative_floor:
            # Still bad — keep frozen, skip governance reassignment
            governance_state = "frozen"
        else:
            # Expectancy recovered — but check minimum cooling period.
            from datetime import timedelta
            min_days = int(_cfg.AUTONOMY_CONFIG.get("unfreeze_min_frozen_days", 3))
            freeze_utc = card.get("freeze_utc")
            still_cooling = False
            if freeze_utc and min_days > 0:
                try:
                    freeze_dt = datetime.fromisoformat(
                        str(freeze_utc).replace("Z", "+00:00")
                    )
                    cooldown_end = freeze_dt + timedelta(days=min_days)
                    if datetime.now(timezone.utc) < cooldown_end:
                        still_cooling = True
                except (ValueError, TypeError) as exc:
                    log.debug("Malformed freeze_utc %r, allowing unfreeze: %s", freeze_utc, exc)
            if still_cooling:
                governance_state = "frozen"
            else:
                # Clear the manual freeze and let
                # the normal transition logic run below.
                card.pop("freeze_reason", None)
                card.pop("freeze_utc", None)
                governance_state = None  # sentinel — will be set below
    else:
        governance_state = None

    if governance_state != "frozen":
        if resolved == 0:
            governance_state = "paper_candidate"
        elif resolved < probation_min_resolved:
            governance_state = "paper_probe"
        elif resolved < 3 and card["expectancy"] <= negative_floor:
            governance_state = "paper_probe"
        elif card["expectancy"] <= severe_negative_floor:
            # P-OP32g: Don't freeze strategies that haven't reached the
            # minimum adaptation sample — expectancy is too noisy with few
            # trades. Let them accumulate data before judging.
            _min_adapt = int(_cfg.SIGNAL_THRESHOLD_MIN_SAMPLE)
            if _deadlock_grace:
                # P8-01: Don't re-freeze during deadlock unfreeze grace period
                governance_state = "paper_active"
            elif resolved < _min_adapt and existing_state != "frozen":
                governance_state = "paper_probe"  # keep probing, don't freeze yet
            else:
                governance_state = "frozen"
        elif card["sample_quality"] >= 1.0 and card["expectancy"] >= min_expectancy and card["win_rate"] >= min_win_rate:
            governance_state = "promote_candidate"
        elif card["sample_quality"] >= 0.5 and card["expectancy"] > 0:
            governance_state = "paper_watch"
        elif card["sample_quality"] < 1.0:
            governance_state = "paper_active"
        else:
            governance_state = "paper_watch"

    card["promotion_state"] = governance_state
    card["governance_state"] = governance_state
    card["freeze_recommended"] = governance_state == "frozen"
    card["promote_candidate"] = governance_state == "promote_candidate"
    card["watch_recommended"] = governance_state == "paper_watch"
    card["min_expectancy_required"] = round(min_expectancy, 4)
    card["min_win_rate_required"] = round(min_win_rate, 4)
    card["negative_expectancy_floor"] = round(negative_floor, 4)

    card["net_pnl"] = round(net_pnl, 4)


def unfreeze_eligible_strategies(scorecards: Dict[str, Dict]) -> List[str]:
    """Proactively unfreeze strategies whose conditions have improved.

    Scans all frozen (non-retired) aggregate scorecards and runs
    ``_recompute()`` which will clear manual freezes if:
    1. Expectancy has recovered above the severe negative floor
    2. The minimum cooling period (``unfreeze_min_frozen_days``) has elapsed

    For computed freezes (no ``freeze_reason``), ``_recompute()`` will
    transition out of frozen if the expectancy is no longer severely
    negative.

    Returns a list of strategy IDs that were unfrozen in this call.
    """
    unfrozen_ids: List[str] = []
    for strategy_id, card in scorecards.items():
        if str(card.get("governance_state") or "") != "frozen":
            continue
        # Save the state before recompute
        _recompute(card)
        if str(card.get("governance_state") or "") != "frozen":
            unfrozen_ids.append(strategy_id)
    return unfrozen_ids


def force_unfreeze_best_frozen(scorecards: Dict[str, Dict]) -> str | None:
    """P8-02: Force-unfreeze the best frozen (non-retired) strategy.

    Used by the ``break_system_deadlock`` action when ALL strategies are
    frozen and the system cannot make progress.  Selects the frozen
    strategy with the highest ``rank_score`` (or fewest losses), clears
    its freeze state, and returns it to ``paper_active``.

    Returns the ``strategy_id`` that was unfrozen, or ``None``.
    """
    candidates: List[tuple] = []
    for strategy_id, card in scorecards.items():
        gov = str(card.get("governance_state") or "")
        if gov not in ("frozen",):
            continue
        # Skip retired/archived — those are terminal
        if card.get("archive_state") == "archived_refuted":
            continue
        if gov == "retired":
            continue
        # Rank by: positive expectancy preferred, then fewer resolved trades
        # (small sample = still worth trying), then recency
        score = float(card.get("expectancy", 0.0) or 0.0)
        resolved = int(card.get("entries_resolved", 0) or 0)
        # Strategies with small samples get a bonus — they haven't been
        # proven wrong with enough data yet
        if resolved < 15:
            score += 0.5
        candidates.append((score, -resolved, strategy_id, card))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    _, _, best_id, best_card = candidates[0]

    # Force unfreeze
    best_card.pop("freeze_reason", None)
    best_card.pop("freeze_utc", None)
    best_card["governance_state"] = "paper_active"
    best_card["promotion_state"] = "paper_active"
    best_card["freeze_recommended"] = False
    best_card["deadlock_unfreeze_utc"] = _utc_now()
    log.info(
        "P8-02: Force-unfroze strategy %s (expectancy=%.4f, resolved=%d) "
        "to break system deadlock.",
        best_id,
        float(best_card.get("expectancy", 0.0) or 0.0),
        int(best_card.get("entries_resolved", 0) or 0),
    )
    return best_id


def retire_frozen_strategies(scorecards: Dict[str, Dict]) -> List[str]:
    """Auto-retire strategies frozen longer than ``retirement_frozen_days``.

    Iterates *scorecards* (aggregate tier) in-place.  A strategy is
    eligible for retirement when:

    1. ``governance_state == "frozen"``
    2. It has a ``freeze_utc`` timestamp older than
       ``_cfg.AUTONOMY_CONFIG["retirement_frozen_days"]`` days ago.

    Retired strategies get ``governance_state = "retired"`` and
    ``promotion_state = "retired"``, plus an ``archive_state`` field set
    to ``"archived_refuted"`` and ``retired_utc`` timestamp.  The
    ``_recompute()`` short-circuit ensures this state is never
    overridden.

    Returns a list of strategy IDs that were retired in this call.
    """
    from datetime import timedelta

    retirement_days = int(_cfg.AUTONOMY_CONFIG.get("retirement_frozen_days", 14))
    cutoff = datetime.now(timezone.utc) - timedelta(days=retirement_days)
    retired_ids: List[str] = []

    for strategy_id, card in scorecards.items():
        if str(card.get("governance_state") or "") != "frozen":
            continue
        if str(card.get("governance_state") or "") == "retired":
            continue  # already retired

        freeze_utc = card.get("freeze_utc")
        if not freeze_utc:
            # No timestamp — stamp one now so the clock starts ticking,
            # but don't retire yet.
            card["freeze_utc"] = _utc_now()
            continue

        try:
            freeze_dt = datetime.fromisoformat(str(freeze_utc).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            card["freeze_utc"] = _utc_now()
            continue

        if freeze_dt <= cutoff:
            card["governance_state"] = "retired"
            card["promotion_state"] = "retired"
            card["archive_state"] = "archived_refuted"
            card["retired_utc"] = _utc_now()
            card["retirement_reason"] = (
                f"auto_retired_frozen_{retirement_days}d"
            )
            retired_ids.append(strategy_id)

    return retired_ids


def ensure_scorecards(strategies: List[Dict], prune_stale: bool = True) -> Dict:
    payload = read_json(SCORECARDS_PATH, {
        "schema_version": "strategy_scorecards_v2",
        "updated_utc": _utc_now(),
        "scorecards": {},
        "symbol_scorecards": {},
        "context_scorecards": {},
    })
    ledger_payload = read_json(_ledger_path(), {"entries": []})
    ledger_entries = ledger_payload.get("entries", []) if isinstance(ledger_payload, dict) else []
    payload["schema_version"] = "strategy_scorecards_v3"
    scorecards = payload.setdefault("scorecards", {})
    symbol_scorecards = payload.setdefault("symbol_scorecards", {})
    context_scorecards = payload.setdefault("context_scorecards", {})
    if prune_stale:
        valid_ids = {s["strategy_id"] for s in strategies if s.get("strategy_id")}
        # P5-08: Build exact valid keys for symbol/context scorecards.
        # Strategies with a declared universe prune to exactly those symbols.
        # Strategies without a universe keep all symbols (prefix match).
        valid_symbol_keys: set = set()
        strats_with_universe: set = set()  # strategy_ids that have explicit universe
        for s in strategies:
            sid = s.get("strategy_id")
            venue = s.get("venue")
            if not sid or not venue:
                continue
            universe = s.get("universe")
            if universe:
                strats_with_universe.add(sid)
                for symbol in universe:
                    valid_symbol_keys.add(f"{venue}::{sid}::{symbol}")
        # For strategies WITHOUT a declared universe, keep by id prefix
        id_prefixes_no_universe = {
            f'{s["venue"]}::{s["strategy_id"]}::'
            for s in strategies
            if s.get("strategy_id") and s.get("venue") and s["strategy_id"] not in strats_with_universe
        }

        for stale_key in list(scorecards.keys()):
            if stale_key not in valid_ids:
                scorecards.pop(stale_key, None)
        for stale_key in list(symbol_scorecards.keys()):
            if stale_key in valid_symbol_keys:
                continue
            if any(stale_key.startswith(p) for p in id_prefixes_no_universe):
                continue
            symbol_scorecards.pop(stale_key, None)
        for stale_key in list(context_scorecards.keys()):
            # Context key = venue::sid::symbol::tf::variant
            # Valid if its symbol prefix (venue::sid::symbol) is valid
            ctx_symbol_prefix = "::".join(stale_key.split("::")[:3])
            if ctx_symbol_prefix in valid_symbol_keys:
                continue
            if any(stale_key.startswith(p) for p in id_prefixes_no_universe):
                continue
            context_scorecards.pop(stale_key, None)
    for strategy in strategies:
        strategy_id = strategy["strategy_id"]
        if strategy_id not in scorecards:
            scorecards[strategy_id] = _blank_scorecard(strategy)
        else:
            scorecards[strategy_id]["family"] = strategy.get("family")
            scorecards[strategy_id]["venue"] = strategy.get("venue")
            scorecards[strategy_id]["linked_hypotheses"] = strategy.get("linked_hypotheses", [])
            scorecards[strategy_id]["success_criteria"] = strategy.get("success_criteria", {})
        for symbol in strategy.get("universe", []):
            symbol_key = _symbol_key(strategy, symbol)
            if symbol_key not in symbol_scorecards:
                symbol_scorecards[symbol_key] = _blank_symbol_scorecard(strategy, symbol)
            else:
                symbol_scorecards[symbol_key]["family"] = strategy.get("family")
                symbol_scorecards[symbol_key]["venue"] = strategy.get("venue")
                symbol_scorecards[symbol_key]["status"] = strategy.get("status", "paper_candidate")
                symbol_scorecards[symbol_key]["linked_hypotheses"] = strategy.get("linked_hypotheses", [])
                symbol_scorecards[symbol_key]["success_criteria"] = strategy.get("success_criteria", {})
                symbol_scorecards[symbol_key]["symbol"] = symbol
                _recompute(symbol_scorecards[symbol_key])
            for timeframe in strategy.get("timeframes", []):
                for setup_variant in strategy.get("setup_variants", ["base"]):
                    context_key = _context_key(strategy, symbol, timeframe, setup_variant)
                    if context_key not in context_scorecards:
                        context_scorecards[context_key] = _blank_context_scorecard(strategy, symbol, timeframe, setup_variant)
                    else:
                        context_scorecards[context_key]["family"] = strategy.get("family")
                        context_scorecards[context_key]["venue"] = strategy.get("venue")
                        context_scorecards[context_key]["status"] = strategy.get("status", "paper_candidate")
                        context_scorecards[context_key]["linked_hypotheses"] = strategy.get("linked_hypotheses", [])
                        context_scorecards[context_key]["success_criteria"] = strategy.get("success_criteria", {})
                        context_scorecards[context_key]["symbol"] = symbol
                        context_scorecards[context_key]["timeframe"] = timeframe
                        context_scorecards[context_key]["setup_variant"] = setup_variant
                        _recompute(context_scorecards[context_key])
        _sync_strategy_from_ledger(
            strategy,
            scorecards[strategy_id],
            symbol_scorecards,
            context_scorecards,
            ledger_entries,
        )
    # P5-06: Proactively unfreeze strategies whose conditions improved.
    unfreeze_eligible_strategies(scorecards)
    # P5-05: Auto-retire strategies frozen longer than threshold.
    retire_frozen_strategies(scorecards)
    payload["updated_utc"] = _utc_now()
    write_json(SCORECARDS_PATH, payload)
    return payload


def update_strategy_scorecard(strategy: Dict, trade: Dict) -> Dict:
    payload = ensure_scorecards([strategy], prune_stale=False)
    scorecards = payload["scorecards"]
    symbol_scorecards = payload.setdefault("symbol_scorecards", {})
    card = scorecards[strategy["strategy_id"]]
    symbol = trade.get("symbol") or "UNKNOWN"
    timeframe = trade.get("timeframe") or "unknown"
    setup_variant = trade.get("setup_variant") or "base"
    symbol_key = _symbol_key(strategy, symbol)
    symbol_card = symbol_scorecards.setdefault(symbol_key, _blank_symbol_scorecard(strategy, symbol))
    context_scorecards = payload.setdefault("context_scorecards", {})
    context_key = _context_key(strategy, symbol, timeframe, setup_variant)
    context_card = context_scorecards.setdefault(context_key, _blank_context_scorecard(strategy, symbol, timeframe, setup_variant))
    trade_timestamp = str(trade.get("timestamp") or "")

    # P-OP31d: Idempotency guard — ensure_scorecards() already syncs from
    # signal_paper_execution_ledger. If this trade is present there, avoid
    # counting it again.
    if trade_timestamp:
        ledger_entries = read_json(_ledger_path(), {"entries": []}).get("entries", [])
        for row in reversed(ledger_entries[-300:]):
            if (
                str(row.get("strategy_id") or "") == str(strategy.get("strategy_id") or "")
                and str(row.get("venue") or "") == str(strategy.get("venue") or "")
                and str(row.get("timestamp") or "") == trade_timestamp
                and str(row.get("symbol") or "") == symbol
                and str(row.get("timeframe") or "") == timeframe
                and str(row.get("setup_variant") or "base") == setup_variant
            ):
                return {
                    "aggregate": card,
                    "symbol": symbol_card,
                    "context": context_card,
                }

    profit = float(trade.get("profit", 0.0) or 0.0)
    result = trade.get("result")
    resolved = bool(trade.get("resolved", True))
    trade_timestamp = trade_timestamp or _utc_now()
    for target_card in (card, symbol_card, context_card):
        target_card["entries_taken"] = int(target_card.get("entries_taken", 0) or 0) + 1
        if resolved:
            target_card["entries_resolved"] = int(target_card.get("entries_resolved", 0) or 0) + 1
        else:
            target_card["entries_open"] = int(target_card.get("entries_open", 0) or 0) + 1

        if resolved and result == "win":
            target_card["wins"] = int(target_card.get("wins", 0) or 0) + 1
            target_card["gross_profit"] = round(float(target_card.get("gross_profit", 0.0) or 0.0) + profit, 4)
            target_card["largest_win"] = max(float(target_card.get("largest_win", 0.0) or 0.0), profit)
        elif resolved and result == "loss":
            target_card["losses"] = int(target_card.get("losses", 0) or 0) + 1
            target_card["gross_loss"] = round(float(target_card.get("gross_loss", 0.0) or 0.0) + abs(profit), 4)
            target_card["largest_loss"] = max(float(target_card.get("largest_loss", 0.0) or 0.0), abs(profit))
        elif resolved:
            target_card["draws"] = int(target_card.get("draws", 0) or 0) + 1

        if resolved:
            target_card["net_pnl"] = round(float(target_card.get("net_pnl", 0.0) or 0.0) + profit, 4)
        recent = list(target_card.get("recent_5_outcomes", []))
        recent.append({
            "timestamp": trade_timestamp,
            "symbol": symbol,
            "direction": trade.get("direction"),
            "result": result,
            "profit": profit,
            "resolved": resolved,
        })
        target_card["recent_5_outcomes"] = recent[-5:]
        target_card["last_trade_utc"] = trade_timestamp
        _recompute(target_card)

    payload["updated_utc"] = _utc_now()
    write_json(SCORECARDS_PATH, payload)
    return {
        "aggregate": card,
        "symbol": symbol_card,
        "context": context_card,
    }


def read_scorecards() -> Dict:
    return read_json(SCORECARDS_PATH, {
        "schema_version": "strategy_scorecards_v3",
        "updated_utc": None,
        "scorecards": {},
        "symbol_scorecards": {},
        "context_scorecards": {},
    })
