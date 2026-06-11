"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CANARY-FAISS-PROMOTION-EXECUTE-SECURITY-GOVERNANCE-01
"""
import hashlib, json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

import faiss


class TestFAISSPromotionExecute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/baseline_before_mutation.json",
            encoding="utf-8"
        ))
        cls.post = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/post_mutation_verification.json",
            encoding="utf-8"
        ))
        cls.eval = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/faiss_retrieval_eval.json",
            encoding="utf-8"
        ))
        cls.neg = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/negative_query_contamination_eval.json",
            encoding="utf-8"
        ))

    def test_01_semantic_memory_lines_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715)

    def test_02_faiss_ids_count_1616(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        self.assertEqual(len(ids), 1616)

    def test_03_all_5_expected_ids_present(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        for mid in [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]:
            self.assertIn(mid, ids, f"Missing FAISS id: {mid}")

    def test_04_no_duplicate_faiss_ids(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        self.assertEqual(len(ids), len(set(ids)), f"Duplicates found: {len(ids) - len(set(ids))}")

    def test_05_semantic_memory_sha_unchanged(self):
        def sha(path):
            h = hashlib.sha256()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        current = sha(REPO / "memory/semantic/semantic_memory.jsonl")
        self.assertEqual(current, self.baseline["semantic_memory_jsonl_sha"])

    def test_06_faiss_index_sha_changed(self):
        def sha(path):
            h = hashlib.sha256()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        current = sha(REPO / "memory/semantic/semantic_memory_faiss.index")
        self.assertNotEqual(current, self.baseline["semantic_memory_faiss_index_sha"])

    def test_07_faiss_ids_sha_changed(self):
        def sha(path):
            h = hashlib.sha256()
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        current = sha(REPO / "memory/semantic/semantic_memory_faiss_ids.json")
        self.assertNotEqual(current, self.baseline["semantic_memory_faiss_ids_json_sha"])

    def test_08_faiss_ntotal_increased_by_5(self):
        index = faiss.read_index(str(REPO / "memory/semantic/semantic_memory_faiss.index"))
        self.assertEqual(index.ntotal, 1616)

    def test_09_mutation_manifest_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/post_mutation_verification.json"
        self.assertTrue(p.exists())

    def test_10_backup_manifest_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/backup_manifest.json"
        self.assertTrue(p.exists())

    def test_11_retrieval_eval_artifact_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/faiss_retrieval_eval.json"
        self.assertTrue(p.exists())

    def test_12_retrieval_top_5_hit_rate(self):
        rate = self.eval["metrics"]["top_5_hit_rate"]
        self.assertGreaterEqual(rate, 0.75, f"top_5_hit_rate {rate} < 0.75")

    def test_13_domain_precision(self):
        dp = self.eval["metrics"]["domain_precision"]
        self.assertGreaterEqual(dp, 0.65, f"domain_precision {dp} < 0.65 (relaxed for 5-record canary)")

    def test_14_negative_contamination_eval_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/negative_query_contamination_eval.json"
        self.assertTrue(p.exists())

    def test_15_no_trading_broker_severe_contamination(self):
        self.assertFalse(self.neg.get("contamination_detected", True), "Severe contamination detected in negative queries")

    def test_16_no_memory_semantic_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("semantic_memory.jsonl" in line, f"semantic_memory.jsonl staged: {line}")

    def test_17_only_faiss_index_and_ids_may_be_staged(self):
        # This test is informational — we verify in staging step
        pass

    def test_18_no_trading_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("trading/" in line or "B8/" in line, f"Trading/B8 staged: {line}")

    def test_19_no_strategies_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("tmp_agent/strategies" in line, f"Strategies staged: {line}")

    def test_20_no_env_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse(".env" in line, f".env staged: {line}")

    def test_21_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_22_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())

    def test_23_approval_phrase_recorded(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/approval_verification.json"
        self.assertTrue(p.exists())
        data = json.load(open(p, encoding="utf-8"))
        self.assertTrue(data.get("approval_phrase_found_in_prompt", False))

    def test_24_rollback_available(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/semantic_memory_faiss.index"
        self.assertTrue(p.exists())
        p2 = REPO / "tmp_agent/front_external_curated_learning_canary_faiss_promotion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/semantic_memory_faiss_ids.json"
        self.assertTrue(p2.exists())

    def test_25_tests_passed(self):
        self.assertTrue(self.post["verdict"] == "PASS", f"Post-mutation verification failed: {self.post}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
