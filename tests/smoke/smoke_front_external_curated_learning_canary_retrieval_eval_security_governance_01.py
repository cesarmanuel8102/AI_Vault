"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CANARY-RETRIEVAL-EVAL-SECURITY-GOVERNANCE-01
"""
import json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))


class TestCanaryRetrievalEval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canary_records = []
        with open(REPO / "memory/semantic/semantic_memory.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    if record.get("ingestion_batch_id") == "SEC_GOV_CANARY_001":
                        cls.canary_records.append(record)
        
        cls.direct_eval = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_retrieval_eval_security_governance_01/direct_memory_retrieval_eval.json",
            encoding="utf-8"
        ))
        cls.negative_eval = json.load(open(
            REPO / "tmp_agent/front_external_curated_learning_canary_retrieval_eval_security_governance_01/negative_query_contamination_eval.json",
            encoding="utf-8"
        ))

    # --- Counts ---
    def test_01_memory_line_count_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715, f"Expected 1715 lines, got {count}")

    def test_02_faiss_ids_count_1611(self):
        count = len(json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8")))
        self.assertEqual(count, 1611, f"Expected 1611 FAISS ids, got {count}")

    def test_03_batch_has_exactly_5_records(self):
        self.assertEqual(len(self.canary_records), 5)

    def test_04_all_source_ids_present(self):
        expected = {"nist_csf", "nist_ai_rmf", "opa_docs", "mitre_atlas", "gvisor_docs"}
        found = {r["source_id"] for r in self.canary_records}
        self.assertEqual(found, expected)

    def test_05_all_memory_ids_present(self):
        expected = {
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        }
        found = {r["memory_id"] for r in self.canary_records}
        self.assertEqual(found, expected)

    def test_06_all_memory_ids_globally_unique(self):
        all_ids = []
        with open(REPO / "memory/semantic/semantic_memory.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    mid = record.get("memory_id", "")
                    if mid:
                        all_ids.append(mid)
        
        # Check duplicates
        from collections import Counter
        counts = Counter(all_ids)
        duplicates = [mid for mid, count in counts.items() if count > 1]
        self.assertEqual(len(duplicates), 0, f"Duplicate memory_ids found: {duplicates}")

    def test_07_all_domain_security_governance(self):
        for r in self.canary_records:
            self.assertEqual(r["domain"], "security_governance_sandboxing")

    def test_08_all_ingestion_status_ingested(self):
        for r in self.canary_records:
            self.assertEqual(r["ingestion_status"], "ingested_memory_only")

    def test_09_all_faiss_eligible_false(self):
        for r in self.canary_records:
            self.assertIs(r["faiss_eligible"], False)

    def test_10_all_faiss_embedding_text_empty(self):
        for r in self.canary_records:
            self.assertEqual(r.get("faiss_embedding_text", None), "")

    def test_11_all_approval_phrase_present(self):
        for r in self.canary_records:
            self.assertIn("user_approval_phrase", r)
            self.assertTrue(len(r["user_approval_phrase"]) > 0)

    # --- Direct eval artifacts ---
    def test_12_direct_eval_artifact_exists(self):
        self.assertTrue(self.direct_eval is not None)
        self.assertEqual(self.direct_eval["batch_id"], "SEC_GOV_CANARY_001")

    def test_13_negative_eval_artifact_exists(self):
        self.assertTrue(self.negative_eval is not None)
        self.assertEqual(self.negative_eval["batch_id"], "SEC_GOV_CANARY_001")

    def test_14_all_direct_queries_return_result(self):
        for result in self.direct_eval["per_query_results"]:
            self.assertTrue(result["top_5_hit"], f"Query '{result['query']}' returned no result in top-5")

    def test_15_at_least_6_of_8_queries_top_3(self):
        top_3_hits = sum(1 for r in self.direct_eval["per_query_results"] if r["top_3_hit"])
        self.assertGreaterEqual(top_3_hits, 6, f"Only {top_3_hits}/8 queries had top-3 hit")

    def test_16_domain_precision_1(self):
        self.assertEqual(self.direct_eval["domain_precision"], 1.0)

    # --- Negative eval ---
    def test_17_all_negative_queries_safe(self):
        for result in self.negative_eval["per_query_results"]:
            self.assertTrue(result["safe"], f"Negative query '{result['query']}' matched canary records")

    def test_18_no_forbidden_fields(self):
        self.assertEqual(len(self.negative_eval["forbidden_fields_found"]), 0)

    def test_19_no_domain_contamination(self):
        self.assertEqual(len(self.negative_eval["domain_contamination"]), 0)

    def test_20_no_rejected_source(self):
        for r in self.canary_records:
            self.assertNotEqual(r["acceptance_status"], "reject")

    def test_21_no_hold_source(self):
        for r in self.canary_records:
            self.assertNotEqual(r["acceptance_status"], "hold")

    def test_22_no_candidate_source(self):
        for r in self.canary_records:
            self.assertNotEqual(r["acceptance_status"], "candidate")

    def test_23_no_financial_source(self):
        financial = ["financial", "trading", "broker", "portfolio"]
        for r in self.canary_records:
            self.assertFalse(any(f in r["source_id"].lower() for f in financial))

    def test_24_no_coding_source(self):
        coding = ["coding", "patch", "autonomous_code", "code_gen"]
        for r in self.canary_records:
            self.assertFalse(any(c in r["source_id"].lower() for c in coding))

    # --- Metadata ---
    def test_25_source_urls_present(self):
        for r in self.canary_records:
            self.assertTrue(len(r.get("source_url", "").strip()) > 0)

    def test_26_source_license_present(self):
        for r in self.canary_records:
            self.assertTrue(len(r.get("source_license_or_status", "").strip()) > 0)

    def test_27_retrieval_phrases_valid(self):
        for r in self.canary_records:
            phrases = r.get("retrieval_phrases", [])
            self.assertTrue(3 <= len(phrases) <= 8)

    # --- Git safety ---
    def test_28_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_29_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())

    def test_30_no_trading_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("trading/" in line or "B8/" in line, f"Trading/B8 staged: {line}")

    def test_31_no_strategies_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("tmp_agent/strategies" in line, f"Strategies staged: {line}")

    def test_32_no_env_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse(".env" in line, f".env staged: {line}")

    def test_33_no_memory_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("memory/semantic" in line, f"Memory staged: {line}")

    def test_34_no_faiss_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("faiss" in line.lower(), f"FAISS staged: {line}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
