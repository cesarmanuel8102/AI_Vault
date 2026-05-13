"""
Brain V9 - Post-trade analysis snapshot

Builds a canonical summary from the signal paper execution ledger so that
LLM-assisted analysis and hypothesis generation can consume a stable,
auditable packet instead of scraping multiple artifacts ad hoc.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
LEDGER_PATH = ENGINE_PATH / "signal_paper_execution_ledger.json"
EDGE_PATH = ENGINE_PATH / "edge_validation_latest.json"
RANKING_PATH = ENGINE_PATH / "strategy_ranking_v2_latest.json"
OUTPUT_PATH = ENGINE_PATH / "post_trade_analysis_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _is_resolved(entry: Dict[str, Any]) -> bool:
    return bool(entry.get("resolved")) or str(entry.get("result")) in {"win", "loss", "draw"}


def _group_duplicates(entries: List[Dict[str, Any]], window_seconds: int = 2) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        key = (
            entry.get("strategy_id"),
            entry.get("venue"),
            entry.get("symbol"),
            entry.get("direction"),
            round(_safe_float(entry.get("entry_price")), 5),
        )
        grouped[key].append(entry)

    anomalies: List[Dict[str, Any]] = []
    for key, rows in grouped.items():
        rows = sorted(rows, key=lambda x: _parse_ts(x.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
        cluster: List[Dict[str, Any]] = []
        cluster_start: datetime | None = None
        for row in rows:
            ts = _parse_ts(row.get("timestamp"))
            if ts is None:
                continue
            if cluster_start is None:
                cluster = [row]
                cluster_start = ts
                continue
            delta = (ts - cluster_start).total_seconds()
            if delta <= window_seconds:
                cluster.append(row)
            else:
                if len(cluster) > 1:
                    anomalies.append(_build_duplicate_anomaly(cluster, key, window_seconds))
                cluster = [row]
                cluster_start = ts
        if len(cluster) > 1:
            anomalies.append(_build_duplicate_anomaly(cluster, key, window_seconds))
    return anomalies


def _build_duplicate_anomaly(cluster: List[Dict[str, Any]], key: Tuple[Any, ...], window_seconds: int) -> Dict[str, Any]:
    strategy_id, venue, symbol, direction, entry_price = key
    timestamps = [row.get("timestamp") for row in cluster]
    return {
        "type": "duplicate_execution_burst",
        "strategy_id": strategy_id,
        "venue": venue,
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "count": len(cluster),
        "window_seconds": window_seconds,
        "timestamps": timestamps,
    }


def _summarize_by(entries: List[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[str(entry.get(field) or "unknown")].append(entry)

    results = []
    for key, rows in grouped.items():
        wins = sum(1 for row in rows if row.get("result") == "win")
        losses = sum(1 for row in rows if row.get("result") == "loss")
        profit = round(sum(_safe_float(row.get("profit")) for row in rows), 4)
        resolved = len(rows)
        results.append({
            field: key,
            "resolved": resolved,
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / resolved) if resolved else 0.0, 4),
            "net_profit": profit,
            "avg_profit": round((profit / resolved) if resolved else 0.0, 4),
        })
    results.sort(key=lambda row: (row["resolved"], row["net_profit"]), reverse=True)
    return results


def _duration_bucket(entry: Dict[str, Any]) -> str:
    """Classify trade duration into operational buckets."""
    ts = _parse_ts(entry.get("timestamp"))
    resolved = _parse_ts(entry.get("resolved_utc"))
    if ts is None or resolved is None:
        return "unknown"
    seconds = (resolved - ts).total_seconds()
    if seconds < 0:
        return "unknown"
    if seconds <= 120:
        return "ultra_short_<=2m"
    if seconds <= 600:
        return "short_2m-10m"
    if seconds <= 3600:
        return "medium_10m-1h"
    return "long_>1h"


def _payout_bucket(entry: Dict[str, Any]) -> str:
    """Classify payout into operational buckets (PO-relevant)."""
    payout = _safe_float(entry.get("entry_payout_pct"), -1)
    if payout < 0:
        return "no_payout"
    if payout < 60:
        return "low_<60%"
    if payout < 75:
        return "mid_60-75%"
    if payout < 85:
        return "good_75-85%"
    return "excellent_>=85%"


def build_post_trade_analysis_snapshot(limit: int = 100) -> Dict[str, Any]:
    ledger = read_json(LEDGER_PATH, {"entries": []})
    edge = read_json(EDGE_PATH, {})
    ranking = read_json(RANKING_PATH, {})

    entries = ledger.get("entries") or []
    resolved = [entry for entry in entries if isinstance(entry, dict) and _is_resolved(entry)]
    resolved = sorted(
        resolved,
        key=lambda x: _parse_ts(x.get("resolved_utc") or x.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    recent = resolved[: max(1, int(limit))]

    duplicate_anomalies = _group_duplicates(recent)
    by_strategy = _summarize_by(recent, "strategy_id")
    by_venue = _summarize_by(recent, "venue")
    by_symbol = _summarize_by(recent, "symbol")

    # Fase 3.1: additional context dimensions
    by_setup_variant = _summarize_by(recent, "setup_variant")

    # Duration buckets (computed, not a raw field)
    for entry in recent:
        entry["_duration_bucket"] = _duration_bucket(entry)
    by_duration = _summarize_by(recent, "_duration_bucket")
    for item in by_duration:
        item["duration_bucket"] = item.pop("_duration_bucket", item.get("duration_bucket"))

    # Payout buckets (computed, not a raw field)
    for entry in recent:
        entry["_payout_bucket"] = _payout_bucket(entry)
    by_payout = _summarize_by(recent, "_payout_bucket")
    for item in by_payout:
        item["payout_bucket"] = item.pop("_payout_bucket", item.get("payout_bucket"))

    # Clean up temporary fields
    for entry in recent:
        entry.pop("_duration_bucket", None)
        entry.pop("_payout_bucket", None)

    total_profit = round(sum(_safe_float(entry.get("profit")) for entry in recent), 4)
    wins = sum(1 for entry in recent if entry.get("result") == "win")
    losses = sum(1 for entry in recent if entry.get("result") == "loss")
    unresolved = sum(1 for entry in entries if isinstance(entry, dict) and not _is_resolved(entry))

    next_focus = "continue_probation"
    if duplicate_anomalies:
        next_focus = "audit_duplicate_execution"
    elif edge.get("summary", {}).get("validated_count", 0) == 0:
        next_focus = "no_validated_edge"
    elif total_profit < 0:
        next_focus = "reduce_lossy_contexts"

    payload = {
        "schema_version": "post_trade_analysis_v1",
        "updated_utc": _utc_now(),
        "summary": {
            "recent_resolved_trades": len(recent),
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / len(recent)) if recent else 0.0, 4),
            "net_profit": total_profit,
            "open_or_unresolved_trades": unresolved,
            "duplicate_anomaly_count": len(duplicate_anomalies),
            "validated_edge_count": edge.get("summary", {}).get("validated_count", 0),
            "probation_count": edge.get("summary", {}).get("probation_count", 0),
            "top_action": ranking.get("top_action"),
            "next_focus": next_focus,
        },
        "recent_trades": recent[:20],
        "by_strategy": by_strategy[:10],
        "by_venue": by_venue[:10],
        "by_symbol": by_symbol[:10],
        "by_setup_variant": by_setup_variant[:10],
        "by_duration": by_duration[:10],
        "by_payout": by_payout[:10],
        "anomalies": duplicate_anomalies[:20],
    }
    write_json(OUTPUT_PATH, payload)
    return payload


def read_post_trade_analysis_snapshot() -> Dict[str, Any]:
    payload = read_json(OUTPUT_PATH, {})
    if payload:
        return payload
    return build_post_trade_analysis_snapshot()
