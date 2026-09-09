"""R8.3 contract: deterministic routes require an explicit immutable fallback receipt."""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_closed_circuit_selects_the_requested_provider_without_a_fallback():
    from tmp_agent.brain_v9.core.provider_gateway import resolve_provider_route

    decision = resolve_provider_route("codex", circuit_state="CLOSED")

    assert decision.requested_provider_id == "codex"
    assert decision.selected_provider_id == "codex"
    assert decision.fallback_used is False
    assert decision.reason == "primary_route"


def test_open_circuit_requires_an_explicit_fallback_receipt():
    from tmp_agent.brain_v9.core.provider_gateway import resolve_provider_route

    with pytest.raises(ValueError, match="explicit_fallback_receipt_required"):
        resolve_provider_route("codex", circuit_state="OPEN")


def test_open_circuit_uses_only_the_provider_bound_by_its_explicit_receipt():
    from tmp_agent.brain_v9.core.provider_gateway import (
        ProviderFallbackReceipt,
        resolve_provider_route,
    )

    receipt = ProviderFallbackReceipt(
        requested_provider_id="kimi_k2_6_cloud",
        fallback_provider_id="local_ollama",
        reason="circuit_open",
    )
    decision = resolve_provider_route(
        "kimi_k2_6_cloud",
        circuit_state="OPEN",
        fallback_receipt=receipt,
    )

    assert decision.requested_provider_id == "kimi_k2_6_cloud"
    assert decision.selected_provider_id == "local_ollama"
    assert decision.fallback_used is True
    assert decision.reason == "explicit_circuit_open_fallback"
    with pytest.raises(FrozenInstanceError):
        receipt.fallback_provider_id = "codex"


@pytest.mark.parametrize(
    ("requested_provider_id", "circuit_state", "receipt", "error"),
    [
        ("unknown", "CLOSED", None, "unknown_provider"),
        ("codex", "UNKNOWN", None, "unknown_circuit_state"),
        (
            "codex",
            "OPEN",
            {"requested_provider_id": "codex", "fallback_provider_id": "local_ollama"},
            "fallback_receipt_invalid",
        ),
        (
            "codex",
            "OPEN",
            {"requested_provider_id": "local_ollama", "fallback_provider_id": "codex", "reason": "circuit_open"},
            "fallback_receipt_request_mismatch",
        ),
        (
            "codex",
            "OPEN",
            {"requested_provider_id": "codex", "fallback_provider_id": "codex", "reason": "circuit_open"},
            "fallback_provider_must_differ",
        ),
        (
            "codex",
            "OPEN",
            {"requested_provider_id": "codex", "fallback_provider_id": "unknown", "reason": "circuit_open"},
            "unknown_provider",
        ),
        (
            "codex",
            "OPEN",
            {"requested_provider_id": "codex", "fallback_provider_id": "local_ollama", "reason": "manual"},
            "fallback_receipt_reason_invalid",
        ),
    ],
)
def test_route_selection_fails_closed_for_unknown_or_ambiguous_inputs(
    requested_provider_id, circuit_state, receipt, error
):
    from tmp_agent.brain_v9.core.provider_gateway import (
        ProviderFallbackReceipt,
        resolve_provider_route,
    )

    fallback_receipt = ProviderFallbackReceipt(**receipt) if isinstance(receipt, dict) and len(receipt) == 3 else receipt
    with pytest.raises(ValueError, match=error):
        resolve_provider_route(
            requested_provider_id,
            circuit_state=circuit_state,
            fallback_receipt=fallback_receipt,
        )


def test_closed_circuit_rejects_a_receipt_to_prevent_preemptive_degradation():
    from tmp_agent.brain_v9.core.provider_gateway import (
        ProviderFallbackReceipt,
        resolve_provider_route,
    )

    with pytest.raises(ValueError, match="fallback_receipt_not_permitted"):
        resolve_provider_route(
            "codex",
            circuit_state="CLOSED",
            fallback_receipt=ProviderFallbackReceipt(
                requested_provider_id="codex",
                fallback_provider_id="local_ollama",
                reason="circuit_open",
            ),
        )


def test_route_module_remains_static_without_provider_execution_or_configuration_imports():
    source = (ROOT / "tmp_agent/brain_v9/core/provider_gateway.py").read_text(encoding="utf-8")

    for forbidden in ("import os", "import requests", "import subprocess", "from .llm import"):
        assert forbidden not in source
    assert "resolve_provider_route" in source


def test_evidence_records_a_static_no_deploy_route_validation_boundary():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R8_3_PROVIDER_GATEWAY_ROUTE_FALLBACK_VALIDATION.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item_id"] == "R8.3"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_actions"] == {
        "provider_call": False,
        "runtime_configuration_mutation": False,
        "scheduler_activation": False,
        "canonical_local_sync": False,
    }


def test_closeout_closes_r8_3_and_authorizes_only_bound_r9_1():
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R8_3_PROVIDER_GATEWAY_ROUTE_FALLBACK_VALIDATION_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )

    assert manifest["roadmap_items"]["R8.3"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert [
        item_id
        for item_id, item in manifest["roadmap_items"].items()
        if item["status"] == "AUTHORIZED_ACTIVE"
    ] == ["R9.1"]
    binding = manifest["roadmap_items"]["R9.1"]["automation"]
    assert binding["jit_binding_completed"] is True
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert binding["work_branch"] == "control-plane/r9-1-curated-knowledge-canonical-inventory-taxonomy"
    assert binding["allowed_paths"] == [
        "tmp_agent/brain_v9/core/curated_knowledge_catalog.py",
        "docs/roadmap/evidence/BRAIN_101_R9_1_CURATED_KNOWLEDGE_CANONICAL_INVENTORY_TAXONOMY.json",
        "tests/contract/test_r9_1_curated_knowledge_canonical_inventory_taxonomy.py",
    ]
    assert closeout["parent_merge_commit"] == "5f32c71538c141590416d2d36c120add9aad967d"
    assert closeout["runtime_actions"] == {
        "worker_install": False,
        "scheduler_activation": False,
        "provider_call": False,
        "canonical_local_sync": False,
    }
