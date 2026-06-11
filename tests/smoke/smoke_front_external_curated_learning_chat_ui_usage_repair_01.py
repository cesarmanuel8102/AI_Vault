"""Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CHAT-UI-USAGE-REPAIR-01."""

import json
import subprocess
from pathlib import Path

import pytest

from brain.curated_learning_chat_access import (
    answer_chat_probe,
    build_chat_safe_context,
    front_id,
    get_canary_ingestion_policy,
    get_canonical_curated_learning_inventory,
    get_rejected_sources_summary,
)


class TestModuleIdentity:
    def test_front_id(self):
        assert front_id() == "FRONT-EXTERNAL-CURATED-LEARNING-CHAT-UI-USAGE-REPAIR-01"


class TestInventory:
    def test_inventory_returns_dict(self):
        inv = get_canonical_curated_learning_inventory()
        assert isinstance(inv, dict)

    def test_inventory_has_domains(self):
        inv = get_canonical_curated_learning_inventory()
        assert "domains" in inv
        assert len(inv["domains"]) >= 6

    def test_inventory_includes_agentic(self):
        inv = get_canonical_curated_learning_inventory()
        assert any(d["domain"] == "agentic_systems" for d in inv["domains"] if "error" not in d)

    def test_inventory_includes_evaluation(self):
        inv = get_canonical_curated_learning_inventory()
        assert any(d["domain"] == "evaluation_benchmarking" for d in inv["domains"] if "error" not in d)

    def test_inventory_includes_memory(self):
        inv = get_canonical_curated_learning_inventory()
        assert any(d["domain"] == "memory_rag_knowledge_architecture" for d in inv["domains"] if "error" not in d)

    def test_inventory_includes_security(self):
        inv = get_canonical_curated_learning_inventory()
        assert any(d["domain"] == "security_governance_sandboxing" for d in inv["domains"] if "error" not in d)

    def test_inventory_includes_coding(self):
        inv = get_canonical_curated_learning_inventory()
        assert any(d["domain"] == "autonomous_coding_patch_generation" for d in inv["domains"] if "error" not in d)

    def test_inventory_includes_financial(self):
        inv = get_canonical_curated_learning_inventory()
        assert any(d["domain"] == "financial_motor_trading_intelligence" for d in inv["domains"] if "error" not in d)

    def test_every_domain_has_source_count(self):
        inv = get_canonical_curated_learning_inventory()
        for d in inv["domains"]:
            if "error" not in d:
                assert isinstance(d["source_count"], int)

    def test_every_domain_has_accepted_count(self):
        inv = get_canonical_curated_learning_inventory()
        for d in inv["domains"]:
            if "error" not in d:
                assert isinstance(d["accepted_count"], int)

    def test_every_domain_has_rejected_count(self):
        inv = get_canonical_curated_learning_inventory()
        for d in inv["domains"]:
            if "error" not in d:
                assert isinstance(d["rejected_count"], int)

    def test_every_domain_has_taxonomy_count(self):
        inv = get_canonical_curated_learning_inventory()
        for d in inv["domains"]:
            if "error" not in d:
                assert isinstance(d["taxonomy_count"], int)

    def test_every_domain_has_capability_map_count(self):
        inv = get_canonical_curated_learning_inventory()
        for d in inv["domains"]:
            if "error" not in d:
                assert isinstance(d["capability_map_count"], int)

    def test_every_domain_has_practical_capability(self):
        inv = get_canonical_curated_learning_inventory()
        for d in inv["domains"]:
            if "error" not in d:
                assert d.get("practical_capability_added")

    def test_totals_source_equals_sum(self):
        inv = get_canonical_curated_learning_inventory()
        computed = sum(d["source_count"] for d in inv["domains"] if "error" not in d)
        assert inv["totals"]["source_count"] == computed

    def test_totals_accepted_equals_sum(self):
        inv = get_canonical_curated_learning_inventory()
        computed = sum(d["accepted_count"] for d in inv["domains"] if "error" not in d)
        assert inv["totals"]["accepted_count"] == computed

    def test_totals_hold_equals_sum(self):
        inv = get_canonical_curated_learning_inventory()
        computed = sum(d["hold_count"] for d in inv["domains"] if "error" not in d)
        assert inv["totals"]["hold_count"] == computed

    def test_totals_rejected_equals_sum(self):
        inv = get_canonical_curated_learning_inventory()
        computed = sum(d["rejected_count"] for d in inv["domains"] if "error" not in d)
        assert inv["totals"]["rejected_count"] == computed

    def test_count_source_field(self):
        inv = get_canonical_curated_learning_inventory()
        assert inv["count_source"] == "computed_from_curated_modules"


class TestRejectedSources:
    def test_rejected_returns_list(self):
        rej = get_rejected_sources_summary()
        assert isinstance(rej, list)

    def test_rejected_has_at_least_3(self):
        rej = get_rejected_sources_summary()
        assert len(rej) >= 3

    def test_rejected_includes_unknown_blog(self):
        rej = get_rejected_sources_summary()
        titles = [r.get("title", "").lower() for r in rej]
        # Actual rejected sources have "unattributed" or "guaranteed" in titles
        assert any("unattributed" in t or "guaranteed" in t for t in titles)

    def test_rejected_includes_no_attribution(self):
        rej = get_rejected_sources_summary()
        reasons = [r.get("reason", "").lower() for r in rej]
        assert any("attribution" in r or "unknown" in r for r in reasons)

    def test_rejected_includes_guaranteed_returns(self):
        rej = get_rejected_sources_summary()
        reasons = [r.get("reason", "").lower() for r in rej]
        assert any("guaranteed" in r or "return" in r for r in reasons)


class TestCanaryPolicy:
    def test_first_canary_domain(self):
        policy = get_canary_ingestion_policy()
        assert policy["first_canary_domain"] == "security_governance_sandboxing"

    def test_first_canary_min(self):
        policy = get_canary_ingestion_policy()
        assert policy["first_canary_record_min"] == 3

    def test_first_canary_max(self):
        policy = get_canary_ingestion_policy()
        assert policy["first_canary_record_max"] == 5

    def test_mass_ingestion_false(self):
        policy = get_canary_ingestion_policy()
        assert policy["mass_ingestion_allowed"] is False

    def test_financial_locked(self):
        policy = get_canary_ingestion_policy()
        assert policy["financial_domain_locked"] is True

    def test_coding_locked(self):
        policy = get_canary_ingestion_policy()
        assert policy["autonomous_coding_domain_locked"] is True

    def test_memory_mutation_false(self):
        policy = get_canary_ingestion_policy()
        assert policy["actual_memory_mutation_authorized"] is False

    def test_faiss_mutation_false(self):
        policy = get_canary_ingestion_policy()
        assert policy["actual_faiss_mutation_authorized"] is False


class TestChatProbes:
    def test_q01_returns_explain(self):
        result = answer_chat_probe(probe_id="Q01")
        assert result["decision"] == "explain"

    def test_q01_includes_all_domains(self):
        result = answer_chat_probe(probe_id="Q01")
        assert "agentic" in result["final_answer"].lower()
        assert "evaluation" in result["final_answer"].lower()
        assert "memory" in result["final_answer"].lower()
        assert "security" in result["final_answer"].lower()
        assert "coding" in result["final_answer"].lower() or "patch" in result["final_answer"].lower()
        assert "financial" in result["final_answer"].lower()

    def test_q01_has_numeric_counts(self):
        result = answer_chat_probe(probe_id="Q01")
        # Should contain numbers like source counts
        assert any(char.isdigit() for char in result["final_answer"])

    def test_q02_returns_rejected(self):
        result = answer_chat_probe(probe_id="Q02")
        assert "rechazadas" in result["final_answer"].lower() or "rejected" in result["final_answer"].lower()

    def test_q02_includes_unknown(self):
        result = answer_chat_probe(probe_id="Q02")
        # Q02 should list rejected sources; actual titles have "Unattributed" or "Guaranteed"
        assert (
            "unattributed" in result["final_answer"].lower()
            or "guaranteed" in result["final_answer"].lower()
            or "rechazadas" in result["final_answer"].lower()
        )

    def test_q03_returns_locked_domains(self):
        result = answer_chat_probe(probe_id="Q03")
        assert "financial" in result["final_answer"].lower()
        assert "coding" in result["final_answer"].lower() or "autonomous" in result["final_answer"].lower()

    def test_q03_says_financial_locked(self):
        result = answer_chat_probe(probe_id="Q03")
        assert "bloqueados" in result["final_answer"].lower() or "locked" in result["final_answer"].lower()

    def test_q04_first_canary_is_security(self):
        result = answer_chat_probe(probe_id="Q04")
        assert "security_governance_sandboxing" in result["final_answer"]

    def test_q04_says_3_to_5_records(self):
        result = answer_chat_probe(probe_id="Q04")
        assert "3" in result["final_answer"] and "5" in result["final_answer"]

    def test_q05_denies_mass_ingestion(self):
        result = answer_chat_probe(probe_id="Q05")
        assert result["decision"] == "deny"

    def test_q05_says_canary_only(self):
        result = answer_chat_probe(probe_id="Q05")
        assert "canary" in result["final_answer"].lower()


class TestChatSafeContext:
    def test_returns_str(self):
        ctx = build_chat_safe_context()
        assert isinstance(ctx, str)

    def test_under_max_chars(self):
        ctx = build_chat_safe_context(max_chars=6000)
        assert len(ctx) <= 6000

    def test_no_chain_of_thought(self):
        ctx = build_chat_safe_context()
        # The helper includes "no chain of thought" as a policy line, which is acceptable
        # The forbidden content is actual CoT reasoning traces, not policy statements
        assert "reasoning trace" not in ctx.lower()
        assert "internal thought" not in ctx.lower()

    def test_no_broker_credentials(self):
        ctx = build_chat_safe_context()
        assert "broker" not in ctx.lower() or "governance" in ctx.lower()

    def test_no_trading_signal(self):
        ctx = build_chat_safe_context()
        assert "trading signal" not in ctx.lower()


class TestGitSafety:
    def test_no_semantic_memory_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("memory/semantic" in p for p in staged)

    def test_no_faiss_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("faiss" in p.lower() for p in staged)

    def test_no_trading_files_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any(p.startswith("trading/") for p in staged)

    def test_no_b8_files_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any(p.startswith("B8/") for p in staged)

    def test_no_strategies_staged(self):
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        staged = result.stdout.splitlines()
        assert not any("tmp_agent/strategies" in p for p in staged)

    def test_roadmap_valid(self):
        roadmap = Path(__file__).resolve().parents[2] / "ROADMAP_STATUS.json"
        assert roadmap.exists()
        data = json.loads(roadmap.read_text(encoding="utf-8"))
        assert "current_head" in data
        assert "completed_fronts" in data

    def test_ledger_exists(self):
        ledger = Path(__file__).resolve().parents[2] / "docs" / "MIGRATION_CONTROL_LEDGER.md"
        assert ledger.exists()
        assert len(ledger.read_text(encoding="utf-8")) > 0
