"""Runtime read-only access to external source learning results.

This module exposes previously generated dry-run learning result artifacts
without regenerating pipelines, writing memory, touching FAISS, or promoting
knowledge.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_RESULTS_OUTPUT_DIR = (
    "tmp_agent/external_source_learning_results_report_dry_run_01_evidence/run_output"
)
MODE = "runtime_readonly_external_knowledge_results"
TOKEN_MARKERS = (
    "github_pat_",
    "ghp_",
    "gho_",
    "Authorization:",
    "Bearer ",
    "FRED_API_KEY",
    "api_key=",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_read_json(path: str) -> Dict[str, Any] | List[Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if isinstance(value, (dict, list)):
        return value
    return {}


def _is_compatible_output_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "learning_results_cards.json").is_file()
        and (path / "learning_results_summary.json").is_file()
    )


def find_latest_learning_results_output(root: str = "tmp_agent") -> str | None:
    preferred = Path(DEFAULT_RESULTS_OUTPUT_DIR)
    if _is_compatible_output_dir(preferred):
        return str(preferred)

    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        return None

    candidates: List[Path] = []
    for cards_path in root_path.rglob("learning_results_cards.json"):
        output_dir = cards_path.parent
        if _is_compatible_output_dir(output_dir):
            candidates.append(output_dir)

    if not candidates:
        return None
    latest = max(candidates, key=lambda p: (p / "learning_results_cards.json").stat().st_mtime)
    return str(latest)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for marker in TOKEN_MARKERS:
            if marker in sanitized:
                sanitized = sanitized.replace(marker, f"{marker.split(':')[0]}REDACTED")
        return sanitized
    return value


def load_learning_results_cards(output_dir: str) -> List[Dict[str, Any]]:
    cards_path = Path(output_dir) / "learning_results_cards.json"
    cards = safe_read_json(str(cards_path))
    if not isinstance(cards, list):
        return []
    return [card for card in _sanitize_value(cards) if isinstance(card, dict)]


def load_learning_results_summary(output_dir: str) -> Dict[str, Any]:
    summary_path = Path(output_dir) / "learning_results_summary.json"
    summary = safe_read_json(str(summary_path))
    if not isinstance(summary, dict):
        return {}
    summary = _sanitize_value(summary)
    if isinstance(summary, dict):
        summary.pop("cards", None)
    return summary if isinstance(summary, dict) else {}


def build_readonly_response(output_dir: str | None = None) -> Dict[str, Any]:
    resolved_output_dir = output_dir or find_latest_learning_results_output()
    if not resolved_output_dir or not _is_compatible_output_dir(Path(resolved_output_dir)):
        return {
            "ok": False,
            "mode": MODE,
            "source_output_dir": resolved_output_dir,
            "learning_result_cards": 0,
            "cards": [],
            "summary": {},
            "memory_write_performed": False,
            "faiss_write_performed": False,
            "real_write_performed": False,
            "promotion_performed": False,
            "readonly": True,
            "timestamp": now_utc(),
            "error": "learning results output not found",
        }

    cards = load_learning_results_cards(resolved_output_dir)
    summary = load_learning_results_summary(resolved_output_dir)
    return {
        "ok": bool(cards),
        "mode": MODE,
        "source_output_dir": resolved_output_dir,
        "learning_result_cards": len(cards),
        "cards": cards,
        "summary": summary,
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "readonly": True,
        "timestamp": now_utc(),
    }


def _card_matches_query(card: Dict[str, Any], query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return False
    fields = (
        "provider",
        "source_id",
        "candidate_id",
        "what_was_learned",
        "why_it_matters",
        "status",
    )
    haystack = " ".join(str(card.get(field, "")) for field in fields).lower()
    return needle in haystack


def search_learning_results(query: str, output_dir: str | None = None, limit: int = 5) -> Dict[str, Any]:
    response = build_readonly_response(output_dir=output_dir)
    safe_limit = max(1, min(int(limit or 5), 50))
    query_text = (query or "").strip()
    if not query_text:
        return {
            "ok": False,
            "mode": MODE,
            "query": query_text,
            "result_count": 0,
            "results": [],
            "source_output_dir": response.get("source_output_dir"),
            "memory_write_performed": False,
            "faiss_write_performed": False,
            "real_write_performed": False,
            "promotion_performed": False,
            "readonly": True,
            "timestamp": now_utc(),
            "error": "query is required",
        }

    cards = response.get("cards", []) if isinstance(response.get("cards"), list) else []
    matches = [card for card in cards if isinstance(card, dict) and _card_matches_query(card, query_text)]
    limited = matches[:safe_limit]
    return {
        "ok": response.get("ok", False) and bool(limited),
        "mode": MODE,
        "query": query_text,
        "result_count": len(limited),
        "total_matches": len(matches),
        "limit": safe_limit,
        "results": limited,
        "source_output_dir": response.get("source_output_dir"),
        "memory_write_performed": False,
        "faiss_write_performed": False,
        "real_write_performed": False,
        "promotion_performed": False,
        "readonly": True,
        "timestamp": now_utc(),
    }
