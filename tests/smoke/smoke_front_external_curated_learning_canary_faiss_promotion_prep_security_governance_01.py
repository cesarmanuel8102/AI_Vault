"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-PREP-SECURITY-GOVERNANCE-01
"""
import json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from brain.external_curated_learning_canary_faiss_promotion_prep_security_governance import (
    front_id,
    get_batch_id,
    get_expected_memory_ids,
    load_canary_records_from_memory,
    validate_faiss_promotion_candidate,
    build_faiss_embedding_text,
    build_faiss_promotion_plan,
    build_human_approval_package,
)


class TestFAISSPromotionPrep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_canary_records_from_memory()
        cls.plan = build_faiss_promotion_plan()
        cls.approval = build_human_approval_package()
        cls.baseline = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_prep_security_governance_01/baseline_inventory.json",
            encoding="utf-8"
        ))

    # --- Module basics ---
    def test_01_front_id_exact(self):
        self.assertEqual(front_id(), "FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-PREP-SECURITY-GOVERNANCE-01")

    def test_02_batch_id_exact(self):
        self.assertEqual(get_batch_id(), "SEC_GOV_CANARY_001")

    def test_03_expected_memory_ids_exact(self):
        expected = [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]
        self.assertEqual(get_expected_memory_ids(), expected)

    # --- Records loading ---
    def test_04_loads_exactly_5_records(self):
        self.assertEqual(len(self.records), 5)

    def test_05_all_expected_memory_ids_present(self):
        found = {r["memory_id"] for r in self.records}
        for mid in get_expected_memory_ids():
            self.assertIn(mid, found, f"Missing memory_id: {mid}")

    def test_06_all_source_ids_present(self):
        expected = {"nist_csf", "nist_ai_rmf", "opa_docs", "mitre_atlas", "gvisor_docs"}
        found = {r["source_id"] for r in self.records}
        self.assertEqual(found, expected)

    def test_07_all_domain_security_governance(self):
        for r in self.records:
            self.assertEqual(r["domain"], "security_governance_sandboxing")

    def test_08_all_ingestion_status_ingested(self):
        for r in self.records:
            self.assertEqual(r["ingestion_status"], "ingested_memory_only")

    def test_09_all_faiss_eligible_false(self):
        for r in self.records:
            self.assertIs(r["faiss_eligible"], False)

    def test_10_all_faiss_embedding_text_empty(self):
        for r in self.records:
            self.assertEqual(r.get("faiss_embedding_text", None), "")

    # --- Validation ---
    def test_11_all_candidates_validate_zero_errors(self):
        for r in self.records:
            errors = validate_faiss_promotion_candidate(r)
            self.assertEqual(errors, [], f"Validation errors for {r['memory_id']}: {errors}")

    # --- Embedding text ---
    def test_12_embedding_text_built_for_every_record(self):
        for r in self.records:
            text = build_faiss_embedding_text(r)
            self.assertTrue(len(text) > 0, f"Empty embedding text for {r['memory_id']}")

    def test_13_embedding_text_deterministic(self):
        for r in self.records:
            t1 = build_faiss_embedding_text(r)
            t2 = build_faiss_embedding_text(r)
            self.assertEqual(t1, t2, f"Non-deterministic embedding text for {r['memory_id']}")

    def test_14_embedding_text_length_gt_100(self):
        for r in self.records:
            text = build_faiss_embedding_text(r)
            self.assertGreater(len(text), 100, f"Embedding text too short for {r['memory_id']}")

    def test_15_embedding_text_length_lt_2500(self):
        for r in self.records:
            text = build_faiss_embedding_text(r)
            self.assertLess(len(text), 2500, f"Embedding text too long for {r['memory_id']}")

    def test_16_embedding_text_no_chain_of_thought(self):
        for r in self.records:
            text = build_faiss_embedding_text(r).lower()
            self.assertNotIn("chain_of_thought", text)

    def test_17_embedding_text_no_broker_api(self):
        for r in self.records:
            text = build_faiss_embedding_text(r).lower()
            self.assertNotIn("broker_api", text)

    def test_18_embedding_text_no_trading_signal(self):
        for r in self.records:
            text = build_faiss_embedding_text(r).lower()
            self.assertNotIn("trading_signal", text)

    def test_19_embedding_text_no_executable_code(self):
        for r in self.records:
            text = build_faiss_embedding_text(r).lower()
            self.assertNotIn("executable_code", text)

    # --- Promotion plan ---
    def test_20_promotion_plan_status_proposed_only(self):
        self.assertEqual(self.plan["promotion_status"], "proposed_only")

    def test_21_expected_faiss_ids_before_1611(self):
        self.assertEqual(self.plan["current_faiss_ids_count_expected"], 1611)

    def test_22_expected_faiss_ids_after_1616(self):
        self.assertEqual(self.plan["expected_faiss_ids_count_after_if_approved"], 1616)

    def test_23_faiss_index_mutation_authorized_now_false(self):
        self.assertIs(self.plan["faiss_index_mutation_authorized_now"], False)

    def test_24_faiss_ids_mutation_authorized_now_false(self):
        self.assertIs(self.plan["faiss_ids_mutation_authorized_now"], False)

    def test_25_embeddings_creation_authorized_now_false(self):
        self.assertIs(self.plan["embeddings_creation_authorized_now"], False)

    # --- Approval package ---
    def test_26_approval_package_requires_user_approval(self):
        self.assertTrue(self.approval["requires_user_approval_before_mutation"])

    def test_27_approval_phrase_exact(self):
        expected = "APPROVE_SECURITY_GOVERNANCE_CANARY_FAISS_PROMOTION_BATCH_SEC_GOV_CANARY_001"
        self.assertEqual(self.approval["approval_phrase_required"], expected)

    def test_28_denial_phrase_exact(self):
        expected = "DENY_SECURITY_GOVERNANCE_CANARY_FAISS_PROMOTION_BATCH_SEC_GOV_CANARY_001"
        self.assertEqual(self.approval["denial_phrase"], expected)

    # --- Evidence artifacts ---
    def test_29_backup_rollback_plan_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_prep_security_governance_01/backup_rollback_plan.json"
        self.assertTrue(p.exists())

    def test_30_future_execution_plan_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_prep_security_governance_01/future_execution_plan.json"
        self.assertTrue(p.exists())

    # --- Counts ---
    def test_31_memory_line_count_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715, f"Expected 1715 lines, got {count}")

    def test_32_faiss_ids_count_1611(self):
        count = len(json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8")))
        self.assertEqual(count, 1611, f"Expected 1611 FAISS ids, got {count}")

    # --- Git safety ---
    def test_33_no_memory_semantic_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("memory/semantic" in line, f"Memory staged: {line}")

    def test_34_no_faiss_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("faiss" in line.lower(), f"FAISS staged: {line}")

    def test_35_no_trading_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("trading/" in line or "B8/" in line, f"Trading/B8 staged: {line}")

    def test_36_no_strategies_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("tmp_agent/strategies" in line, f"Strategies staged: {line}")

    def test_37_no_env_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse(".env" in line, f".env staged: {line}")

    def test_38_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_39_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())

    def test_40_all_valid_true(self):
        self.assertTrue(self.plan["all_valid"], f"Not all candidates valid: {[c['validation_errors'] for c in self.plan['candidates'] if not c['valid']]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
