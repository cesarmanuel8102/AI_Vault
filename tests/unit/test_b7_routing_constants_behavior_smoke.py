"""B7-STRANGLER-04 behavior smoke: pin regex semantics for the 7 extracted
constants so any future edit that breaks behavior is caught here."""
from __future__ import annotations

import os
import re
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_TMP_AGENT = os.path.join(_REPO_ROOT, "tmp_agent")
if _TMP_AGENT not in sys.path:
    sys.path.insert(0, _TMP_AGENT)


class TestB7RoutingConstantsBehaviorSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from brain_v9.core import session_routing_constants as rc
        cls.rc = rc

    def test_agent_intents_canonical_set(self):
        self.assertEqual(self.rc.AGENT_INTENTS, {"SYSTEM", "CODE", "COMMAND", "TRADING"})

    def test_agent_patterns_length_matches_keywords(self):
        self.assertEqual(len(self.rc._AGENT_PATTERNS), len(self.rc.AGENT_KEYWORDS))
        for p in self.rc._AGENT_PATTERNS:
            self.assertIsInstance(p, re.Pattern)
            self.assertTrue(p.flags & re.IGNORECASE)

    def test_agent_keywords_match_representative_phrases(self):
        # If ANY pattern matches, classification considers it tool-worthy.
        positives = [
            "revisa el archivo brain.log",
            "verify the dashboard tab",
            "list files in tmp_agent",
            "scan red local 192.168.1.0/24",
            "ejecutar backtest en quantconnect",
            "muestra el estado del proceso",
            "freeze strategy mean_reversion",
            "show me the orders for paper account",
        ]
        for text in positives:
            self.assertTrue(
                any(p.search(text) for p in self.rc._AGENT_PATTERNS),
                f"Expected at least one AGENT_KEYWORDS match for: {text!r}",
            )

    def test_agent_keywords_do_not_match_pure_chitchat(self):
        # Pure greetings/chit-chat must NOT match any agent keyword.
        negatives = ["hola", "gracias", "ok"]
        for text in negatives:
            self.assertFalse(
                any(p.search(text) for p in self.rc._AGENT_PATTERNS),
                f"Did NOT expect any AGENT_KEYWORDS match for chitchat: {text!r}",
            )

    def test_code_analysis_path_re_matches_windows_and_unix_paths(self):
        rgx = self.rc._CODE_ANALYSIS_PATH_RE
        self.assertIsNotNone(rgx.search(r"please look at C:\AI_VAULT\tmp_agent\brain_v9\core\session.py"))
        self.assertIsNotNone(rgx.search("see tmp_agent/brain_v9/core/session.py for details"))
        self.assertIsNone(rgx.search("just a casual sentence with no path"))

    def test_leak_tail_re_detects_cot_leak(self):
        rgx = self.rc._LEAK_TAIL_RE
        self.assertIsNotNone(rgx.search("revisando el archivo de configuración..."))
        self.assertIsNotNone(rgx.search("analizando los datos del usuario...."))
        self.assertIsNone(rgx.search("Aquí está el resultado final."))

    def test_continue_words_re_detects_short_continue(self):
        rgx = self.rc._CONTINUE_WORDS_RE
        for text in ["continua", "continúa", "sigue", "go on", "keep going", "expand"]:
            self.assertIsNotNone(rgx.match(text), f"expected continue-match for {text!r}")
        for text in ["dame un reporte completo", "ejecuta esto"]:
            self.assertIsNone(rgx.match(text), f"did NOT expect continue-match for {text!r}")

    def test_correction_re_detects_user_corrections(self):
        rgx = self.rc._CORRECTION_RE
        positives = [
            "no, te equivocaste con el nombre",
            "estas mal, el correcto es otro",
            "eso es incorrecto",
            "esa tool no existe",
            "lo correcto es usar tool01",
        ]
        for text in positives:
            self.assertIsNotNone(rgx.search(text), f"expected correction-match for {text!r}")
        negatives = ["gracias por la respuesta", "perfecto, sigamos"]
        for text in negatives:
            self.assertIsNone(rgx.search(text), f"did NOT expect correction-match for {text!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
