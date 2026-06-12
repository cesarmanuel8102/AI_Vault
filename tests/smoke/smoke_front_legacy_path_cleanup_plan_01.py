"""
Smoke tests for FRONT-LEGACY-PATH-CLEANUP-PLAN-01
"""
import hashlib, json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tmp_agent"))

import faiss


class TestLegacyPathCleanupPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_plan_01/canonical_baseline.json",
            encoding="utf-8"
        ))
        cls.legacy = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_plan_01/legacy_baseline.json",
            encoding="utf-8"
        ))
        cls.diff = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_plan_01/directory_diff_inventory.json",
            encoding="utf-8"
        ))
        cls.runtime = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_plan_01/runtime_dependency_audit.json",
            encoding="utf-8"
        ))
        cls.risk = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_plan_01/legacy_risk_classification.json",
            encoding="utf-8"
        ))
        cls.plan = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_plan_01/cleanup_plan_package.json",
            encoding="utf-8"
        ))
        cls.immut = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_plan_01/immutability_verify.json",
            encoding="utf-8"
        ))

    def test_01_canonical_semantic_memory_lines_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715)

    def test_02_canonical_faiss_ids_count_1616(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        self.assertEqual(len(ids), 1616)

    def test_03_canonical_faiss_ntotal_1616(self):
        index = faiss.read_index(str(REPO / "memory/semantic/semantic_memory_faiss.index"))
        self.assertEqual(index.ntotal, 1616)

    def test_04_base_path_canonical(self):
        self.assertTrue(self.runtime["runtime_config"]["base_path_canonical"],
                        f"BASE_PATH not canonical: {self.runtime['runtime_config']['imported_BASE_PATH']}")

    def test_05_faiss_paths_canonical(self):
        self.assertTrue(self.canonical["checks"]["index_path_canonical"],
                        f"FAISS index path not canonical: {self.canonical['FAISS_index_path']}")
        self.assertTrue(self.canonical["checks"]["ids_path_canonical"],
                        f"FAISS ids path not canonical: {self.canonical['FAISS_ids_path']}")

    def test_06_legacy_audit_exists(self):
        self.assertTrue(self.legacy["legacy_exists"], "Legacy audit artifact missing")

    def test_07_directory_diff_exists(self):
        self.assertTrue(self.diff["canonical_file_count"] > 0, "Directory diff artifact missing")

    def test_08_runtime_dependency_audit_exists(self):
        self.assertTrue(self.runtime["verdict"] == "PASS", "Runtime dependency audit failed")

    def test_09_risk_classification_exists(self):
        self.assertIn("cleanup_risk_level", self.risk, "Risk classification artifact missing")

    def test_10_cleanup_plan_package_exists(self):
        self.assertTrue(self.plan.get("plan_only", False), "Cleanup plan package not marked plan_only")

    def test_11_plan_only_true(self):
        self.assertTrue(self.plan["plan_only"], "Cleanup plan must be plan_only=true")

    def test_12_no_deletion_authorized(self):
        self.assertFalse(self.plan.get("deletion_authorized", True), "Deletion must not be authorized")

    def test_13_approval_phrase_exact(self):
        self.assertEqual(
            self.plan.get("approval_phrase_required", ""),
            "APPROVE_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT",
            "Approval phrase mismatch"
        )

    def test_14_denial_phrase_exact(self):
        self.assertEqual(
            self.plan.get("denial_phrase", ""),
            "DENY_LEGACY_PATH_CLEANUP_EXECUTE_AI_VAULT",
            "Denial phrase mismatch"
        )

    def test_15_immutability_pass(self):
        self.assertEqual(self.immut["verdict"], "PASS", f"Immutability verify failed: {self.immut}")

    def test_16_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_17_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())

    def test_18_no_memory_semantic_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("semantic_memory" in line, f"semantic_memory staged: {line}")

    def test_19_no_trading_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("trading/" in line or "B8/" in line, f"Trading/B8 staged: {line}")

    def test_20_no_strategies_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("tmp_agent/strategies" in line, f"Strategies staged: {line}")

    def test_21_no_env_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse(".env" in line, f".env staged: {line}")

    def test_22_canary_ids_in_canonical_faiss(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        for mid in [
            "SEC_GOV_CANARY_001_nist_csf_001",
            "SEC_GOV_CANARY_001_nist_ai_rmf_002",
            "SEC_GOV_CANARY_001_opa_docs_003",
            "SEC_GOV_CANARY_001_mitre_atlas_004",
            "SEC_GOV_CANARY_001_gvisor_docs_005",
        ]:
            self.assertIn(mid, ids, f"Missing canary id: {mid}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
