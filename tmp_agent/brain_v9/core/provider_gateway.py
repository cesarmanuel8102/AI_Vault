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


_INVENTORY = (
    ProviderCapability("codex", "codex_cli", ("inventory_read",)),
    ProviderCapability("kimi_k2_6_cloud", "ollama_cloud", ("inventory_read",)),
    ProviderCapability("local_ollama", "ollama", ("inventory_read",)),
)
_BY_ID = {provider.provider_id: provider for provider in _INVENTORY}
_SECRET_KEY_PARTS = ("api_key", "authorization", "credential", "password", "secret", "token")


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
