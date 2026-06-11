"""
Smoke tests for FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-EXECUTE-SECURITY-GOVERNANCE-01
"""
import hashlib, json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from brain.external_curated_learning_canary_ingestion_prep_security_governance import (
    build_proposed_memory_records,
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


class TestCanaryIngestionExecute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.load(open(REPO / "tmp_agent/front_external_curated_learning_canary_ingestion_execute_security_governance_01/baseline_before_mutation.json", encoding="utf-8"))
        cls.approved_source_ids = ["nist_csf", "nist_ai_rmf", "opa_docs", "mitre_atlas", "gvisor_docs"]
        cls.approved_memory_ids = [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]
        cls.new_records = []
        with open(REPO / "memory/semantic/semantic_memory.jsonl", "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-5:]:
                if line.strip():
                    cls.new_records.append(json.loads(line))

    # --- Counts ---
    def test_01_memory_line_count_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715, f"Expected 1715 lines, got {count}")

    def test_02_faiss_ids_count_1611(self):
        count = len(json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8")))
        self.assertEqual(count, 1611, f"Expected 1611 FAISS ids, got {count}")

    def test_03_faiss_index_sha_unchanged(self):
        current = sha256_file(REPO / "memory/semantic/semantic_memory_faiss.index")
        self.assertEqual(current, self.baseline["semantic_memory_faiss_index_sha"])

    def test_04_faiss_ids_sha_unchanged(self):
        current = sha256_file(REPO / "memory/semantic/semantic_memory_faiss_ids.json")
        self.assertEqual(current, self.baseline["semantic_memory_faiss_ids_json_sha"])

    # --- New records ---
    def test_05_all_approved_memory_ids_exist(self):
        existing_ids = {r["memory_id"] for r in self.new_records}
        for mid in self.approved_memory_ids:
            self.assertIn(mid, existing_ids, f"Missing memory_id: {mid}")

    def test_06_no_duplicate_memory_id(self):
        ids = [r["memory_id"] for r in self.new_records]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate memory_id found")

    def test_07_all_domain_security_governance(self):
        for r in self.new_records:
            self.assertEqual(r["domain"], "security_governance_sandboxing")

    def test_08_all_acceptance_status_accept(self):
        for r in self.new_records:
            self.assertEqual(r["acceptance_status"], "accept")

    def test_09_all_ingestion_status_ingested(self):
        for r in self.new_records:
            self.assertEqual(r["ingestion_status"], "ingested_memory_only")

    def test_10_all_user_approval_phrase_present(self):
        for r in self.new_records:
            self.assertIn("user_approval_phrase", r)
            self.assertTrue(len(r["user_approval_phrase"]) > 0)

    def test_11_all_faiss_eligible_false(self):
        for r in self.new_records:
            self.assertIs(r["faiss_eligible"], False)

    def test_12_all_faiss_embedding_text_empty(self):
        for r in self.new_records:
            self.assertEqual(r.get("faiss_embedding_text", None), "")

    def test_13_all_source_ids_match_approved(self):
        for r in self.new_records:
            self.assertIn(r["source_id"], self.approved_source_ids)

    # --- Safety fields ---
    def test_14_no_rejected_source(self):
        for r in self.new_records:
            self.assertNotEqual(r["acceptance_status"], "reject")

    def test_15_no_hold_source(self):
        for r in self.new_records:
            self.assertNotEqual(r["acceptance_status"], "hold")

    def test_16_no_candidate_source(self):
        for r in self.new_records:
            self.assertNotEqual(r["acceptance_status"], "candidate")

    def test_17_no_financial_source(self):
        financial = ["financial", "trading", "broker", "portfolio"]
        for r in self.new_records:
            self.assertFalse(any(f in r["source_id"].lower() for f in financial))

    def test_18_no_coding_source(self):
        coding = ["coding", "patch", "code"]
        for r in self.new_records:
            self.assertFalse(any(c in r["source_id"].lower() for c in coding))

    def test_19_no_broker_api_field(self):
        for r in self.new_records:
            self.assertNotIn("broker_api", r)

    def test_20_no_trading_signal_field(self):
        for r in self.new_records:
            self.assertNotIn("trading_signal", r)

    def test_21_no_executable_code_field(self):
        for r in self.new_records:
            self.assertNotIn("executable_code", r)

    def test_22_no_chain_of_thought_field(self):
        for r in self.new_records:
            self.assertNotIn("chain_of_thought", r)

    # --- Evidence files ---
    def test_23_backup_manifest_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_ingestion_execute_security_governance_01/backups/SEC_GOV_CANARY_001/backup_manifest.json"
        self.assertTrue(p.exists())

    def test_24_append_manifest_exists(self):
        p = REPO / "tmp_agent/front_external_curated_learning_canary_ingestion_execute_security_governance_01/append_manifest.json"
        self.assertTrue(p.exists())

    # --- Git safety ---
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

    def test_31_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_32_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())
        content = ledger.read_text(encoding="utf-8")
        # Check at least one relevant front entry exists
        self.assertTrue(
            "FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-" in content or
            "FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-EXECUTE" in content or
            "FRONT-EXTERNAL-CURATED-LEARNING-CANARY-INGESTION-PREP" in content,
            "Ledger should contain canary ingestion entries"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
