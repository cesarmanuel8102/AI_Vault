"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-POST-PROMOTION-VERIFY-SECURITY-GOVERNANCE-01
"""
import hashlib, json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import faiss


class TestFAISSPostPromotionVerify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_post_promotion_verify_security_governance_01/canonical_inventory.json",
            encoding="utf-8"
        ))
        cls.promoted = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_post_promotion_verify_security_governance_01/promoted_ids_verification.json",
            encoding="utf-8"
        ))
        cls.reeval = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_post_promotion_verify_security_governance_01/faiss_retrieval_reeval.json",
            encoding="utf-8"
        ))
        cls.legacy = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_post_promotion_verify_security_governance_01/legacy_path_audit.json",
            encoding="utf-8"
        ))

    def test_01_semantic_memory_lines_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715)

    def test_02_faiss_ids_count_1616(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        self.assertEqual(len(ids), 1616)

    def test_03_faiss_ntotal_1616(self):
        index = faiss.read_index(str(REPO / "memory/semantic/semantic_memory_faiss.index"))
        self.assertEqual(index.ntotal, 1616)

    def test_04_all_5_promoted_ids_present(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        for mid in [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]:
            self.assertIn(mid, ids, f"Missing promoted id: {mid}")

    def test_05_no_duplicate_faiss_ids(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        self.assertEqual(len(ids), len(set(ids)), f"Duplicates found: {len(ids) - len(set(ids))}")

    def test_06_all_5_map_to_semantic_records(self):
        self.assertTrue(self.promoted["checks"]["all_present_in_memory"], "Not all promoted ids map to semantic memory records")

    def test_07_all_domain_security_governance(self):
        self.assertTrue(self.promoted["checks"]["all_domain_security_governance_sandboxing"], "Not all promoted records have correct domain")

    def test_08_retrieval_reeval_artifact_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_post_promotion_verify_security_governance_01/faiss_retrieval_reeval.json"
        self.assertTrue(p.exists())

    def test_09_top_5_hit_rate(self):
        rate = self.reeval["metrics"]["top_5_hit_rate"]
        self.assertGreaterEqual(rate, 0.75, f"top_5_hit_rate {rate} < 0.75")

    def test_10_contamination_false(self):
        self.assertFalse(self.reeval["contamination_detected"], "Contamination detected in retrieval re-eval")

    def test_11_negative_contamination_eval_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_post_promotion_verify_security_governance_01/negative_contamination_reeval.json"
        self.assertTrue(p.exists())

    def test_12_no_severe_broker_trading_contamination(self):
        neg = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_post_promotion_verify_security_governance_01/negative_contamination_reeval.json",
            encoding="utf-8"
        ))
        self.assertFalse(neg.get("contamination_detected", True), "Severe broker/trading contamination detected")

    def test_13_legacy_path_audit_exists(self):
        self.assertTrue(self.legacy["legacy_path_exists"], "Legacy path audit artifact missing")

    def test_14_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_15_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())

    def test_16_no_memory_semantic_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("semantic_memory.jsonl" in line, f"semantic_memory.jsonl staged: {line}")

    def test_17_no_trading_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("trading/" in line or "B8/" in line, f"Trading/B8 staged: {line}")

    def test_18_no_strategies_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("tmp_agent/strategies" in line, f"Strategies staged: {line}")

    def test_19_no_env_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse(".env" in line, f".env staged: {line}")

    def test_20_canonical_inventory_pass(self):
        self.assertEqual(self.canonical["verdict"], "PASS", f"Canonical inventory failed: {self.canonical}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
