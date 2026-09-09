"""R8.1 contract: deterministic, inspection-only provider capability policy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_inventory_exposes_only_explicit_non_invocable_provider_identities():
    from tmp_agent.brain_v9.core.provider_gateway import provider_capability_inventory

    inventory = provider_capability_inventory()

    assert [provider.provider_id for provider in inventory] == [
        "codex",
        "kimi_k2_6_cloud",
        "local_ollama",
    ]
    assert all(provider.invocation_allowed is False for provider in inventory)
    assert all(provider.capabilities == ("inventory_read",) for provider in inventory)


def test_request_rejects_unknown_provider_implicit_fallback_and_invocation():
    from tmp_agent.brain_v9.core.provider_gateway import authorize_provider_inspection

    with pytest.raises(ValueError, match="unknown_provider"):
        authorize_provider_inspection("untrusted")
    with pytest.raises(ValueError, match="implicit_provider_fallback_forbidden"):
        authorize_provider_inspection("codex", fallback_provider_id="local_ollama")
    with pytest.raises(ValueError, match="provider_invocation_forbidden"):
        authorize_provider_inspection("codex", invocation_requested=True)


@pytest.mark.parametrize(
    "config",
    [
        {"kimi_k2_6_cloud": {"api_key": "not-a-secret"}},
        {"local_ollama": {"nested": {"token": "not-a-secret"}}},
        {"untrusted": {"model": "anything"}},
    ],
)
def test_inventory_rejects_secret_bearing_or_unknown_configuration(config):
    from tmp_agent.brain_v9.core.provider_gateway import provider_capability_inventory

    with pytest.raises(ValueError):
        provider_capability_inventory(config)


def test_evidence_records_a_no_deploy_static_inventory_boundary():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R8_1_PROVIDER_GATEWAY_POLICY_CAPABILITY_INVENTORY.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item_id"] == "R8.1"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_actions"] == {
        "provider_call": False,
        "runtime_configuration_mutation": False,
        "scheduler_activation": False,
        "canonical_local_sync": False,
    }
