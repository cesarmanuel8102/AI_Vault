"""BRAIN-101-R3-2 Agent V2 intent router contract tests.

Front: BRAIN-101-R3-2-AGENT-V2-COGNITIVE-PIPELINE-CONTRACTS-01
Surface: C2 Intent contract

These tests exercise the deterministic intent classifier surface and the
AgentV2IntentAdapter router surface.  They never start servers, make HTTP
calls, or perform real write operations.  LLM classification is forced off by
monkeypatching BRAIN_USE_LLM_INTENT_CLASSIFIER so the tests are deterministic and
CI-safe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


INTENT_CLASSIFIER = "brain_v9.core.agent_kernel_v2.intent_classifier"
INTENT_ADAPTER = "brain_v9.core.agent_kernel_v2.intent_adapter"


@pytest.fixture(autouse=True)
def disable_llm_classifier(monkeypatch):
    """Ensure deterministic keyword-only intent classification in tests."""
    monkeypatch.setattr(f"{INTENT_CLASSIFIER}.BRAIN_USE_LLM_INTENT_CLASSIFIER", False)
    monkeypatch.setattr(f"{INTENT_ADAPTER}.BRAIN_USE_LLM_INTENT_CLASSIFIER", False)


# ---------------------------------------------------------------------------
# 1. Supported intent inventory contract
# ---------------------------------------------------------------------------

def test_intent_classifier_exports_supported_intent_set():
    from brain_v9.core.agent_kernel_v2.intent_classifier import SUPPORTED_INTENTS

    required_intents = {
        "read_only_status",
        "explain_capabilities",
        "repo_read",
        "dashboard_diagnosis",
        "code_change_request",
        "push_request",
        "delete_request",
        "memory_read",
        "memory_write",
        "autonomy_dryrun",
        "self_improvement_reportonly",
        "trading_broker_live",
        "teacher_codex_search",
        "memory_structure_diagnosis",
        "semantic_memory_status",
        "promotion_queue_status",
        "trace_inspect",
        "capability_registry_read",
        "brain_self_knowledge_lookup",
        "financial_autonomy_diagnosis",
        "evidence_required_diagnosis",
        "unknown_or_insufficient_info",
    }
    assert required_intents.issubset(SUPPORTED_INTENTS)
    assert "god_mode" not in SUPPORTED_INTENTS


def test_intent_classifier_lists_supported_intents():
    from brain_v9.core.agent_kernel_v2.intent_classifier import list_supported_intents

    intents = list_supported_intents()
    assert isinstance(intents, list)
    assert "trading_broker_live" in intents
    assert sorted(intents) == intents


# ---------------------------------------------------------------------------
# 2. Route map contract
# ---------------------------------------------------------------------------

def test_intent_route_map_has_canonical_routes():
    from brain_v9.core.agent_kernel_v2.intent_classifier import INTENT_ROUTE_MAP

    assert INTENT_ROUTE_MAP["read_only_status"] == "direct_assistant"
    assert INTENT_ROUTE_MAP["repo_read"] == "brain_evidence"
    assert INTENT_ROUTE_MAP["code_change_request"] == "operational_agent"
    assert INTENT_ROUTE_MAP["trading_broker_live"] == "direct_assistant"
    for intent, route in INTENT_ROUTE_MAP.items():
        assert route in {"direct_assistant", "brain_evidence", "operational_agent"}
        assert intent != "god_mode"


# ---------------------------------------------------------------------------
# 3. Classification output schema contract
# ---------------------------------------------------------------------------

def test_classify_intent_returns_required_schema_for_read_only_status():
    from brain_v9.core.agent_kernel_v2.intent_classifier import classify_intent

    # Use a phrasing that the deterministic keyword classifier owns directly,
    # avoiding the generic evidence-policy override.
    result = classify_intent("current status")
    required_keys = {
        "intent",
        "confidence",
        "language",
        "risk_level",
        "requires_approval",
        "route",
        "reason",
        "blocked_reason",
        "matched_terms",
        "classifier",
    }
    assert required_keys.issubset(result.keys())
    assert result["intent"] == "read_only_status"
    assert result["route"] == "direct_assistant"
    assert result["requires_approval"] is False
    assert result["risk_level"] == "safe"
    assert 0 <= result["confidence"] <= 1


def test_classify_intent_blocks_trading_broker_live():
    from brain_v9.core.agent_kernel_v2.intent_classifier import classify_intent

    result = classify_intent("Connect IBKR and enable live trading")
    assert result["intent"] == "trading_broker_live"
    assert result["route"] == "direct_assistant"
    assert result["risk_level"] == "blocked"
    assert result["requires_approval"] is False
    assert "trading" in (result["blocked_reason"] or "").lower()


def test_classify_intent_escalates_write_intents_to_approval_required():
    from brain_v9.core.agent_kernel_v2.intent_classifier import classify_intent

    result = classify_intent("Modify the response normalizer code")
    assert result["intent"] == "code_change_request"
    assert result["route"] == "operational_agent"
    assert result["requires_approval"] is True
    assert result["risk_level"] in {"approval_required", "safe"}


def test_classify_intent_ignores_negated_phrases():
    from brain_v9.core.agent_kernel_v2.intent_classifier import classify_intent

    result = classify_intent("Do not connect IBKR or enable live trading")
    assert result["intent"] != "trading_broker_live"
    assert result["route"] in {"direct_assistant", "brain_evidence"}


def test_select_route_from_intent_returns_route_from_classification():
    from brain_v9.core.agent_kernel_v2.intent_classifier import select_route_from_intent

    assert select_route_from_intent({"intent": "repo_read"}) == "brain_evidence"
    assert select_route_from_intent({"intent": "unknown_or_insufficient_info"}) == "direct_assistant"


# ---------------------------------------------------------------------------
# 4. IntentAdapter route contract
# ---------------------------------------------------------------------------

def test_intent_adapter_select_route_returns_required_schema():
    from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter

    adapter = AgentV2IntentAdapter()
    result = adapter.select_route("How is the dashboard structured?")
    assert "route" in result
    assert result["route"] in {
        "direct_assistant",
        "brain_evidence",
        "mixed_brain_reasoning",
        "operational_agent",
    }
    assert "intent" in result
    assert isinstance(result.get("confidence"), (int, float))


def test_intent_adapter_get_evidence_sources_returns_required_schema():
    from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter

    adapter = AgentV2IntentAdapter()
    sources = adapter.get_evidence_sources("brain_evidence", "What tools are available in Agent V2?")
    assert isinstance(sources, list)
    if sources:
        first = sources[0]
        assert {"type", "paths", "tools", "grep_pattern"}.issubset(first.keys())
        assert isinstance(first["tools"], list)


def test_intent_adapter_has_evidence_source_contract_inventory():
    from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter

    adapter = AgentV2IntentAdapter()
    contract = adapter.EVIDENCE_SOURCE_CONTRACT
    types = {entry["type"] for entry in contract}
    required_types = {
        "front_brain",
        "traces",
        "ledgers",
        "learning_external",
        "runtime_operations",
        "tools_capabilities",
        "semantic_memory",
    }
    assert required_types.issubset(types)
    for entry in contract:
        assert isinstance(entry.get("positive_keywords_en"), list)
        assert isinstance(entry.get("positive_keywords_es"), list)
        assert isinstance(entry.get("tools"), list)
        assert isinstance(entry.get("paths"), list)


def test_intent_adapter_promotion_dry_run_route_is_detected():
    from brain_v9.core.agent_kernel_v2.intent_adapter import AgentV2IntentAdapter

    adapter = AgentV2IntentAdapter()
    result = adapter.select_route("valida candidato dry-run promotion_queue abc123")
    assert result["intent"] == "PROMOTION_ADAPTER_DRY_RUN"
    assert result["route"] == "promotion_adapter_dry_run"
    assert result.get("promotion_adapter_meta", {}).get("dry_run") == "true"


# ---------------------------------------------------------------------------
# 5. Governance policy contract on classified intents
# ---------------------------------------------------------------------------

def test_governance_policy_decision_schema_for_allowed_intent():
    from brain_v9.core.agent_kernel_v2.governance_policy import decide_governance

    decision = decide_governance("repo_read", "read_only", "read_only")
    assert decision["governance_decision"] == "allow"
    assert decision["safe_mode"] is True
    assert decision["approval_required"] is False


def test_governance_policy_blocks_trading():
    from brain_v9.core.agent_kernel_v2.governance_policy import decide_governance

    decision = decide_governance("trading_broker_live", "auto", "auto")
    assert decision["governance_decision"] == "blocked"
    assert decision["safe_mode"] is True
    assert "trading" in (decision["blocked_reason"] or "").lower()


def test_governance_policy_approval_required_for_memory_write():
    from brain_v9.core.agent_kernel_v2.governance_policy import decide_governance

    decision = decide_governance("memory_write", "read_only", "read_only")
    assert decision["governance_decision"] == "approval_required"
    assert decision["required_permission"] == "memory_write"
    assert decision["approval_required"] is True
    assert decision["safe_mode"] is True


def test_governance_policy_autonomy_dry_run_only_by_default():
    from brain_v9.core.agent_kernel_v2.governance_policy import decide_governance

    decision = decide_governance("autonomy_dryrun", "auto", "auto")
    assert decision["governance_decision"] == "dry_run_only"
    assert decision["required_permission"] == "autonomy_dryrun"


# ---------------------------------------------------------------------------
# 6. Evidence routing policy contract
# ---------------------------------------------------------------------------

def test_evidence_policy_routes_brain_internal_questions():
    from brain_v9.core.agent_kernel_v2.intent_classifier import _evidence_policy_classify

    result = _evidence_policy_classify("How is memory structured in Brain?")
    assert result is not None
    assert result["route"] == "brain_evidence"
    assert result["risk_level"] == "safe"


def test_evidence_policy_excludes_generic_greetings():
    from brain_v9.core.agent_kernel_v2.intent_classifier import _evidence_policy_classify

    assert _evidence_policy_classify("Hola, como estas?") is None
    assert _evidence_policy_classify("thanks") is None


# ---------------------------------------------------------------------------
# 7. Import boundaries: no disallowed runtime surfaces are pulled in
# ---------------------------------------------------------------------------

def test_intent_classifier_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/intent_classifier.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem(", "sub" + "process.run("]
    assert not any(token in src for token in forbidden)


def test_intent_adapter_does_not_import_server_starters():
    src = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/intent_adapter.py").read_text(encoding="utf-8")
    forbidden = ["uv" + "icorn", "FastAPI(", "Test" + "Client(", "os.s" + "ystem(", "sub" + "process.run("]
    assert not any(token in src for token in forbidden)


# ---------------------------------------------------------------------------
# Runner for direct invocation
# ---------------------------------------------------------------------------

_TESTS = [
    test_intent_classifier_exports_supported_intent_set,
    test_intent_route_map_has_canonical_routes,
    test_classify_intent_returns_required_schema_for_read_only_status,
    test_classify_intent_blocks_trading_broker_live,
    test_classify_intent_escalates_write_intents_to_approval_required,
    test_classify_intent_ignores_negated_phrases,
    test_select_route_from_intent_returns_route_from_classification,
    test_intent_adapter_select_route_returns_required_schema,
    test_intent_adapter_get_evidence_sources_returns_required_schema,
    test_intent_adapter_has_evidence_source_contract_inventory,
    test_intent_adapter_promotion_dry_run_route_is_detected,
    test_governance_policy_decision_schema_for_allowed_intent,
    test_governance_policy_blocks_trading,
    test_governance_policy_approval_required_for_memory_write,
    test_governance_policy_autonomy_dry_run_only_by_default,
    test_evidence_policy_routes_brain_internal_questions,
    test_evidence_policy_excludes_generic_greetings,
    test_intent_classifier_does_not_import_server_starters,
    test_intent_adapter_does_not_import_server_starters,
]


if __name__ == "__main__":
    passed = failed = 0
    for t in _TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed}/{len(_TESTS)} passed")
    if failed:
        raise SystemExit(1)
