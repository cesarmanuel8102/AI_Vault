"""
Smoke tests for FRONT-LEGACY-PATH-CLEANUP-RETRY-POST-REBOOT-01
"""
import hashlib, json, os, subprocess, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tmp_agent"))

import faiss


class TestLegacyPathCleanupRetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_retry_post_reboot_01/canonical_baseline_before_retry.json",
            encoding="utf-8"
        ))
        cls.rename_result = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_retry_post_reboot_01/quarantine_rename_result.json",
            encoding="utf-8"
        ))
        cls.post = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_retry_post_reboot_01/post_rename_canonical_verify.json",
            encoding="utf-8"
        ))
        cls.rollback = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_retry_post_reboot_01/rollback_plan.json",
            encoding="utf-8"
        ))
        cls.legacy = json.load(open(
            REPO / "tmp_agent/front_legacy_path_cleanup_retry_post_reboot_01/legacy_current_state.json",
            encoding="utf-8"
        ))

    def test_01_canonical_path_exists(self):
        self.assertTrue(self.post["C_AI_VAULT_CANONICAL_exists"], "Canonical path does not exist")

    def test_02_canonical_semantic_memory_lines_1715(self):
        count = sum(1 for _ in open(REPO / "memory/semantic/semantic_memory.jsonl", encoding="utf-8"))
        self.assertEqual(count, 1715)

    def test_03_canonical_faiss_ids_count_1616(self):
        ids = json.load(open(REPO / "memory/semantic/semantic_memory_faiss_ids.json", encoding="utf-8"))
        self.assertEqual(len(ids), 1616)

    def test_04_canonical_faiss_ntotal_1616(self):
        index = faiss.read_index(str(REPO / "memory/semantic/semantic_memory_faiss.index"))
        self.assertEqual(index.ntotal, 1616)

    def test_05_base_path_canonical(self):
        self.assertTrue(self.post["BASE_PATH_canonical"], f"BASE_PATH not canonical")

    def test_06_faiss_index_path_canonical(self):
        self.assertTrue(self.post["FAISS_index_path_canonical"], f"FAISS index path not canonical")

    def test_07_faiss_ids_path_canonical(self):
        self.assertTrue(self.post["FAISS_ids_path_canonical"], f"FAISS ids path not canonical")

    def test_08_legacy_current_state_exists(self):
        self.assertTrue(self.legacy["legacy_exists"], "Legacy current state artifact missing")

    def test_09_rename_result_exists(self):
        self.assertTrue(self.rename_result["rename_attempted"], "Rename not attempted")

    def test_10_deletion_not_performed(self):
        self.assertFalse(self.rename_result.get("deletion_performed", True), "Deletion was performed")

    def test_11_copy_not_performed(self):
        self.assertFalse(self.rename_result.get("copy_performed", True), "Copy was performed")

    def test_12_sync_not_performed(self):
        self.assertFalse(self.rename_result.get("sync_performed", True), "Sync was performed")

    def test_13_rollback_plan_exists(self):
        self.assertTrue(self.rollback["rollback_possible"] is not None, "Rollback plan missing")

    def test_14_canonical_unchanged(self):
        self.assertTrue(self.post["semantic_memory_jsonl_unchanged"], "Canonical semantic_memory mutated")
        self.assertTrue(self.post["semantic_memory_faiss_index_unchanged"], "Canonical FAISS index mutated")
        self.assertTrue(self.post["semantic_memory_faiss_ids_unchanged"], "Canonical FAISS ids mutated")

    def test_15_roadmap_valid(self):
        data = json.load(open(REPO / "ROADMAP_STATUS.json", encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_16_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())

    def test_17_no_memory_semantic_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("semantic_memory" in line, f"semantic_memory staged: {line}")

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

    def test_21_canonical_post_verdict_pass(self):
        self.assertEqual(self.post["verdict"], "PASS", f"Post-rename verify failed: {self.post}")

    def test_22_legacy_still_exists(self):
        # Since rename failed, legacy should still exist
        self.assertTrue(self.post["C_AI_VAULT_exists"], "Legacy path unexpectedly missing after failed rename")


if __name__ == "__main__":
    unittest.main(verbosity=2)
