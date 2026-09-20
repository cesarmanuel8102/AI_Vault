"""BR2-3 contract: Brain records the BR1 semantic authority as the ONLY evaluator.

Brain must not re-evaluate semantics. Any semantic PASS/BLOCK question on
roadmap requirements routes exclusively through the BR1 gate
(evaluateSemanticCompletion, PR #391). This pointer record makes that
binding explicit for the future HIVE receipt integration.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POINTER = ROOT / "docs/roadmap/evidence/BRAIN_101_BR2_SEMANTIC_AUTHORITY_POINTER.json"


def test_pointer_record_exists_and_binds_the_br1_authority():
    record = json.loads(POINTER.read_text(encoding="utf-8"))
    assert record["schema_version"] == 1
    assert record["record_type"] == "SEMANTIC_AUTHORITY_POINTER"
    assert record["single_semantic_authority"] == "evaluateSemanticCompletion"
    assert record["authority_module"] == "scripts/operator_proxy/semantic_completion_gate.ts"
    assert record["merged_pr"] == 391
    assert record["merge_commit"] == "ae3be637fa7642b735c92a1b4b16aa20b92ac1b8"
    assert record["brain_re_evaluates_semantics"] is False
    assert "must route through the BR1 gate" in record["routing_rule"]
    # The governed canonical artifacts the authority consumes must be named.
    for path in (
        "docs/roadmap/semantic/semantic_registry.json",
        "docs/roadmap/semantic/requirements.json",
        "docs/roadmap/semantic/evidence.json",
        "docs/roadmap/semantic/soak_execution_manifest.json",
        "docs/roadmap/semantic/regime_classifier_contract.json",
    ):
        assert path in record["governed_authority_artifacts"]
    assert record["runtime_actions"] == {}


def test_brain_core_defines_no_second_semantic_evaluator():
    """No module under brain_v9/core may implement a semantic PASS/BLOCK evaluator."""
    core = ROOT / "tmp_agent/brain_v9/core"
    forbidden_markers = (
        "SEMANTIC_COMPLETION_DECISION",
        "def evaluate_semantic_completion",
        "SemanticCompletionDecisionV1",
    )
    offenders = []
    for path in core.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in forbidden_markers:
            if marker in text and "hive_receipt_boundary" not in path.name:
                offenders.append(f"{path.name}:{marker}")
    assert not offenders, f"second semantic evaluator found: {offenders}"


def test_r15_semantic_truth_remains_block():
    """The pointer must state the truthful current R15 decision, not a hope."""
    record = json.loads(POINTER.read_text(encoding="utf-8"))
    truth = record["current_r15_semantic_truth"]
    assert truth["decision"] == "BLOCK"
    assert "MISSING_EVIDENCE" in truth["reason_codes"]
    assert "PARENT_REQUIREMENT_UNSATISFIED" in truth["reason_codes"]
    assert truth["canonical_evidence_empty"] is True
    assert truth["soak_started"] is False