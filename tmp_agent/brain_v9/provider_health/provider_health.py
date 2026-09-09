"""Pure provider-health classification for Brain V9.

This module does not probe networks, write files, or mutate runtime state. Callers
provide observed model tags and optional probe outcomes; the module returns a
serializable health snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from ..tracing.trace_redactor import sanitize_event


@dataclass(frozen=True)
class ProviderHealthRecord:
    provider_id: str
    model_tag: str
    status: str
    last_latency_ms: int | None
    last_error_type: str | None
    empty_response_count: int
    timeout_count: int
    success_count: int
    last_checked_utc: str
    usable_for_chat: bool
    usable_for_code: bool
    usable_for_autonomy: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_provider_health_snapshot(
    ollama_models: Iterable[str],
    *,
    configured_model_tag: str = "kimi-k2.6:cloud",
    k2_5_probe: dict[str, Any] | None = None,
    codex_available: bool = True,
    local_llama_available: bool = False,
    checked_utc: str | None = None,
) -> dict[str, Any]:
    """Build a read-only provider health snapshot from observed facts."""

    model_set = {str(model) for model in ollama_models}
    checked = checked_utc or _now_utc()
    k2_6_present = configured_model_tag in model_set
    k2_5_present = "kimi-k2.5:cloud" in model_set
    k2_5_empty = bool(k2_5_probe and not k2_5_probe.get("non_empty", False))

    records = [
        ProviderHealthRecord(
            provider_id="kimi_k2_6_cloud",
            model_tag=configured_model_tag,
            status="AVAILABLE" if k2_6_present else "TAG_MISSING",
            last_latency_ms=None,
            last_error_type=None if k2_6_present else "KIMI_K2_6_OLLAMA_TAG_MISSING",
            empty_response_count=0,
            timeout_count=0,
            success_count=1 if k2_6_present else 0,
            last_checked_utc=checked,
            usable_for_chat=k2_6_present,
            usable_for_code=k2_6_present,
            usable_for_autonomy=k2_6_present,
            notes=["Configured primary cloud provider via Ollama Cloud."],
        ),
        ProviderHealthRecord(
            provider_id="kimi_k2_5_cloud",
            model_tag="kimi-k2.5:cloud",
            status="PARTIAL_UNRELIABLE" if k2_5_present and k2_5_empty else ("AVAILABLE_FALLBACK" if k2_5_present else "TAG_MISSING"),
            last_latency_ms=int(k2_5_probe.get("latency_ms")) if k2_5_probe and k2_5_probe.get("latency_ms") is not None else None,
            last_error_type="EMPTY_RESPONSE" if k2_5_empty else None,
            empty_response_count=1 if k2_5_empty else 0,
            timeout_count=0,
            success_count=1 if k2_5_present and not k2_5_empty else 0,
            last_checked_utc=checked,
            usable_for_chat=k2_5_present and not k2_5_empty,
            usable_for_code=k2_5_present and not k2_5_empty,
            usable_for_autonomy=False,
            notes=["Temporary diagnostic fallback only; do not promote above configured K2.6 tag."],
        ),
        ProviderHealthRecord(
            provider_id="codex",
            model_tag="codex",
            status="EXECUTOR_AVAILABLE" if codex_available else "UNAVAILABLE",
            last_latency_ms=None,
            last_error_type=None if codex_available else "CODEX_UNAVAILABLE",
            empty_response_count=0,
            timeout_count=0,
            success_count=1 if codex_available else 0,
            last_checked_utc=checked,
            usable_for_chat=codex_available,
            usable_for_code=codex_available,
            usable_for_autonomy=codex_available,
            notes=["Second provider in Brain chain; no secrets required."],
        ),
        ProviderHealthRecord(
            provider_id="llama8b",
            model_tag="llama3.1:8b",
            status="AVAILABLE_FALLBACK" if local_llama_available else "TAG_MISSING",
            last_latency_ms=None,
            last_error_type=None if local_llama_available else "LOCAL_MODEL_TAG_MISSING",
            empty_response_count=0,
            timeout_count=0,
            success_count=1 if local_llama_available else 0,
            last_checked_utc=checked,
            usable_for_chat=local_llama_available,
            usable_for_code=False,
            usable_for_autonomy=False,
            notes=["Local fallback only; not preferred for final autonomy quality."],
        ),
    ]

    return {
        "checked_utc": checked,
        "configured_primary": "kimi_k2_6_cloud",
        "configured_model_tag": configured_model_tag,
        "cloud_provider_available": k2_6_present,
        "codex_provider_available": codex_available,
        "local_fallback_available": local_llama_available,
        "records": [record.to_dict() for record in records],
    }


_OBSERVATION_FIELDS = {"provider_id", "model", "outcome", "input_tokens", "output_tokens", "cost_microusd", "error_type"}
_OUTCOMES = {"success", "error", "timeout"}


def derive_provider_health_and_accounting(observations: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate sanitized provider observations without probing a provider or writing state."""
    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    totals = {"input_tokens": 0, "output_tokens": 0, "cost_microusd": 0}
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) - _OBSERVATION_FIELDS:
            raise ValueError("provider_observation_invalid")
        if sanitize_event(observation) != observation:
            raise ValueError("provider_observation_not_sanitized")
        provider_id, model, outcome = observation.get("provider_id"), observation.get("model"), observation.get("outcome")
        if not all(isinstance(value, str) and value.strip() for value in (provider_id, model)) or outcome not in _OUTCOMES:
            raise ValueError("provider_observation_invalid")
        if outcome in {"error", "timeout"} and (not isinstance(observation.get("error_type"), str) or not observation["error_type"].strip()):
            raise ValueError("provider_error_type_required")
        if outcome == "success" and "error_type" in observation:
            raise ValueError("provider_error_type_invalid")
        numeric = {field: observation.get(field) for field in totals}
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in numeric.values()):
            raise ValueError("provider_accounting_invalid")
        key = (provider_id, model)
        record = aggregate.setdefault(key, {"provider_id": provider_id, "model": model, "success_count": 0, "error_count": 0, "timeout_count": 0, **{field: 0 for field in totals}, "error_taxonomy": {}})
        record[f"{outcome}_count"] += 1
        if outcome in {"error", "timeout"}:
            record["error_taxonomy"][observation["error_type"]] = record["error_taxonomy"].get(observation["error_type"], 0) + 1
        for field, value in numeric.items():
            record[field] += value
            totals[field] += value
    providers = []
    for key in sorted(aggregate):
        record = aggregate[key]
        record["error_taxonomy"] = dict(sorted(record["error_taxonomy"].items()))
        providers.append(record)
    return {"schema_version": 1, "provider_count": len(providers), **totals, "providers": providers}
