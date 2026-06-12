"""Pure provider-health classification for Brain V9.

This module does not probe networks, write files, or mutate runtime state. Callers
provide observed model tags and optional probe outcomes; the module returns a
serializable health snapshot.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


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
