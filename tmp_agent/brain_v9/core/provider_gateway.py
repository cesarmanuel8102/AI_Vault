"""R8.1 provider policy boundary: deterministic inventory with no execution path."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


@dataclass(frozen=True)
class ProviderCapability:
    """A safe-to-display provider identity; it never carries credentials or clients."""

    provider_id: str
    transport: str
    capabilities: Tuple[str, ...]
    invocation_allowed: bool = False


@dataclass(frozen=True)
class ProviderResilienceDecision:
    """A bounded policy decision over reported outcomes, never an execution request."""

    provider_id: str
    max_attempts: int
    retry_allowed: bool
    circuit_state: str
    reason: str
    cost_microunits: int


@dataclass(frozen=True)
class ProviderFallbackReceipt:
    """An explicit, immutable authorization to route an open circuit elsewhere."""

    requested_provider_id: str
    fallback_provider_id: str
    reason: str


@dataclass(frozen=True)
class ProviderRouteDecision:
    """A deterministic route choice; it never creates a provider client or call."""

    requested_provider_id: str
    selected_provider_id: str
    fallback_used: bool
    reason: str


_INVENTORY = (
    ProviderCapability("codex", "codex_cli", ("inventory_read",)),
    ProviderCapability("kimi_k2_6_cloud", "ollama_cloud", ("inventory_read",)),
    ProviderCapability("local_ollama", "ollama", ("inventory_read",)),
)
_BY_ID = {provider.provider_id: provider for provider in _INVENTORY}
_SECRET_KEY_PARTS = ("api_key", "authorization", "credential", "password", "secret", "token")
_RESILIENCE_METADATA_KEYS = (
    "model_id",
    "prompt_version",
    "request_class",
    "cost_microunits",
)
_RESILIENCE_OUTCOMES = ("success", "transport_timeout", "transport_failure", "configuration_failure")
_MAX_RESILIENCE_ATTEMPTS = 3
_CIRCUIT_OPEN_AFTER_FAILURES = 2


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            any(marker in str(key).lower() for marker in _SECRET_KEY_PARTS)
            or _contains_secret_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, (tuple, list)):
        return any(_contains_secret_key(item) for item in value)
    return False


def _reject_runtime_configuration(config: Optional[Mapping[str, object]]) -> None:
    if config is None or config == {}:
        return
    if not isinstance(config, Mapping):
        raise ValueError("provider_configuration_must_be_mapping")
    if _contains_secret_key(config):
        raise ValueError("secret_bearing_provider_configuration_forbidden")
    if any(provider_id not in _BY_ID for provider_id in config):
        raise ValueError("unknown_provider")
    raise ValueError("runtime_provider_configuration_forbidden")


def _validate_resilience_metadata(metadata: Optional[Mapping[str, object]]) -> int:
    if metadata is None:
        return 0
    if not isinstance(metadata, Mapping):
        raise ValueError("provider_metadata_must_be_mapping")
    if _contains_secret_key(metadata):
        raise ValueError("secret_bearing_provider_metadata_forbidden")
    if any(key not in _RESILIENCE_METADATA_KEYS for key in metadata):
        raise ValueError("provider_metadata_key_forbidden")
    cost_microunits = metadata.get("cost_microunits", 0)
    if (
        isinstance(cost_microunits, bool)
        or not isinstance(cost_microunits, int)
        or cost_microunits < 0
    ):
        raise ValueError("provider_cost_microunits_invalid")
    if any(
        key != "cost_microunits" and (not isinstance(value, str) or not value)
        for key, value in metadata.items()
    ):
        raise ValueError("provider_metadata_value_invalid")
    return cost_microunits


def provider_resilience_decision(
    provider_id: str,
    *,
    outcome: str,
    consecutive_failures: int,
    metadata: Optional[Mapping[str, object]] = None,
) -> ProviderResilienceDecision:
    """Classify an already observed result using fixed, non-executing policy."""

    if provider_id not in _BY_ID:
        raise ValueError("unknown_provider")
    if outcome not in _RESILIENCE_OUTCOMES:
        raise ValueError("unknown_provider_outcome")
    if not isinstance(consecutive_failures, int) or not 0 <= consecutive_failures <= _MAX_RESILIENCE_ATTEMPTS - 1:
        raise ValueError("provider_failure_count_out_of_bounds")
    cost_microunits = _validate_resilience_metadata(metadata)

    circuit_open = consecutive_failures >= _CIRCUIT_OPEN_AFTER_FAILURES
    if circuit_open:
        return ProviderResilienceDecision(
            provider_id,
            _MAX_RESILIENCE_ATTEMPTS,
            False,
            "OPEN",
            "circuit_open",
            cost_microunits,
        )
    if outcome == "configuration_failure":
        return ProviderResilienceDecision(
            provider_id,
            _MAX_RESILIENCE_ATTEMPTS,
            False,
            "CLOSED",
            "configuration_failure",
            cost_microunits,
        )
    if outcome in ("transport_timeout", "transport_failure"):
        return ProviderResilienceDecision(
            provider_id,
            _MAX_RESILIENCE_ATTEMPTS,
            True,
            "CLOSED",
            "transient_failure",
            cost_microunits,
        )
    return ProviderResilienceDecision(
        provider_id,
        _MAX_RESILIENCE_ATTEMPTS,
        False,
        "CLOSED",
        "success",
        cost_microunits,
    )


def resolve_provider_route(
    requested_provider_id: str,
    *,
    circuit_state: str,
    fallback_receipt: Optional[ProviderFallbackReceipt] = None,
) -> ProviderRouteDecision:
    """Select a static route and require a matching receipt for any fallback."""

    if requested_provider_id not in _BY_ID:
        raise ValueError("unknown_provider")
    if circuit_state not in ("CLOSED", "OPEN"):
        raise ValueError("unknown_circuit_state")
    if circuit_state == "CLOSED":
        if fallback_receipt is not None:
            raise ValueError("fallback_receipt_not_permitted")
        return ProviderRouteDecision(
            requested_provider_id,
            requested_provider_id,
            False,
            "primary_route",
        )

    if fallback_receipt is None:
        raise ValueError("explicit_fallback_receipt_required")
    if not isinstance(fallback_receipt, ProviderFallbackReceipt):
        raise ValueError("fallback_receipt_invalid")
    if fallback_receipt.requested_provider_id != requested_provider_id:
        raise ValueError("fallback_receipt_request_mismatch")
    if fallback_receipt.fallback_provider_id not in _BY_ID:
        raise ValueError("unknown_provider")
    if fallback_receipt.fallback_provider_id == requested_provider_id:
        raise ValueError("fallback_provider_must_differ")
    if fallback_receipt.reason != "circuit_open":
        raise ValueError("fallback_receipt_reason_invalid")
    return ProviderRouteDecision(
        requested_provider_id,
        fallback_receipt.fallback_provider_id,
        True,
        "explicit_circuit_open_fallback",
    )


def provider_capability_inventory(
    config: Optional[Mapping[str, object]] = None,
) -> Tuple[ProviderCapability, ...]:
    """Return the fixed inspection inventory without consulting runtime configuration."""

    _reject_runtime_configuration(config)
    return _INVENTORY


def authorize_provider_inspection(
    provider_id: str,
    *,
    fallback_provider_id: Optional[str] = None,
    invocation_requested: bool = False,
) -> ProviderCapability:
    """Authorize an inventory lookup only; selection, fallback, and invocation fail closed."""

    if fallback_provider_id is not None:
        raise ValueError("implicit_provider_fallback_forbidden")
    if invocation_requested:
        raise ValueError("provider_invocation_forbidden")
    try:
        return _BY_ID[provider_id]
    except KeyError as exc:
        raise ValueError("unknown_provider") from exc
