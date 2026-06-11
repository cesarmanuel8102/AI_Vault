"""
Smoke tests for FRONT-RUNTIME-PATH-ALIGNMENT-CANONICAL-VERIFY-01
"""
import hashlib, json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tmp_agent"))

import faiss


class TestRuntimePathAlignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.post_patch = json.load(open(
            REPO / "tmp_agent/front_runtime_path_alignment_canonical_verify_01/post_patch_path_verify.json",
            encoding="utf-8"
        ))
        cls.immut = json.load(open(
            REPO / "tmp_agent/front_runtime_path_alignment_canonical_verify_01/immutability_verify.json",
            encoding="utf-8"
        ))
        cls.legacy = json.load(open(
            REPO / "tmp_agent/front_runtime_path_alignment_canonical_verify_01/legacy_path_readonly_audit.json",
            encoding="utf-8"
        ))
        cls.scan = json.load(open(
            REPO / "tmp_agent/front_runtime_path_alignment_canonical_verify_01/path_definition_scan.json",
            encoding="utf-8"
        ))

    def test_01_import_config(self):
        import brain_v9.config as cfg
        self.assertTrue(hasattr(cfg, "BASE_PATH"))
        self.assertTrue(hasattr(cfg, "STATE_PATH"))

    def test_02_base_path_endswith_canonical(self):
        self.assertTrue(self.post_patch["checks"]["base_path_endswith_canonical"],
                        f"BASE_PATH does not end with AI_VAULT_CANONICAL: {self.post_patch.get('BASE_PATH')}")

    def test_03_state_path_under_canonical(self):
        bp = self.post_patch["BASE_PATH"]
        sp = self.post_patch["STATE_PATH"]
        self.assertTrue(str(sp).startswith(str(bp)), f"STATE_PATH not under BASE_PATH: {sp}")

    def test_04_faiss_index_path_under_canonical(self):
        ip = self.post_patch["INDEX_PATH"]
        self.assertTrue(str(ip).replace("\\", "/").endswith("AI_VAULT_CANONICAL/memory/semantic/semantic_memory_faiss.index"),
                        f"INDEX_PATH not canonical: {ip}")

    def test_05_faiss_ids_path_under_canonical(self):
        ip = self.post_patch["IDS_PATH"]
        self.assertTrue(str(ip).replace("\\", "/").endswith("AI_VAULT_CANONICAL/memory/semantic/semantic_memory_faiss_ids.json"),
                        f"IDS_PATH not canonical: {ip}")

    def test_06_semantic_memory_lines_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715)

    def test_07_faiss_ids_count_1616(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        self.assertEqual(len(ids), 1616)

    def test_08_faiss_ntotal_1616(self):
        index = faiss.read_index(str(REPO / "memory/semantic/semantic_memory_faiss.index"))
        self.assertEqual(index.ntotal, 1616)

    def test_09_all_5_canary_ids_present(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        for mid in [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]:
            self.assertIn(mid, ids, f"Missing canary id: {mid}")

    def test_10_legacy_audit_exists(self):
        self.assertTrue(self.legacy["legacy_path_exists"], "Legacy audit artifact missing")

    def test_11_path_scan_exists(self):
        self.assertTrue(self.scan.get("BASE_PATH_definition", {}).get("file"), "Path scan artifact missing")

    def test_12_post_patch_verify_exists(self):
        self.assertEqual(self.post_patch["verdict"], "PASS", f"Post-patch verify failed: {self.post_patch}")

    def test_13_immutability_verify_exists(self):
        self.assertEqual(self.immut["verdict"], "PASS", f"Immutability verify failed: {self.immut}")

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
            self.assertFalse("semantic_memory" in line, f"semantic_memory staged: {line}")

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

    def test_20_canary_records_in_memory(self):
        records = {}
        with open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    mid = rec.get("memory_id") or rec.get("id")
                    if mid:
                        records[mid] = rec
        for cid in [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]:
            self.assertIn(cid, records, f"Canary {cid} not in semantic memory")
            self.assertEqual(records[cid].get("domain"), "security_governance_sandboxing",
                             f"Domain mismatch for {cid}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
