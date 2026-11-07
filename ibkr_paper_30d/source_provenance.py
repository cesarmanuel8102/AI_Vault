"""Provenance records for the evidence sources behind autonomous decisions.

Only facts the tools actually expose are recorded: missing URLs, timestamps or
time zones are reported as explicit limitations, never invented.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .canonical import sha256_json

SCHEMA = "DECISION_SOURCE_PROVENANCE_V1"
_PROVIDERS = {
    "WORKSPACE": "HOST_WORKSPACE",
    "RUN_RESEARCH_SCRIPT": "HOST_RESEARCH_SANDBOX",
    "QUANTCONNECT": "QUANTCONNECT_LEAN_LOCAL",
}
_ROLES = {
    "NEWS_SEARCH": "SECONDARY",
    "WORKSPACE": "DERIVED",
    "RUN_RESEARCH_SCRIPT": "DERIVED",
    "QUANTCONNECT": "DERIVED",
}
_TIME_KEYS = frozenset(
    {"time", "timestamp", "date", "server_time_utc", "as_of_utc", "last_timestamp", "lastTimestamp"}
)
_MAX_QUERY_VALUE = 200
_MAX_NEWS_ITEMS = 20


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _bounded(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _bounded(item) for key, item in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [_bounded(item) for item in list(value)[:10]]
    if isinstance(value, str) and len(value) > _MAX_QUERY_VALUE:
        return value[:_MAX_QUERY_VALUE] + f"...[{len(value)} chars]"
    return value


def _time_values(node: Any, depth: int = 0) -> Iterable[str]:
    if depth > 4:
        return
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in _TIME_KEYS and isinstance(value, str):
                yield value
            elif isinstance(value, (Mapping, list, tuple)):
                yield from _time_values(value, depth + 1)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _time_values(item, depth + 1)


def _symbol(arguments: Mapping[str, Any], data: Mapping[str, Any]) -> str | None:
    for source in (arguments, data.get("contract") or {}):
        if isinstance(source, Mapping):
            for key in ("symbol", "localSymbol", "local_symbol"):
                if source.get(key):
                    return str(source[key])
    return None


def research_source_provenance(
    request: Any,
    result: Any,
    *,
    requested_at_utc: str,
    received_at_utc: str,
) -> dict[str, Any]:
    tool = str(getattr(request.tool, "value", request.tool))
    arguments = dict(request.arguments or {})
    data = dict(result.data or {})
    limitations: list[str] = []
    aware: list[datetime] = []
    naive: list[str] = []
    for raw in _time_values(data):
        parsed = _parse(raw)
        if parsed is None:
            continue
        if parsed.tzinfo is None:
            naive.append(raw)
        else:
            aware.append(parsed)
    source_time = max(aware) if aware else None
    received = _parse(received_at_utc)
    freshness = None
    if source_time is not None and received is not None and received.tzinfo is not None:
        freshness = int((received - source_time).total_seconds())
    if source_time is None:
        if naive:
            limitations.append("SOURCE_TIMEZONE_UNKNOWN")
        else:
            limitations.append("SOURCE_TIMESTAMP_UNAVAILABLE")
    news_items = [
        {
            "provider_code": item.get("providerCode"),
            "article_id": item.get("articleId"),
            "headline": item.get("headline"),
            "time": item.get("time"),
        }
        for item in (data.get("headlines") or [])[:_MAX_NEWS_ITEMS]
        if isinstance(item, Mapping)
    ]
    source_ids = [item["article_id"] for item in news_items if item["article_id"]]
    if not source_ids:
        con_id = (data.get("contract") or {}).get("conId") if isinstance(data.get("contract"), Mapping) else None
        if con_id:
            source_ids = [f"IBKR_CONID:{con_id}"]
    retrieved = [
        str(item.get("articleId"))
        for item in data.get("articles") or []
        if isinstance(item, Mapping) and item.get("status") == "RETRIEVED"
    ]
    if news_items and not retrieved:
        limitations.append("NEWS_ARTICLE_BODY_NOT_RETRIEVED")
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "request_id": request.request_id,
        "provider": _PROVIDERS.get(tool, "IBKR_TWS_API"),
        "tool": tool,
        "success": bool(result.success),
        "query": _bounded(arguments),
        "query_sha256": sha256_json(arguments),
        "url": None,
        "source_ids": source_ids,
        "requested_at_utc": requested_at_utc,
        "received_at_utc": received_at_utc,
        "source_timestamp_utc": None if source_time is None else _iso(source_time),
        "source_timestamp_raw": None if source_time is not None or not naive else max(naive),
        "freshness_seconds": freshness,
        "symbol": _symbol(arguments, data),
        "source_role": _ROLES.get(tool, "PRIMARY"),
        "payload_sha256": sha256_json(data),
        "limitations": limitations,
    }
    if news_items:
        record["news_items"] = news_items
        record["news_articles_retrieved"] = retrieved
    return record


def native_tool_provenance(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Trace provider-native tool use (e.g. web search) exactly as exposed by the stream."""

    records = []
    for event in events:
        query = event.get("query") if isinstance(event.get("query"), str) else None
        urls = [str(url) for url in event.get("urls") or [] if isinstance(url, str)]
        if urls:
            status = "QUERY_AND_URLS_RECORDED" if query else "URLS_RECORDED_QUERY_UNAVAILABLE"
        elif query:
            status = "QUERY_RECORDED_URLS_UNAVAILABLE"
        else:
            status = "WEB_SOURCE_TRACE_UNAVAILABLE"
        records.append(
            {
                "schema": SCHEMA,
                "provider": "MODEL_PROVIDER_NATIVE_TOOL",
                "tool": str(event.get("type") or ""),
                "native_event_id": event.get("id"),
                "status": event.get("status"),
                "query": query,
                "urls": urls,
                "trace_status": status,
                "source_role": "SECONDARY",
            }
        )
    return records


def model_visible_history(history: Iterable[Any]) -> list[Any]:
    """History sent back to the model; host-only provenance records are excluded."""

    return [
        item for item in history
        if not (isinstance(item, Mapping) and item.get("type") == "source_provenance")
    ]
