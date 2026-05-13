"""
Brain V9 - Strategy archive
Clasifica estrategias activas, en prueba y refutadas.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

ARCHIVE_PATH = ENGINE_PATH / "strategy_archive_latest.json"
log = logging.getLogger("strategy_archive")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_strategy_archive(strategies: List[Dict[str, Any]], scorecards: Dict[str, Any], hypothesis_results: Dict[str, Any]) -> Dict[str, Any]:
    strategy_cards = scorecards.get("scorecards", {}) or {}
    hypothesis_index = {
        item.get("strategy_id"): item
        for item in hypothesis_results.get("results", [])
        if isinstance(item, dict)
    }
    archived: List[Dict[str, Any]] = []
    active: List[Dict[str, Any]] = []
    watchlist: List[Dict[str, Any]] = []
    testing: List[Dict[str, Any]] = []

    for strategy in strategies:
        strategy_id = strategy.get("strategy_id")
        card = strategy_cards.get(strategy_id, {})
        hypothesis = hypothesis_index.get(strategy_id, {})
        resolved = int(card.get("entries_resolved", 0) or 0)
        expectancy = float(card.get("expectancy", 0.0) or 0.0)
        state = str(card.get("governance_state") or card.get("promotion_state") or "paper_candidate")
        min_resolved = int(strategy.get("success_criteria", {}).get("min_resolved_trades", 20) or 20)
        archive_reason = None

        if state == "frozen" and resolved >= min_resolved and expectancy <= 0:
            archive_reason = "refuted_after_minimum_sample"
        elif hypothesis.get("status") == "fail" and resolved >= max(10, min_resolved // 2):
            archive_reason = "hypothesis_failed_with_material_sample"

        item = {
            "strategy_id": strategy_id,
            "venue": strategy.get("venue"),
            "family": strategy.get("family"),
            "governance_state": state,
            "entries_resolved": resolved,
            "expectancy": expectancy,
            "hypothesis_status": hypothesis.get("status"),
        }

        if archive_reason:
            item["archive_state"] = "archived_refuted"
            item["archive_reason"] = archive_reason
            archived.append(item)
        elif state in {"paper_active", "promote_candidate"}:
            item["archive_state"] = "active"
            active.append(item)
        elif state == "paper_watch":
            item["archive_state"] = "watch"
            watchlist.append(item)
        else:
            item["archive_state"] = "testing"
            testing.append(item)

    payload = {
        "schema_version": "strategy_archive_v1",
        "generated_utc": _utc_now(),
        "archived": archived,
        "active": active,
        "watchlist": watchlist,
        "testing": testing,
        "summary": {
            "archived_count": len(archived),
            "active_count": len(active),
            "watch_count": len(watchlist),
            "testing_count": len(testing),
        },
    }
    write_json(ARCHIVE_PATH, payload)
    return payload


def read_strategy_archive() -> Dict[str, Any]:
    return read_json(ARCHIVE_PATH, {
        "schema_version": "strategy_archive_v1",
        "generated_utc": None,
        "archived": [],
        "active": [],
        "watchlist": [],
        "testing": [],
        "summary": {},
    })
