from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

import brain_v9.config as _cfg
from brain_v9.core.state_io import read_json, write_json
from brain_v9.trading.paper_execution import PAPER_EXECUTION_LEDGER_PATH
from brain_v9.trading.signal_engine import SIGNAL_SNAPSHOT_PATH
from brain_v9.trading.strategy_scorecard import SCORECARDS_PATH


PIPELINE_INTEGRITY_PATH = _cfg.STATE_PATH / "strategy_engine" / "pipeline_integrity_latest.json"
RANKING_V2_PATH = _cfg.STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json"
UTILITY_LATEST_PATH = _cfg.STATE_PATH / "utility_u_latest.json"
AUTONOMY_NEXT_ACTIONS_PATH = _cfg.STATE_PATH / "autonomy_next_actions.json"
PLATFORMS_STATE_PATH = _cfg.STATE_PATH / "platforms"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _seconds_between(older: Any, newer: Any) -> float | None:
    older_dt = _parse_utc(older)
    newer_dt = _parse_utc(newer)
    if older_dt is None or newer_dt is None:
        return None
    return round((newer_dt - older_dt).total_seconds(), 4)


def _latest_timestamp(entries: List[Dict[str, Any]], field: str) -> str | None:
    stamps = [entry.get(field) for entry in entries if entry.get(field)]
    parsed = [item for item in (_parse_utc(stamp) for stamp in stamps) if item is not None]
    if not parsed:
        return None
    return max(parsed).isoformat().replace("+00:00", "Z")


def _trade_identity(entry: Dict[str, Any]) -> str:
    browser_trade_id = str(entry.get("browser_trade_id") or "").strip()
    if browser_trade_id:
        return f"browser:{browser_trade_id}"
    browser_order = entry.get("browser_order") or {}
    order_id = str(browser_order.get("trade_id") or browser_order.get("order_id") or "").strip()
    if order_id:
        return f"browser-order:{order_id}"
    return "core::{strategy_id}::{symbol}::{direction}::{timestamp}::{timeframe}::{setup_variant}".format(
        strategy_id=str(entry.get("strategy_id") or ""),
        symbol=str(entry.get("symbol") or ""),
        direction=str(entry.get("direction") or ""),
        timestamp=str(entry.get("timestamp") or ""),
        timeframe=str(entry.get("timeframe") or ""),
        setup_variant=str(entry.get("setup_variant") or ""),
    )


def _platform_files_status() -> Dict[str, Any]:
    platforms = ("pocket_option", "ibkr", "internal_paper")
    missing: List[str] = []
    files_present: Dict[str, bool] = {}
    for platform in platforms:
        metrics_path = PLATFORMS_STATE_PATH / f"{platform}_metrics.json"
        u_path = PLATFORMS_STATE_PATH / f"{platform}_u.json"
        metrics_ok = metrics_path.exists()
        u_ok = u_path.exists()
        files_present[f"{platform}_metrics"] = metrics_ok
        files_present[f"{platform}_u"] = u_ok
        if not metrics_ok:
            missing.append(str(metrics_path))
        if not u_ok:
            missing.append(str(u_path))
    return {
        "ok": not missing,
        "files_present": files_present,
        "missing_files": missing,
    }


def build_pipeline_integrity_snapshot() -> Dict[str, Any]:
    signal_snapshot = read_json(SIGNAL_SNAPSHOT_PATH, default={})
    ledger = read_json(PAPER_EXECUTION_LEDGER_PATH, default={"entries": []})
    scorecards_payload = read_json(SCORECARDS_PATH, default={})
    ranking = read_json(RANKING_V2_PATH, default={})
    utility = read_json(UTILITY_LATEST_PATH, default={})
    next_actions = read_json(AUTONOMY_NEXT_ACTIONS_PATH, default={})

    signal_items = signal_snapshot.get("items") or []
    ledger_entries = ledger.get("entries") or []
    scorecards = scorecards_payload.get("scorecards") or {}

    resolved_entries = [
        entry for entry in ledger_entries
        if bool(entry.get("resolved")) or str(entry.get("result") or "").lower() in {"win", "loss", "draw"}
    ]
    pending_entries = [
        entry for entry in ledger_entries
        if not bool(entry.get("resolved")) and str(entry.get("result") or "").lower() == "pending_resolution"
    ]
    stale_items = [item for item in signal_items if item.get("is_stale")]
    stale_without_marker = [
        item for item in stale_items
        if "data_too_stale" not in {str(x) for x in (item.get("blockers") or [])}
    ]

    identities = [_trade_identity(entry) for entry in ledger_entries if isinstance(entry, dict)]
    duplicates = {key: count for key, count in Counter(identities).items() if count > 1}

    ledger_resolved_by_strategy = Counter(
        str(entry.get("strategy_id") or "")
        for entry in resolved_entries
        if entry.get("strategy_id")
    )
    aggregate_resolved = sum(int(card.get("entries_resolved", 0) or 0) for card in scorecards.values())
    aggregate_open = sum(int(card.get("entries_open", 0) or 0) for card in scorecards.values())
    aggregate_taken = sum(int(card.get("entries_taken", 0) or 0) for card in scorecards.values())
    scorecard_resolved_by_strategy = {
        str(strategy_id): int((card or {}).get("entries_resolved", 0) or 0)
        for strategy_id, card in scorecards.items()
    }
    reconciled_scorecards_resolved = sum(
        scorecard_resolved_by_strategy.get(strategy_id, 0)
        for strategy_id in ledger_resolved_by_strategy
    )
    orphaned_scorecard_history = {
        strategy_id: {
            "scorecards_resolved": scorecard_resolved_by_strategy.get(strategy_id, 0),
            "governance_state": str((scorecards.get(strategy_id) or {}).get("governance_state") or ""),
            "last_trade_utc": (scorecards.get(strategy_id) or {}).get("last_trade_utc"),
        }
        for strategy_id in scorecards
        if scorecard_resolved_by_strategy.get(strategy_id, 0) > 0
        and ledger_resolved_by_strategy.get(strategy_id, 0) == 0
    }
    unresolved_strategy_mismatches = {
        strategy_id: {
            "ledger_resolved": ledger_resolved_by_strategy.get(strategy_id, 0),
            "scorecards_resolved": scorecard_resolved_by_strategy.get(strategy_id, 0),
        }
        for strategy_id in ledger_resolved_by_strategy
        if ledger_resolved_by_strategy.get(strategy_id, 0) != scorecard_resolved_by_strategy.get(strategy_id, 0)
    }

    latest_signal_utc = signal_snapshot.get("generated_utc")
    latest_execution_utc = _latest_timestamp(ledger_entries, "timestamp")
    latest_resolved_utc = _latest_timestamp(resolved_entries, "resolved_utc") or _latest_timestamp(resolved_entries, "timestamp")
    scorecards_updated_utc = scorecards_payload.get("updated_utc")
    utility_updated_utc = utility.get("updated_utc")
    decision_updated_utc = next_actions.get("updated_utc")

    scorecard_lag_seconds = _seconds_between(latest_resolved_utc, scorecards_updated_utc) if latest_resolved_utc else None
    utility_lag_seconds = _seconds_between(scorecards_updated_utc, utility_updated_utc) if scorecards_updated_utc else None
    decision_lag_seconds = _seconds_between(utility_updated_utc, decision_updated_utc) if utility_updated_utc else None

    scorecards_fresh = scorecard_lag_seconds is None or scorecard_lag_seconds >= 0
    utility_fresh = utility_lag_seconds is None or utility_lag_seconds >= 0
    decision_fresh = decision_lag_seconds is None or decision_lag_seconds >= 0

    pending_vs_open_match = aggregate_open == len(pending_entries)
    resolved_vs_scorecard_match = not unresolved_strategy_mismatches
    taken_consistent = aggregate_taken == aggregate_resolved + aggregate_open

    platform_files = _platform_files_status()
    ledger_venues = sorted({str(entry.get("venue") or "") for entry in ledger_entries if entry.get("venue")})
    scorecard_venues = sorted({str(card.get("venue") or "") for card in scorecards.values() if card.get("venue")})
    venue_sets_match = set(ledger_venues).issubset(set(scorecard_venues) | {"internal_paper_simulator"})

    anomalies: List[Dict[str, Any]] = []

    def add_anomaly(severity: str, code: str, message: str, **extra: Any) -> None:
        payload = {"severity": severity, "code": code, "message": message}
        if extra:
            payload.update(extra)
        anomalies.append(payload)

    if duplicates:
        add_anomaly(
            "critical",
            "duplicate_trade_detected",
            "Se detectaron trades duplicados en el ledger canónico.",
            duplicate_keys=duplicates,
        )
    if not pending_vs_open_match:
        add_anomaly(
            "critical",
            "pending_resolution_mismatch",
            "Los trades pending del ledger no coinciden con entries_open de scorecards.",
            ledger_pending=len(pending_entries),
            scorecards_open=aggregate_open,
        )
    if not resolved_vs_scorecard_match:
        add_anomaly(
            "critical",
            "resolved_count_mismatch",
            "Los trades resueltos del ledger no coinciden con entries_resolved de scorecards.",
            ledger_resolved=len(resolved_entries),
            scorecards_resolved=reconciled_scorecards_resolved,
            affected_strategies=unresolved_strategy_mismatches,
        )
    if orphaned_scorecard_history:
        orphaned_is_critical = any(
            str(item.get("governance_state") or "") not in {"frozen", "retired"}
            for item in orphaned_scorecard_history.values()
        )
        add_anomaly(
            "critical" if orphaned_is_critical else "warning",
            "orphaned_scorecard_history",
            "Hay scorecards con historial resuelto sin footprint correspondiente en el ledger canónico.",
            affected_strategies=orphaned_scorecard_history,
            orphaned_resolved_total=sum(
                int(item.get("scorecards_resolved", 0) or 0)
                for item in orphaned_scorecard_history.values()
            ),
        )
    if not taken_consistent:
        add_anomaly(
            "critical",
            "scorecard_taken_mismatch",
            "entries_taken no coincide con resolved + open en scorecards.",
            scorecards_taken=aggregate_taken,
            scorecards_resolved=aggregate_resolved,
            scorecards_open=aggregate_open,
        )
    if stale_without_marker:
        add_anomaly(
            "warning",
            "stale_signal_not_marked",
            "Hay señales stale sin blocker explícito data_too_stale.",
            affected_signals=len(stale_without_marker),
        )
    if not scorecards_fresh:
        add_anomaly(
            "critical",
            "scorecards_stale_after_resolution",
            "Scorecards no quedaron frescos después de la última resolución.",
            latest_resolved_utc=latest_resolved_utc,
            scorecards_updated_utc=scorecards_updated_utc,
            lag_seconds=scorecard_lag_seconds,
        )
    if not utility_fresh:
        add_anomaly(
            "critical",
            "utility_stale_after_scorecards",
            "Utility U no quedó fresca después de actualizar scorecards.",
            scorecards_updated_utc=scorecards_updated_utc,
            utility_updated_utc=utility_updated_utc,
            lag_seconds=utility_lag_seconds,
        )
    if not decision_fresh:
        add_anomaly(
            "critical",
            "decision_stale_after_utility",
            "Autonomy next actions no quedó fresco después de Utility U.",
            utility_updated_utc=utility_updated_utc,
            decision_updated_utc=decision_updated_utc,
            lag_seconds=decision_lag_seconds,
        )
    if not platform_files.get("ok"):
        add_anomaly(
            "warning",
            "platform_state_missing",
            "Faltan archivos de estado independientes por plataforma.",
            missing_files=platform_files.get("missing_files", []),
        )
    if not venue_sets_match:
        add_anomaly(
            "warning",
            "platform_separation_mismatch",
            "Los venues presentes en ledger y scorecards no están alineados.",
            ledger_venues=ledger_venues,
            scorecard_venues=scorecard_venues,
        )

    critical_count = sum(1 for item in anomalies if item["severity"] == "critical")
    warning_count = sum(1 for item in anomalies if item["severity"] == "warning")
    status = "critical" if critical_count else "degraded" if warning_count else "healthy"

    payload = {
        "schema_version": "trading_pipeline_integrity_v1",
        "generated_utc": _utc_now(),
        "pipeline": ["signal", "execution", "ledger", "resolution", "scorecard", "utility", "decision"],
        "paths": {
            "signal_snapshot_path": str(SIGNAL_SNAPSHOT_PATH),
            "ledger_path": str(PAPER_EXECUTION_LEDGER_PATH),
            "scorecards_path": str(SCORECARDS_PATH),
            "ranking_v2_path": str(RANKING_V2_PATH),
            "utility_path": str(UTILITY_LATEST_PATH),
            "decision_path": str(AUTONOMY_NEXT_ACTIONS_PATH),
        },
        "summary": {
            "status": status,
            "pipeline_ok": critical_count == 0,
            "critical_failure_count": critical_count,
            "warning_count": warning_count,
            "anomaly_count": len(anomalies),
            "signals_count": len(signal_items),
            "ledger_entries": len(ledger_entries),
            "resolved_entries": len(resolved_entries),
            "pending_entries": len(pending_entries),
            "duplicate_trade_count": sum(count - 1 for count in duplicates.values()),
            "stale_signal_count": len(stale_items),
            "stale_signal_without_marker_count": len(stale_without_marker),
            "scorecard_resolved_match": resolved_vs_scorecard_match,
            "scorecards_resolved_total": aggregate_resolved,
            "scorecards_resolved_reconciled_total": reconciled_scorecards_resolved,
            "orphaned_scorecard_resolved_total": sum(
                int(item.get("scorecards_resolved", 0) or 0)
                for item in orphaned_scorecard_history.values()
            ),
            "scorecard_open_match": pending_vs_open_match,
            "scorecard_entries_taken_consistent": taken_consistent,
            "scorecards_fresh_after_resolution": scorecards_fresh,
            "utility_fresh_after_scorecards": utility_fresh,
            "decision_fresh_after_utility": decision_fresh,
            "platform_isolation_ok": bool(platform_files.get("ok") and venue_sets_match),
            "last_signal_utc": latest_signal_utc,
            "last_execution_utc": latest_execution_utc,
            "last_resolved_utc": latest_resolved_utc,
            "top_action": next_actions.get("top_action") or ranking.get("top_action"),
        },
        "stages": {
            "signal": {
                "ok": len(stale_without_marker) == 0,
                "generated_utc": latest_signal_utc,
                "items_count": len(signal_items),
                "stale_count": len(stale_items),
                "stale_without_marker_count": len(stale_without_marker),
            },
            "execution": {
                "ok": len(ledger_entries) >= len(resolved_entries),
                "latest_execution_utc": latest_execution_utc,
                "paper_shadow_count": sum(1 for entry in ledger_entries if entry.get("paper_shadow")),
                "browser_confirmed_count": sum(1 for entry in ledger_entries if entry.get("browser_trade_confirmed")),
            },
            "ledger": {
                "ok": not duplicates and pending_vs_open_match and resolved_vs_scorecard_match,
                "entries_count": len(ledger_entries),
                "resolved_count": len(resolved_entries),
                "pending_count": len(pending_entries),
                "duplicate_keys": duplicates,
            },
            "resolution": {
                "ok": len(pending_entries) == 0 or latest_resolved_utc is not None,
                "latest_resolved_utc": latest_resolved_utc,
                "timeout_threshold_seconds": _cfg.PENDING_TRADE_TIMEOUT_SECONDS,
            },
            "scorecard": {
                "ok": scorecards_fresh and pending_vs_open_match and resolved_vs_scorecard_match and taken_consistent,
                "updated_utc": scorecards_updated_utc,
                "entries_resolved_total": aggregate_resolved,
                "entries_resolved_reconciled_total": reconciled_scorecards_resolved,
                "entries_open_total": aggregate_open,
                "entries_taken_total": aggregate_taken,
                "orphaned_scorecard_history": orphaned_scorecard_history,
                "freshness_lag_seconds": scorecard_lag_seconds,
            },
            "utility": {
                "ok": utility_fresh,
                "updated_utc": utility_updated_utc,
                "u_score": utility.get("u_score", utility.get("u_proxy_score")),
                "freshness_lag_seconds": utility_lag_seconds,
            },
            "decision": {
                "ok": decision_fresh,
                "updated_utc": decision_updated_utc,
                "top_action": next_actions.get("top_action"),
                "current_focus": (next_actions.get("current_focus") or {}).get("action"),
                "freshness_lag_seconds": decision_lag_seconds,
            },
            "platform_separation": {
                "ok": bool(platform_files.get("ok") and venue_sets_match),
                "ledger_venues": ledger_venues,
                "scorecard_venues": scorecard_venues,
                "platform_files": platform_files,
            },
        },
        "anomalies": anomalies,
    }
    write_json(PIPELINE_INTEGRITY_PATH, payload)
    return payload


def read_pipeline_integrity_snapshot() -> Dict[str, Any]:
    return read_json(
        PIPELINE_INTEGRITY_PATH,
        default={
            "schema_version": "trading_pipeline_integrity_v1",
            "generated_utc": None,
            "summary": {"status": "unknown", "pipeline_ok": False},
            "stages": {},
            "anomalies": [],
        },
    )
