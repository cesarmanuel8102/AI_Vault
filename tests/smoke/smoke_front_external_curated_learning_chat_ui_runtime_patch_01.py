"""Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CHAT-UI-RUNTIME-PATCH-01.

This front tests that the curated learning helper is callable and correct,
acknowledging that the local chat runtime lives outside this repository.
"""

import json
import subprocess
from pathlib import Path

import pytest

from brain.curated_learning_chat_access import (
    answer_chat_probe,
    build_chat_safe_context,
    front_id,
    get_canonical_curated_learning_inventory,
    get_rejected_sources_summary,
    get_canary_ingestion_policy,
)


class TestModuleIdentity:
    def test_front_id(self):
        assert front_id() == "FRONT-EXTERNAL-CURATED-LEARNING-CHAT-UI-USAGE-REPAIR-01"


class TestHelperAvailability:
    def test_helper_importable(self):
        from brain.curated_learning_chat_access import answer_chat_probe
        assert callable(answer_chat_probe)

    def test_context_builder_importable(self):
        from brain.curated_learning_chat_access import build_chat_safe_context
        assert callable(build_chat_safe_context)


class TestInventory:
    def test_six_domains_present(self):
        inv = get_canonical_curated_learning_inventory()
        domains = [d["domain"] for d in inv["domains"] if "error" not in d]
        assert len(domains) == 6

    def test_total_sources_computed(self):
        inv = get_canonical_curated_learning_inventory()
        assert inv["totals"]["source_count"] > 0

    def test_total_accepted_computed(self):
        inv = get_canonical_curated_learning_inventory()
        assert inv["totals"]["accepted_count"] > 0

    def test_totals_equal_sum(self):
        inv = get_canonical_curated_learning_inventory()
        computed_src = sum(d["source_count"] for d in inv["domains"] if "error" not in d)
        assert inv["totals"]["source_count"] == computed_src


class TestDirectProbes:
    def test_q01_all_domains_and_counts(self):
        r = answer_chat_probe(probe_id="Q01")
        assert r["decision"] == "explain"
        txt = r["final_answer"].lower()
        assert "agentic" in txt
        assert "evaluation" in txt
        assert "memory" in txt
        assert "security" in txt
        assert any(x in txt for x in ["coding", "patch"])
        assert "financial" in txt
        # Should have numeric counts
        assert any(ch.isdigit() for ch in r["final_answer"])

    def test_q02_rejected_sources(self):
        r = answer_chat_probe(probe_id="Q02")
        assert r["decision"] == "explain"
        txt = r["final_answer"].lower()
        assert any(x in txt for x in ["rechazadas", "rejected", "unattributed", "guaranteed"])

    def test_q03_financial_locked(self):
        r = answer_chat_probe(probe_id="Q03")
        assert "financial" in r["final_answer"].lower()
        assert any(x in r["final_answer"].lower() for x in ["locked", "bloqueados"])

    def test_q03_coding_locked(self):
        r = answer_chat_probe(probe_id="Q03")
        assert any(x in r["final_answer"].lower() for x in ["coding", "autonomous"])

    def test_q04_first_canary_security(self):
        r = answer_chat_probe(probe_id="Q04")
        assert "security_governance_sandboxing" in r["final_answer"]

    def test_q04_range_3_to_5(self):
        r = answer_chat_probe(probe_id="Q04")
        assert "3" in r["final_answer"] and "5" in r["final_answer"]

    def test_q05_denies_mass_ingestion(self):
        r = answer_chat_probe(probe_id="Q05")
        assert r["decision"] == "deny"
        assert "canary" in r["final_answer"].lower()


class TestCanaryPolicy:
    def test_first_canary_domain(self):
        p = get_canary_ingestion_policy()
        assert p["first_canary_domain"] == "security_governance_sandboxing"

    def test_mass_ingestion_false(self):
        p = get_canary_ingestion_policy()
        assert p["mass_ingestion_allowed"] is False

    def test_financial_locked(self):
        p = get_canary_ingestion_policy()
        assert p["financial_domain_locked"] is True

    def test_coding_locked(self):
        p = get_canary_ingestion_policy()
        assert p["autonomous_coding_domain_locked"] is True


class TestChatSafeContext:
    def test_context_length(self):
        ctx = build_chat_safe_context(max_chars=6000)
        assert len(ctx) <= 6000

    def test_context_contains_inventory(self):
        ctx = build_chat_safe_context()
        assert "CURATED LEARNING INVENTORY" in ctx

    def test_context_no_chain_of_thought(self):
        ctx = build_chat_safe_context()
        assert "reasoning trace" not in ctx.lower()
        assert "internal thought" not in ctx.lower()

    def test_context_no_broker_credentials(self):
        ctx = build_chat_safe_context()
        assert "broker credential" not in ctx.lower()

    def test_context_no_trading_signal(self):
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

    def test_roadmap_valid(self):
        roadmap = Path(__file__).resolve().parents[2] / "ROADMAP_STATUS.json"
        assert roadmap.exists()
        data = json.loads(roadmap.read_text(encoding="utf-8"))
        assert "current_head" in data

    def test_ledger_exists(self):
        ledger = Path(__file__).resolve().parents[2] / "docs" / "MIGRATION_CONTROL_LEDGER.md"
        assert ledger.exists()
        assert len(ledger.read_text(encoding="utf-8")) > 0
