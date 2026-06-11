"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CANARY-POST-INGESTION-VERIFY-SECURITY-GOVERNANCE-01
"""
import json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))


class TestCanaryPostIngestionVerify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.approved_source_ids = ["nist_csf", "nist_ai_rmf", "opa_docs", "mitre_atlas", "gvisor_docs"]
        cls.approved_memory_ids = [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]
        cls.canary_records = []
        with open(REPO / "memory/semantic/semantic_memory.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    if record.get("ingestion_batch_id") == "SEC_GOV_CANARY_001":
                        cls.canary_records.append(record)

    # --- Counts ---
    def test_01_memory_line_count_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715, f"Expected 1715 lines, got {count}")

    def test_02_faiss_ids_count_1611(self):
        count = len(json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8")))
        self.assertEqual(count, 1611, f"Expected 1611 FAISS ids, got {count}")

    # --- Batch records ---
    def test_03_batch_appears_exactly_5_times(self):
        self.assertEqual(len(self.canary_records), 5)

    def test_04_all_expected_source_ids_present(self):
        found = {r["source_id"] for r in self.canary_records}
        for sid in self.approved_source_ids:
            self.assertIn(sid, found, f"Missing source_id: {sid}")

    def test_05_all_expected_memory_ids_unique(self):
        found = [r["memory_id"] for r in self.canary_records]
        self.assertEqual(len(found), len(set(found)), "Duplicate memory_id found")
        for mid in self.approved_memory_ids:
            self.assertIn(mid, found, f"Missing memory_id: {mid}")

    def test_06_all_domain_security_governance(self):
        for r in self.canary_records:
            self.assertEqual(r["domain"], "security_governance_sandboxing")

    def test_07_all_ingestion_status_ingested(self):
        for r in self.canary_records:
            self.assertEqual(r["ingestion_status"], "ingested_memory_only")

    def test_08_all_faiss_eligible_false(self):
        for r in self.canary_records:
            self.assertIs(r["faiss_eligible"], False)

    def test_09_all_faiss_embedding_text_empty(self):
        for r in self.canary_records:
            self.assertEqual(r.get("faiss_embedding_text", None), "")

    def test_10_all_approval_phrase_present(self):
        for r in self.canary_records:
            self.assertIn("user_approval_phrase", r)
            self.assertTrue(len(r["user_approval_phrase"]) > 0)

    # --- Safety / contamination ---
    def test_11_no_rejected_source(self):
        for r in self.canary_records:
            self.assertNotEqual(r["acceptance_status"], "reject")

    def test_12_no_hold_source(self):
        for r in self.canary_records:
            self.assertNotEqual(r["acceptance_status"], "hold")

    def test_13_no_candidate_source(self):
        for r in self.canary_records:
            self.assertNotEqual(r["acceptance_status"], "candidate")

    def test_14_no_financial_source(self):
        financial = ["financial", "trading", "broker", "portfolio"]
        for r in self.canary_records:
            self.assertFalse(any(f in r["source_id"].lower() for f in financial))

    def test_15_no_coding_source(self):
        coding = ["coding", "patch", "autonomous_code", "code_gen"]
        for r in self.canary_records:
            self.assertFalse(any(c in r["source_id"].lower() for c in coding))

    def test_16_no_broker_api_field(self):
        for r in self.canary_records:
            self.assertNotIn("broker_api", r)

    def test_17_no_trading_signal_field(self):
        for r in self.canary_records:
            self.assertNotIn("trading_signal", r)

    def test_18_no_executable_code_field(self):
        for r in self.canary_records:
            self.assertNotIn("executable_code", r)

    def test_19_no_chain_of_thought_field(self):
        for r in self.canary_records:
            self.assertNotIn("chain_of_thought", r)

    # --- Metadata ---
    def test_20_source_urls_present(self):
        for r in self.canary_records:
            self.assertTrue(len(r.get("source_url", "").strip()) > 0)

    def test_21_source_license_present(self):
        for r in self.canary_records:
            self.assertTrue(len(r.get("source_license_or_status", "").strip()) > 0)

    def test_22_retrieval_phrases_valid(self):
        for r in self.canary_records:
            phrases = r.get("retrieval_phrases", [])
            self.assertTrue(3 <= len(phrases) <= 8)

    # --- Git safety ---
    def test_23_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_24_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())
        content = ledger.read_text(encoding="utf-8")
        self.assertIn("FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-EXECUTE", content)

    def test_25_no_trading_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("trading/" in line or "B8/" in line, f"Trading/B8 staged: {line}")

    def test_26_no_strategies_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("tmp_agent/strategies" in line, f"Strategies staged: {line}")

    def test_27_no_env_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse(".env" in line, f".env staged: {line}")

    def test_28_no_main_py_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("brain_v9/main.py" in line, f"main.py staged: {line}")

    def test_29_no_session_py_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("brain_v9/core/session.py" in line, f"session.py staged: {line}")

    def test_30_no_llm_py_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("brain_v9/core/llm.py" in line, f"llm.py staged: {line}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
