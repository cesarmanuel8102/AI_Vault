"""Validators observability router.

B7-STRANGLER-13D: Extracted /brain/validators from main.py.

The chat-metrics dependency is injected via a provider callback registered
by main.py, so this module does not depend on the session runtime module.

Moved endpoints:
  - GET /brain/validators
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["validators-observability"])

# ── Provider boundary ────────────────────────────────────────────

ValidatorsMetricsProvider = Callable[[], Mapping[str, Any]]

_validators_metrics_provider: ValidatorsMetricsProvider | None = None


def configure_validators_metrics_provider(provider: ValidatorsMetricsProvider) -> None:
    global _validators_metrics_provider
    _validators_metrics_provider = provider


def _validators_metrics() -> Mapping[str, Any]:
    if _validators_metrics_provider is None:
        raise RuntimeError("validators_metrics_provider_not_configured")
    return _validators_metrics_provider()


# ── Endpoint ─────────────────────────────────────────────────────

@router.get("/brain/validators")
async def brain_validators():
    """R7.4: Live observability of validator counters."""
    return dict(_validators_metrics())