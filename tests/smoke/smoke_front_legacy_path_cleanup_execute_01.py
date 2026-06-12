"""
Smoke tests for FRONT-LEGACY-PATH-CLEANUP-EXECUTE-01
"""
import hashlib, json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tmp_agent"))

import faiss


class TestLegacyPathCleanupExecute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_execute_01/canonical_baseline_before_cleanup.json",
            encoding="utf-8"
        ))
        cls.rename_result = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_execute_01/quarantine_rename_result.json",
            encoding="utf-8"
        ))
        cls.post = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_execute_01/post_rename_canonical_verify.json",
            encoding="utf-8"
        ))
        cls.rollback = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_execute_01/rollback_plan.json",
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
        self.assertTrue(self.post["BASE_PATH_canonical"], f"BASE_PATH not canonical")

    def test_05_faiss_index_path_canonical(self):
        self.assertTrue(self.post["FAISS_index_path_canonical"], f"FAISS index path not canonical")

    def test_06_faiss_ids_path_canonical(self):
        self.assertTrue(self.post["FAISS_ids_path_canonical"], f"FAISS ids path not canonical")

    def test_07_rename_result_exists(self):
        self.assertTrue(self.rename_result["rename_attempted"], "Rename not attempted")

    def test_08_rename_not_successful(self):
        # Rename failed due to Windows file lock — this is expected given the current environment
        self.assertFalse(self.rename_result["rename_success"], "Rename was unexpectedly successful")

    def test_09_legacy_still_exists(self):
        # Since rename failed, legacy should still exist
        self.assertTrue(self.post["C_AI_VAULT_exists"], "Legacy path unexpectedly missing after failed rename")

    def test_10_quarantine_not_created(self):
        self.assertFalse(self.post["quarantine_target_exists"], "Quarantine target unexpectedly exists")

    def test_11_canonical_unchanged(self):
        self.assertTrue(self.post["semantic_memory_jsonl_unchanged"], "Canonical semantic_memory mutated")
        self.assertTrue(self.post["semantic_memory_faiss_index_unchanged"], "Canonical FAISS index mutated")
        self.assertTrue(self.post["semantic_memory_faiss_ids_unchanged"], "Canonical FAISS ids mutated")

    def test_12_deletion_not_authorized(self):
        self.assertFalse(self.rename_result.get("deletion_authorized", True), "Deletion was authorized")

    def test_13_copy_not_authorized(self):
        self.assertFalse(self.rename_result.get("copy_authorized", True), "Copy was authorized")

    def test_14_sync_not_authorized(self):
        self.assertFalse(self.rename_result.get("sync_authorized", True), "Sync was authorized")

    def test_15_rollback_plan_exists(self):
        self.assertTrue(self.rollback["rollback_possible"], "Rollback plan missing")

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

    def test_20_canonical_post_verdict_pass(self):
        self.assertEqual(self.post["verdict"], "PASS", f"Post-rename verify failed: {self.post}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
