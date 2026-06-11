"""
Smoke tests for FRONT-CHAT-UI-LIVE-RUNTIME-SOURCE-RECOVERY-AND-CURATED-WIRING-01
"""
import json, os, hashlib, subprocess, sys, unittest, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

class TestLiveRuntimeRecoveryAndCuratedWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chat_results = json.load(open(REPO / "tmp_agent/front_chat_ui_live_runtime_source_recovery_and_curated_wiring_01/live_q01_q05_probe_results.json", encoding="utf-8"))
        cls.main_py = REPO / "tmp_agent/brain_v9/main.py"

    def test_01_chat_ui_server_source_exists(self):
        # The actual runtime source is tmp_agent/brain_v9/main.py (brain_v9.main:app)
        self.assertTrue(self.main_py.exists(), "Runtime source main.py must exist")

    def test_02_imports_fastapi(self):
        src = self.main_py.read_text(encoding="utf-8", errors="replace")
        self.assertIn("from fastapi import", src)

    def test_03_imports_answer_chat_probe(self):
        src = self.main_py.read_text(encoding="utf-8", errors="replace")
        self.assertIn("from brain.curated_learning_chat_access import answer_chat_probe", src)

    def test_04_defines_looks_like_curated_learning_probe(self):
        src = self.main_py.read_text(encoding="utf-8", errors="replace")
        self.assertIn("def _looks_like_curated_learning_probe(message: str) -> bool", src)

    def test_05_defines_format_curated_probe_response(self):
        src = self.main_py.read_text(encoding="utf-8", errors="replace")
        self.assertIn("def _format_curated_probe_response(result: dict) -> str", src)

    def test_06_helper_q01_direct(self):
        r = self.chat_results["Q01"]
        self.assertEqual(r.get("model_used"), "curated_helper")
        self.assertTrue(r.get("success"))

    def test_07_helper_q02_direct(self):
        r = self.chat_results["Q02"]
        self.assertEqual(r.get("model_used"), "curated_helper")
        self.assertTrue(r.get("success"))

    def test_08_helper_q03_direct(self):
        r = self.chat_results["Q03"]
        self.assertEqual(r.get("model_used"), "curated_helper")
        self.assertTrue(r.get("success"))

    def test_09_helper_q04_direct(self):
        r = self.chat_results["Q04"]
        self.assertEqual(r.get("model_used"), "curated_helper")
        self.assertTrue(r.get("success"))

    def test_10_helper_q05_direct(self):
        r = self.chat_results["Q05"]
        self.assertEqual(r.get("model_used"), "curated_helper")
        self.assertTrue(r.get("success"))

    def test_11_q01_includes_canonical_counts(self):
        r = self.chat_results["Q01"]["response"]
        self.assertIn("152", r)
        self.assertIn("142", r)
        self.assertIn("4", r)
        self.assertIn("6", r)

    def test_12_q04_includes_security_governance(self):
        r = self.chat_results["Q04"]["response"].lower()
        self.assertTrue("security" in r)

    def test_13_q05_deny(self):
        r = self.chat_results["Q05"]["response"].lower()
        self.assertTrue("deny" in r or "denegado" in r or "rechazada" in r)

    def test_14_no_memory_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("memory/semantic" in line, f"Memory file staged: {line}")

    def test_15_no_faiss_index_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("faiss.index" in line, f"FAISS index staged: {line}")

    def test_16_no_faiss_ids_staged(self):
        staged = subprocess.check_output(["git", "-C", str(REPO), "diff", "--cached", "--name-status"], text=True)
        for line in staged.splitlines():
            self.assertFalse("faiss_ids.json" in line, f"FAISS ids staged: {line}")

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

    def test_20_roadmap_valid_json(self):
        roadmap = REPO / "ROADMAP_STATUS.json"
        data = json.load(open(roadmap, encoding="utf-8"))
        self.assertIn("current_head", data)
        self.assertIn("branch", data)

    def test_21_ledger_exists(self):
        ledger = REPO / "docs/MIGRATION_CONTROL_LEDGER.md"
        self.assertTrue(ledger.exists())
        content = ledger.read_text(encoding="utf-8")
        self.assertIn("FRONT-CHAT-UI-LIVE-RUNTIME-SOURCE-RECOVERY-AND-CURATED-WIRING-01", content)

if __name__ == "__main__":
    unittest.main(verbosity=2)
