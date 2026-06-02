"""B7-STRANGLER-04 import-compat: routing constants re-exported from
brain_v9.core.session must be the *same objects* as those defined in
brain_v9.core.session_routing_constants.
"""
from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_TMP_AGENT = os.path.join(_REPO_ROOT, "tmp_agent")
if _TMP_AGENT not in sys.path:
    sys.path.insert(0, _TMP_AGENT)


class TestB7RoutingConstantsImportCompat(unittest.TestCase):
    def test_identity_across_session_and_routing_constants(self):
        from brain_v9.core import session as session_mod
        from brain_v9.core import session_routing_constants as rc

        names = [
            "AGENT_INTENTS",
            "AGENT_KEYWORDS",
            "_AGENT_PATTERNS",
            "_CODE_ANALYSIS_PATH_RE",
            "_LEAK_TAIL_RE",
            "_CONTINUE_WORDS_RE",
            "_CORRECTION_RE",
        ]
        for name in names:
            self.assertTrue(
                hasattr(session_mod, name),
                f"session module missing re-exported name: {name}",
            )
            self.assertTrue(
                hasattr(rc, name),
                f"session_routing_constants missing name: {name}",
            )
            self.assertIs(
                getattr(session_mod, name),
                getattr(rc, name),
                f"{name} is not the same object across modules",
            )

    def test_direct_import_from_session_works(self):
        # Existing external callers do this; must keep working.
        from brain_v9.core.session import (  # noqa: F401
            AGENT_INTENTS,
            AGENT_KEYWORDS,
            _AGENT_PATTERNS,
            _CODE_ANALYSIS_PATH_RE,
            _LEAK_TAIL_RE,
            _CONTINUE_WORDS_RE,
            _CORRECTION_RE,
        )
        self.assertIsInstance(AGENT_INTENTS, set)
        self.assertIsInstance(AGENT_KEYWORDS, list)
        self.assertGreater(len(AGENT_KEYWORDS), 50)
        self.assertEqual(len(_AGENT_PATTERNS), len(AGENT_KEYWORDS))

    def test_direct_import_from_routing_constants_works(self):
        from brain_v9.core.session_routing_constants import (  # noqa: F401
            AGENT_INTENTS,
            AGENT_KEYWORDS,
            _AGENT_PATTERNS,
            _CODE_ANALYSIS_PATH_RE,
            _LEAK_TAIL_RE,
            _CONTINUE_WORDS_RE,
            _CORRECTION_RE,
        )
        self.assertEqual(AGENT_INTENTS, {"SYSTEM", "CODE", "COMMAND", "TRADING"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
