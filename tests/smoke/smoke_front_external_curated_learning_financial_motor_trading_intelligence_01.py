"""Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-FINANCIAL-MOTOR-TRADING-INTELLIGENCE-01."""

import json
import subprocess
from pathlib import Path

import pytest

from brain.external_curated_learning_financial_motor_trading_intelligence import (
    build_curated_learning_plan,
    brain_financial_capability_map,
    canonical_taxonomy,
    cross_source_contrast_matrix,
    front_id,
    knowledge_record_schema,
    learning_domain,
    seed_candidate_sources,
    source_acceptance_criteria,
    source_contrast_scoring_rubric,
    source_rejection_criteria,
    source_safety_scoring_rubric,
    summarize_curated_learning_plan,
)


class TestModuleIdentity:
    def test_front_id(self):
        assert front_id() == "FRONT-EXTERNAL-CURATED-LEARNING-FINANCIAL-MOTOR-TRADING-INTELLIGENCE-01"

    def test_learning_domain_id(self):
        assert learning_domain()["id"] == "financial_motor_trading_intelligence"


class TestTaxonomy:
    def test_taxonomy_count(self):
        assert len(canonical_taxonomy()) >= 32

    def test_taxonomy_market_microstructure(self):
        assert any(t["tag"] == "market_microstructure" for t in canonical_taxonomy())

    def test_taxonomy_asset_classes(self):
        assert any(t["tag"] == "asset_classes_and_instruments" for t in canonical_taxonomy())

    def test_taxonomy_equities_etfs(self):
        assert any(t["tag"] == "equities_etfs" for t in canonical_taxonomy())

    def test_taxonomy_options_risk(self):
        assert any(t["tag"] == "options_risk" for t in canonical_taxonomy())

    def test_taxonomy_leverage_risk(self):
        assert any(t["tag"] == "futures_leverage_risk" for t in canonical_taxonomy())

    def test_taxonomy_portfolio_construction(self):
        assert any(t["tag"] == "portfolio_construction" for t in canonical_taxonomy())

    def test_taxonomy_factor_investing(self):
        assert any(t["tag"] == "factor_investing" for t in canonical_taxonomy())

    def test_taxonomy_stat_arb_risk(self):
        assert any(t["tag"] == "statistical_arbitrage_risk" for t in canonical_taxonomy())

    def test_taxonomy_backtesting_validity(self):
        assert any(t["tag"] == "backtesting_validity" for t in canonical_taxonomy())

    def test_taxonomy_walk_forward(self):
        assert any(t["tag"] == "walk_forward_validation" for t in canonical_taxonomy())

    def test_taxonomy_overfitting(self):
        assert any(t["tag"] == "overfitting_data_snooping" for t in canonical_taxonomy())

    def test_taxonomy_survivorship_bias(self):
        assert any(t["tag"] == "survivorship_bias" for t in canonical_taxonomy())

    def test_taxonomy_lookahead_bias(self):
        assert any(t["tag"] == "look_ahead_bias" for t in canonical_taxonomy())

    def test_taxonomy_transaction_costs(self):
        assert any(t["tag"] == "transaction_costs" for t in canonical_taxonomy())

    def test_taxonomy_slippage(self):
        assert any(t["tag"] == "slippage" for t in canonical_taxonomy())

    def test_taxonomy_liquidity_risk(self):
        assert any(t["tag"] == "liquidity_risk" for t in canonical_taxonomy())

    def test_taxonomy_position_sizing(self):
        assert any(t["tag"] == "position_sizing" for t in canonical_taxonomy())

    def test_taxonomy_drawdown_control(self):
        assert any(t["tag"] == "drawdown_control" for t in canonical_taxonomy())

    def test_taxonomy_paper_trading_governance(self):
        assert any(t["tag"] == "paper_trading_governance" for t in canonical_taxonomy())

    def test_taxonomy_broker_api_governance(self):
        assert any(t["tag"] == "broker_api_governance" for t in canonical_taxonomy())

    def test_taxonomy_financial_action_gates(self):
        assert any(t["tag"] == "financial_action_approval_gates" for t in canonical_taxonomy())

    def test_taxonomy_non_personalized_boundary(self):
        assert any(t["tag"] == "non_personalized_financial_education_boundary" for t in canonical_taxonomy())


class TestCriteriaAndRubrics:
    def test_acceptance_criteria_present(self):
        assert "must_have" in source_acceptance_criteria()

    def test_rejection_criteria_present(self):
        assert "automatic_reject" in source_rejection_criteria()

    def test_safety_rubric_present(self):
        assert "dimensions" in source_safety_scoring_rubric()

    def test_contrast_rubric_present(self):
        assert "required_fields" in source_contrast_scoring_rubric()


class TestSources:
    def test_seed_count(self):
        sources = seed_candidate_sources()
        assert len(sources) >= 28

    def test_source_groups_diversity(self):
        groups = {s["source_group"] for s in seed_candidate_sources()}
        required = {"academic_paper", "book_metadata", "regulatory", "repo", "docs", "framework", "internal_reference", "standard"}
        for g in required:
            assert g in groups, f"Missing source_group: {g}"

    def test_all_sources_have_required_fields(self):
        required = ["source_id", "title", "url", "taxonomy_tags"]
        for s in seed_candidate_sources():
            for f in required:
                assert s.get(f), f"Source {s.get('source_id')} missing {f}"

    def test_all_sources_have_safety_score(self):
        for s in seed_candidate_sources():
            assert isinstance(s.get("safety_score_estimate"), int)

    def test_all_sources_have_capability_target(self):
        for s in seed_candidate_sources():
            assert s.get("specific_brain_capability_target")

    def test_all_sources_ingestion_not_ingested(self):
        for s in seed_candidate_sources():
            assert s.get("ingestion_status") == "not_ingested"

    def test_all_sources_have_trading_execution_risk(self):
        for s in seed_candidate_sources():
            assert s.get("trading_execution_risk") in ("low", "medium", "high")

    def test_all_sources_have_personalized_advice_risk(self):
        for s in seed_candidate_sources():
            assert s.get("personalized_advice_risk") in ("low", "medium", "high")

    def test_all_sources_have_vendor_lock_in_risk(self):
        for s in seed_candidate_sources():
            assert s.get("vendor_lock_in_risk") in ("low", "medium", "high")

    def test_all_sources_have_overfitting_risk(self):
        for s in seed_candidate_sources():
            assert s.get("overfitting_risk") in ("low", "medium", "high")

    def test_all_sources_have_data_quality_risk(self):
        for s in seed_candidate_sources():
            assert s.get("data_quality_risk") in ("low", "medium", "high")

    def test_no_accepted_source_promises_guaranteed_returns(self):
        for s in seed_candidate_sources():
            if s["acceptance_status"] == "accept":
                notes = s.get("notes", "").lower()
                assert "guaranteed" not in notes or "return" not in notes, \
                    f"Accepted source {s['source_id']} may promise guaranteed returns in notes"

    def test_no_source_ingested(self):
        statuses = {s["ingestion_status"] for s in seed_candidate_sources()}
        assert statuses == {"not_ingested"}


class TestContrastAndCapabilities:
    def test_contrast_matrix_count(self):
        assert len(cross_source_contrast_matrix()) >= 10

    def test_capability_map_count(self):
        assert len(brain_financial_capability_map()) >= 24


class TestPlan:
    def test_build_plan_dry_run_only(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["ingestion_status"] == "dry_run_only"

    def test_build_plan_source_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["source_count"] >= 28

    def test_build_plan_taxonomy_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["taxonomy_count"] >= 32

    def test_build_plan_capability_count(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["capability_map_count"] >= 24

    def test_build_plan_memory_not_mutated(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["memory_mutated"] is False

    def test_build_plan_faiss_not_mutated(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["faiss_mutated"] is False

    def test_build_plan_trading_disabled(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["trading_enabled"] is False

    def test_build_plan_broker_not_connected(self):
        plan = build_curated_learning_plan()
        assert plan["summary"]["broker_connected"] is False

    def test_summary_matches_plan(self):
        plan = build_curated_learning_plan()
        summary = summarize_curated_learning_plan()
        assert summary["source_count"] == plan["summary"]["source_count"]


class TestKnowledgeSchema:
    def test_schema_has_required_fields(self):
        schema = knowledge_record_schema()
        assert "required_fields" in schema
        assert len(schema["required_fields"]) > 0

    def test_schema_has_forbidden_fields(self):
        schema = knowledge_record_schema()
        assert "forbidden_fields" in schema
        forbidden = schema["forbidden_fields"]
        assert "guaranteed_return_claim" in forbidden
        assert "personalized_recommendation" in forbidden
        assert "broker_credentials" in forbidden
        assert "executable_strategy" in forbidden


class TestGitSafety:
    def test_no_semantic_memory_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("memory/semantic" in p for p in staged)

    def test_no_faiss_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("faiss" in p.lower() for p in staged)

    def test_no_trading_files_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any(p.startswith("trading/") for p in staged)

    def test_no_b8_files_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any(p.startswith("B8/") for p in staged)

    def test_no_strategies_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("tmp_agent/strategies" in p for p in staged)

    def test_no_previous_curated_modules_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        forbidden = [
            "brain/external_curated_learning_agentic_systems.py",
            "brain/external_curated_learning_evaluation_benchmarking.py",
            "brain/external_curated_learning_memory_rag_knowledge_architecture.py",
            "brain/external_curated_learning_security_governance_sandboxing.py",
            "brain/external_curated_learning_autonomous_coding_patch_generation.py",
        ]
        for f in forbidden:
            assert f not in staged, f"Previous curated module {f} should not be staged"

    def test_roadmap_valid_json(self):
        roadmap = Path(__file__).resolve().parents[2] / "ROADMAP_STATUS.json"
        assert roadmap.exists()
        data = json.loads(roadmap.read_text(encoding="utf-8"))
        assert "current_head" in data
        assert "completed_fronts" in data

    def test_ledger_exists(self):
        ledger = Path(__file__).resolve().parents[2] / "docs" / "MIGRATION_CONTROL_LEDGER.md"
        assert ledger.exists()
        text = ledger.read_text(encoding="utf-8")
        assert len(text) > 0
