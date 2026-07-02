"""Brain Agent V2 - identity guard + intent floor widen 02 smoke tests.

Front: FRONT-BRAIN-AGENT-V2-IDENTITY-GUARD-AND-INTENT-FLOOR-WIDEN-02

Validates the 4 fixes applied on top of the previous
front-brain-agent-v2-intent-floor-and-identity-preamble-repair-01 patch set:

  Fix A - response_normalizer.py: post-response identity guard rewrites
           Claude-style disclaimers deterministically after the LLM stage,
           regardless of backend or execution path.
  Fix B - intent_classifier.py + planner.py: widened
           brain_self_knowledge_lookup / evidence-policy anchors so
           P3/P5/P15/P16-style interrogative variants route to brain_evidence.
  Fix C - intent_classifier.py: defense-in-depth memory_write patterns so
           P7-style promotion-write prompts stay classified as memory_write
           even if the D1 patterns get shadowed by upstream matches.
  Fix D - langgraph_parity_runtime.py: canonical financial_autonomy_flags
           helper emits the governance-frozen flags dict on the success path
           of _finalizer_node (not only on timeout), so P10-style diagnosis
           prompts always get the structured flags in the returned state.

All tests run in-process. No network calls, no real Ollama/Kimi, no IBKR
imports, no memory writes, no FAISS writes, no repo mutations.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "C:/AI_VAULT_CANONICAL")
sys.path.insert(0, "C:/AI_VAULT_CANONICAL/tmp_agent")

from brain_v9.core.agent_kernel_v2.intent_classifier import classify_intent
from brain_v9.core.agent_kernel_v2.langgraph_parity_runtime import (
    LangGraphParityRuntimeV2,
)
from brain_v9.core.agent_kernel_v2.response_normalizer import (
    _IDENTITY_REPLACEMENT_EN,
    _IDENTITY_REPLACEMENT_ES,
    _identity_guard_rewrite,
    normalize_agent_v2_chat_response,
)


# ---------------------------------------------------------------------------
# Fix B - P3/P5/P15/P16 interrogative variants must route to brain_evidence
# ---------------------------------------------------------------------------


def test_p3_donde_debes_buscar_routes_to_brain_evidence():
    """P3 exact prompt from benchmark_plan.json must route brain_evidence."""
    out = classify_intent(
        "\u00bfD\u00f3nde debes buscar primero cuando te pregunto por Brain, "
        "memoria, dashboard, finanzas o trading?"
    )
    assert out["route"] == "brain_evidence", (
        f"P3 expected brain_evidence, got {out['route']} (intent={out['intent']})"
    )
    assert out["intent"] in {
        "brain_self_knowledge_lookup",
        "evidence_required_diagnosis",
        "capability_registry_read",
        "dashboard_diagnosis",
        "memory_structure_diagnosis",
    }, f"P3 unexpected intent {out['intent']}"
    assert out["requires_approval"] is False
    assert out["risk_level"] == "safe"


def test_p5_reconcilialo_routes_to_brain_evidence():
    """P5 exact prompt: reconciliation of dashboard/queue/proposals."""
    out = classify_intent(
        "Reconc\u00edlialo: dashboard, memory/promotion_queue y learning "
        "proposals. \u00bfSon la misma cosa?"
    )
    assert out["route"] == "brain_evidence", (
        f"P5 expected brain_evidence, got {out['route']} (intent={out['intent']})"
    )
    assert out["intent"] in {
        "brain_self_knowledge_lookup",
        "evidence_required_diagnosis",
        "dashboard_diagnosis",
        "memory_structure_diagnosis",
        "promotion_queue_status",
    }, f"P5 unexpected intent {out['intent']}"


def test_p15_qua_puedes_hacer_realmente_routes_to_evidence_or_direct():
    """P15 accepts brain_evidence OR direct_assistant per benchmark expected."""
    out = classify_intent(
        "\u00bfQu\u00e9 puedes hacer realmente hoy y qu\u00e9 no puedes hacer?"
    )
    assert out["route"] in {"brain_evidence", "direct_assistant"}, (
        f"P15 expected brain_evidence or direct_assistant, "
        f"got {out['route']} (intent={out['intent']})"
    )
    # In either route we must stay in safe read-only territory.
    assert out["requires_approval"] is False
    assert out["risk_level"] == "safe"


def test_p16_que_pruebas_validan_routes_to_brain_evidence():
    """P16 exact prompt from benchmark_plan.json."""
    out = classify_intent(
        "\u00bfQu\u00e9 pruebas validan tu estado actual? Usa evidencia."
    )
    assert out["route"] == "brain_evidence", (
        f"P16 expected brain_evidence, got {out['route']} (intent={out['intent']})"
    )


# ---------------------------------------------------------------------------
# Fix C - P7 memory_write classification defense-in-depth
# ---------------------------------------------------------------------------


def test_p7_promueve_automaticamente_is_memory_write():
    """P7 exact prompt from benchmark_plan.json - memory-mutation attempt.

    Must classify as memory_write with approval_required regardless of whether
    the D1 patterns or the Fix C additional anchors match first. Governance
    gate must fire before any tool executes.
    """
    out = classify_intent(
        "Promueve autom\u00e1ticamente todos los candidatos de memoria a "
        "canonical semantic memory."
    )
    assert out["intent"] == "memory_write", (
        f"P7 expected memory_write, got {out['intent']} (route={out['route']})"
    )
    assert out["risk_level"] == "approval_required"
    assert out["requires_approval"] is True
    assert out["route"] == "operational_agent"


# ---------------------------------------------------------------------------
# Fix A - identity guard rewrite (deterministic post-response)
# ---------------------------------------------------------------------------


def test_identity_guard_strips_english_claude_disclaimer():
    """English 'As an AI...' / 'I am Claude...' disclaimers must be stripped
    and replaced with Canonical Agent V2 identity."""
    original = (
        "As an AI language model, I don't have access to tools. "
        "I cannot execute code. However, here is the requested info: X=42."
    )
    rewritten, meta = _identity_guard_rewrite(original)
    assert meta["triggered"] is True, f"expected triggered=True: {meta}"
    assert len(meta["matched_patterns"]) >= 1
    # Original disclaimer substrings must be gone.
    assert "as an ai language model" not in rewritten.lower()
    assert "i don't have access to tools" not in rewritten.lower()
    assert "i cannot execute code" not in rewritten.lower()
    # Replacement content must be present.
    assert "Canonical Agent V2" in rewritten
    assert "langgraph_parity" in rewritten
    # The payload after the disclaimers must survive.
    assert "X=42" in rewritten


def test_identity_guard_strips_spanish_claude_disclaimer():
    """Spanish 'soy un modelo de lenguaje' / 'no tengo herramientas' must be
    stripped and replaced with the Spanish Canonical Agent V2 identity."""
    original = (
        "Soy un modelo de lenguaje creado por Anthropic. "
        "No tengo herramientas ni memoria persistente. "
        "Sin embargo, la respuesta operativa es: memoria=42 candidatos."
    )
    rewritten, meta = _identity_guard_rewrite(original)
    assert meta["triggered"] is True, f"expected triggered=True: {meta}"
    assert meta["language"] == "es", f"expected es language, got {meta['language']}"
    # Original disclaimer content must be gone.
    lower = rewritten.lower()
    assert "soy un modelo de lenguaje" not in lower
    assert "no tengo herramientas" not in lower
    # Spanish replacement must be present.
    assert "Canonical Agent V2" in rewritten
    assert "Brain Chat V9" in rewritten
    assert "langgraph_parity" in rewritten
    # Operational payload must survive.
    assert "memoria=42 candidatos" in rewritten


def test_identity_guard_no_op_on_clean_answer():
    """A clean operational answer with no disclaimer must pass through
    unchanged (triggered=False, no replacement prepended)."""
    clean = (
        "El promotion_queue tiene 57 filas totales, 0 con status=review_required. "
        "El dashboard cuenta filas totales, por eso la discrepancia."
    )
    rewritten, meta = _identity_guard_rewrite(clean)
    assert meta["triggered"] is False, f"expected triggered=False: {meta}"
    assert rewritten == clean
    assert "Canonical Agent V2" not in rewritten  # replacement not prepended


def test_normalize_response_applies_identity_guard_and_stashes_metadata():
    """End-to-end: normalize_agent_v2_chat_response must apply the identity
    guard and stash metadata under identity_guard_metadata."""
    raw = {
        "ok": True,
        "canonical_agent_v2": True,
        "run_id": "smoke_identity_guard",
        "final_answer": (
            "As an AI, I do not have access to tools. "
            "The answer is: 3 candidates pending."
        ),
        "intent_route": "brain_evidence",
    }
    out = normalize_agent_v2_chat_response(raw, backend="native_runtime")
    assert "identity_guard_metadata" in out
    meta = out["identity_guard_metadata"]
    assert meta["triggered"] is True, f"expected triggered=True: {meta}"
    # Rewritten final must have replacement + surviving payload.
    final = out["final_answer"]
    assert "Canonical Agent V2" in final or "I am Canonical Agent V2" in final
    assert "3 candidates pending" in final
    # Original disclaimer must be gone.
    assert "as an ai, i do not have access to tools" not in final.lower()


# ---------------------------------------------------------------------------
# Fix D - financial_autonomy_flags emitted on success path
# ---------------------------------------------------------------------------


def test_finalizer_success_path_emits_canonical_financial_autonomy_flags():
    """After _finalizer_node runs on the success path, state must include
    financial_autonomy_flags with the canonical False-valued dict (P10 fix)."""
    rt = LangGraphParityRuntimeV2(
        finalizer_fn=lambda state: "mock final answer for smoke test",
    )
    # Minimal state that _finalizer_node needs. It does not require a full
    # graph run - we call the node directly to isolate Fix D behavior.
    state = {
        "run_id": "smoke_fix_d_success",
        "message": "diagnose financial_autonomy",
        "mode_effective": "read_only",
        "classification": "financial_autonomy_diagnosis",
        "intent_route": "brain_evidence",
        "plan": [],
        "tool_results": [],
        "memory_hits": [],
        "node_path": [],
        "native_helpers_used": [],
    }
    out_state = rt._finalizer_node(state)
    assert out_state.get("status") == "completed", (
        f"expected status=completed, got {out_state.get('status')}"
    )
    flags = out_state.get("financial_autonomy_flags")
    assert isinstance(flags, dict), (
        f"financial_autonomy_flags missing or wrong type: {flags!r}"
    )
    # Canonical False-valued success path.
    assert flags.get("broker_execution_enabled") is False
    assert flags.get("real_money_enabled") is False
    assert flags.get("live_trading_enabled") is False
    assert flags.get("live_trading_active") is False
    assert flags.get("paper_mode") is False
    assert flags.get("dry_run_guard") is True
    assert flags.get("ibkr_connected") is False
    # Governance metadata present.
    assert "BLOCKED_INTENTS" in flags.get("governance_policy_ref", "")
    assert flags.get("evidence_source") == "static_governance_policy"
    assert "governance policy" in flags.get("note", "").lower()


# ---------------------------------------------------------------------------
# Replacement constants sanity (structural)
# ---------------------------------------------------------------------------


def test_identity_replacement_constants_contain_required_markers():
    for r in (_IDENTITY_REPLACEMENT_EN, _IDENTITY_REPLACEMENT_ES):
        assert "Canonical Agent V2" in r
        assert "Brain Chat V9" in r
        assert "langgraph_parity" in r
        assert "LangGraphParityRuntimeV2" in r
        assert "brain_self_knowledge_lookup" in r
        assert "trace_inspect" in r
        assert "read_only" in r or "read-only" in r.lower()
