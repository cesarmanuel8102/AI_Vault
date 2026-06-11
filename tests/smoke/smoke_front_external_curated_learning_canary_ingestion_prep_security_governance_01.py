"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01
"""
import json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from brain.external_curated_learning_canary_ingestion_prep_security_governance import (
    front_id,
    get_canary_batch_id,
    select_security_governance_canary_sources,
    build_proposed_memory_records,
    validate_proposed_memory_record,
    validate_canary_prep_package,
    build_human_approval_package,
)


class TestCanaryIngestionPrep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selected = select_security_governance_canary_sources()
        cls.records = build_proposed_memory_records()
        cls.approval = build_human_approval_package()
        cls.validation = validate_canary_prep_package()

    # --- Module imports ---
    def test_01_prep_module_imports(self):
        self.assertTrue(callable(front_id))
        self.assertTrue(callable(get_canary_batch_id))
        self.assertTrue(callable(select_security_governance_canary_sources))
        self.assertTrue(callable(build_proposed_memory_records))
        self.assertTrue(callable(validate_proposed_memory_record))
        self.assertTrue(callable(validate_canary_prep_package))
        self.assertTrue(callable(build_human_approval_package))

    def test_02_front_id_exact(self):
        self.assertEqual(front_id(), "FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01")

    def test_03_batch_id_exists(self):
        bid = get_canary_batch_id()
        self.assertIsInstance(bid, str)
        self.assertTrue(len(bid) > 0)

    # --- Selected sources ---
    def test_04_selected_count_in_range(self):
        self.assertTrue(3 <= len(self.selected) <= 5)

    def test_05_all_accepted(self):
        for s in self.selected:
            self.assertEqual(s["acceptance_status"], "accept")

    def test_06_no_hold(self):
        for s in self.selected:
            self.assertNotEqual(s["acceptance_status"], "hold")

    def test_07_no_reject(self):
        for s in self.selected:
            self.assertNotEqual(s["acceptance_status"], "reject")

    def test_08_no_candidate(self):
        for s in self.selected:
            self.assertNotEqual(s["acceptance_status"], "candidate")

    def test_09_no_financial_source(self):
        financial_ids = ["financial", "trading", "broker", "portfolio", "risk_model"]
        for s in self.selected:
            sid = s["source_id"].lower()
            self.assertFalse(any(f in sid for f in financial_ids), f"Financial source found: {sid}")

    def test_10_no_coding_source(self):
        coding_ids = ["coding", "patch", "autonomous_code", "code_gen"]
        for s in self.selected:
            sid = s["source_id"].lower()
            self.assertFalse(any(c in sid for c in coding_ids), f"Coding source found: {sid}")

    # --- Proposed records ---
    def test_11_records_count_equals_selected(self):
        self.assertEqual(len(self.records), len(self.selected))

    def test_12_schema_version_correct(self):
        for r in self.records:
            self.assertEqual(r["schema_version"], "controlled_ingestion_memory_record_v1")

    def test_13_domain_correct(self):
        for r in self.records:
            self.assertEqual(r["domain"], "security_governance_sandboxing")

    def test_14_acceptance_status_accept(self):
        for r in self.records:
            self.assertEqual(r["acceptance_status"], "accept")

    def test_15_ingestion_status_proposed_only(self):
        for r in self.records:
            self.assertEqual(r["ingestion_status"], "proposed_only")

    def test_16_memory_id_present(self):
        for r in self.records:
            self.assertIn("memory_id", r)
            self.assertTrue(len(r["memory_id"]) > 0)

    def test_17_memory_id_unique(self):
        ids = [r["memory_id"] for r in self.records]
        self.assertEqual(len(ids), len(set(ids)))

    def test_18_source_id_present(self):
        for r in self.records:
            self.assertIn("source_id", r)
            self.assertTrue(len(r["source_id"]) > 0)

    def test_19_source_url_present(self):
        for r in self.records:
            self.assertIn("source_url", r)
            self.assertTrue(len(r["source_url"]) > 0)

    def test_20_source_license_present(self):
        for r in self.records:
            self.assertIn("source_license_or_status", r)

    def test_21_content_summary_length(self):
        for r in self.records:
            summary = r.get("content_summary", "")
            self.assertLessEqual(len(summary), 1200)

    def test_22_retrieval_phrases_count(self):
        for r in self.records:
            phrases = r.get("retrieval_phrases", [])
            self.assertTrue(3 <= len(phrases) <= 8)

    def test_23_faiss_eligible_false(self):
        for r in self.records:
            self.assertIs(r["faiss_eligible"], False)

    def test_24_faiss_embedding_text_empty(self):
        for r in self.records:
            self.assertEqual(r.get("faiss_embedding_text", None), "")

    def test_25_no_chain_of_thought(self):
        for r in self.records:
            self.assertNotIn("chain_of_thought", r)

    def test_26_no_executable_code(self):
        for r in self.records:
            self.assertNotIn("executable_code", r)

    def test_27_no_trading_signal(self):
        for r in self.records:
            self.assertNotIn("trading_signal", r)

    def test_28_no_broker_api(self):
        for r in self.records:
            self.assertNotIn("broker_api", r)

    # --- Approval package ---
    def test_29_approval_requires_user_approval(self):
        self.assertTrue(self.approval["requires_user_approval_before_mutation"])

    def test_30_approval_memory_now_false(self):
        self.assertIs(self.approval["memory_mutation_authorized_now"], False)

    def test_31_approval_faiss_now_false(self):
        self.assertIs(self.approval["faiss_mutation_authorized_now"], False)

    def test_32_expected_memory_before_1710(self):
        self.assertEqual(self.approval["expected_memory_line_count_before"], 1710)

    def test_33_expected_faiss_before_1611(self):
        self.assertEqual(self.approval["expected_faiss_ids_count_before"], 1611)

    def test_34_faiss_eligible_count_zero(self):
        self.assertEqual(self.approval["faiss_eligible_count"], 0)

    def test_35_approval_phrase_required(self):
        self.assertIn("APPROVE_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH", self.approval["approval_phrase_required"])

    def test_36_denial_phrase_exists(self):
        self.assertIn("DENY_SECURITY_GOVERNANCE_CANARY_INGESTION_BATCH", self.approval["denial_phrase"])

    # --- Validation ---
    def test_37_package_validation_pass(self):
        self.assertTrue(self.validation["package_valid"])
        self.assertEqual(len(self.validation["validation_errors"]), 0)

    # --- Evidence files exist ---
    def test_38_retrieval_eval_plan_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_ingestion_prep_security_governance_01/retrieval_eval_plan.json"
        self.assertTrue(p.exists())

    def test_39_backup_rollback_plan_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_ingestion_prep_security_governance_01/backup_rollback_plan.json"
        self.assertTrue(p.exists())

    def test_40_human_approval_package_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_ingestion_prep_security_governance_01/human_approval_package.json"
        self.assertTrue(p.exists())

    # --- No mutation ---
    def test_41_no_memory_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("memory/semantic" in line, f"Memory staged: {line}")

    def test_42_no_faiss_index_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("faiss.index" in line, f"FAISS index staged: {line}")

    def test_43_no_faiss_ids_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("faiss_ids.json" in line, f"FAISS ids staged: {line}")

    def test_44_no_trading_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("trading/" in line or "B8/" in line, f"Trading/B8 staged: {line}")

    def test_45_no_strategies_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("tmp_agent/strategies" in line, f"Strategies staged: {line}")

    def test_46_no_env_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse(".env" in line, f".env staged: {line}")

    def test_47_roadmap_valid(self):
        roadmap = REPO / "ROADMAP_STATUS.json"
        data = json.load(open(roadmap, encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_48_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())
        content = ledger.read_text(encoding="utf-8")
        self.assertIn("FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP-SECURITY-GOVERNANCE-01", content)

    def test_49_no_main_py_modified(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("brain_v9/main.py" in line, f"main.py staged: {line}")

    def test_50_no_session_modified(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("brain_v9/core/session.py" in line, f"session.py staged: {line}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
