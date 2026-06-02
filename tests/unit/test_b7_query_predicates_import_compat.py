"""B7-STRANGLER-03 import-compat tests for session_query_predicates.

Validate that:
- `brain_v9.core.session_query_predicates` exports the 31 expected predicate
  functions.
- `BrainSession` still exposes the 31 underscore-prefixed predicate methods.
- The shim methods on BrainSession are equivalent to the module-level
  functions for representative inputs (parity check).

These tests do NOT spin up the BrainSession heavy ``__init__`` (no LLMs, no
network, no QC, no IBKR). They only inspect class symbols and call predicates
via ``BrainSession.__new__(BrainSession)`` (skipping ``__init__``).
"""
from __future__ import annotations

import os
import sys
import unittest

# Allow imports from C:/AI_VAULT/tmp_agent
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_TMP_AGENT = os.path.join(_REPO_ROOT, "tmp_agent")
if _TMP_AGENT not in sys.path:
    sys.path.insert(0, _TMP_AGENT)

from brain_v9.core import session_query_predicates as qp  # noqa: E402
from brain_v9.core.session import BrainSession  # noqa: E402


PREDICATE_PAIRS = [
    ("_looks_like_canned_failure", "looks_like_canned_failure"),
    ("_is_benign_security_audit_query", "is_benign_security_audit_query"),
    ("_is_confirmation", "is_confirmation"),
    ("_is_code_change_request", "is_code_change_request"),
    ("_is_tool_confirmation_request_response", "is_tool_confirmation_request_response"),
    ("_is_dashboard_query", "is_dashboard_query"),
    ("_is_greeting_query", "is_greeting_query"),
    ("_is_capabilities_query", "is_capabilities_query"),
    ("_is_llm_status_query", "is_llm_status_query"),
    ("_is_codex_role_query", "is_codex_role_query"),
    ("_is_codex_comparison_query", "is_codex_comparison_query"),
    ("_is_recent_activity_query", "is_recent_activity_query"),
    ("_is_chat_interaction_review_query", "is_chat_interaction_review_query"),
    ("_is_brain_diagnostic_analysis_query", "is_brain_diagnostic_analysis_query"),
    ("_is_grounded_code_analysis_query", "is_grounded_code_analysis_query"),
    ("_is_chat_ui_background_change_query", "is_chat_ui_background_change_query"),
    ("_is_chat_ui_background_restore_query", "is_chat_ui_background_restore_query"),
    ("_is_chat_send_button_move_query", "is_chat_send_button_move_query"),
    ("_is_brain_status_query", "is_brain_status_query"),
    ("_is_deep_brain_analysis_query", "is_deep_brain_analysis_query"),
    ("_looks_like_deep_analysis", "looks_like_deep_analysis"),
    ("_is_deep_risk_analysis_query", "is_deep_risk_analysis_query"),
    ("_is_deep_edge_analysis_query", "is_deep_edge_analysis_query"),
    ("_is_deep_strategy_analysis_query", "is_deep_strategy_analysis_query"),
    ("_is_deep_pipeline_analysis_query", "is_deep_pipeline_analysis_query"),
    ("_is_self_build_query", "is_self_build_query"),
    ("_is_self_build_resolution_query", "is_self_build_resolution_query"),
    ("_is_consciousness_query", "is_consciousness_query"),
    ("_is_abstract_reasoning_query", "is_abstract_reasoning_query"),
    ("_is_operational_agent_query", "is_operational_agent_query"),
    ("_is_temporal_query", "is_temporal_query"),
]


class TestB7QueryPredicatesImportCompat(unittest.TestCase):
    def test_module_exports_all_31_callables(self):
        self.assertEqual(len(PREDICATE_PAIRS), 31)
        self.assertEqual(set(qp.__all__), {nn for _, nn in PREDICATE_PAIRS})
        for _, new_name in PREDICATE_PAIRS:
            fn = getattr(qp, new_name)
            self.assertTrue(callable(fn), f"qp.{new_name} not callable")

    def test_brain_session_keeps_all_31_shims(self):
        for old_name, _ in PREDICATE_PAIRS:
            self.assertTrue(
                hasattr(BrainSession, old_name),
                f"BrainSession missing shim {old_name}",
            )
            attr = getattr(BrainSession, old_name)
            self.assertTrue(callable(attr), f"BrainSession.{old_name} not callable")

    def test_shim_parity_with_module_functions(self):
        # Build a BrainSession without running heavy __init__.
        s = BrainSession.__new__(BrainSession)
        samples = [
            "",
            "hola",
            "si",
            "ok",
            "dale",
            "yes",
            "no estoy seguro",
            "modifica session.py",
            "abre el dashboard",
            "explica el dashboard",
            "que llm estas usando",
            "que has hecho ultimamente",
            "hoy",
            "ayer",
            "analiza tmp_agent/foo.py revisa",
            "analiza profundamente el riesgo",
            "analiza profundamente el edge",
            "analiza profundamente la estrategia",
            "analiza profundamente el pipeline",
            "autoconstruccion",
            "automejora detenida resuelvelo",
            "consciousness",
            "si todos los humanos son mortales puedes concluir",
            "estado del brain",
            "que carril principal usa codex",
            "compara codex con code tecnicamente",
            "interacciones que estan fallando revisa",
            "diagnostica el brain por que falla el routing",
            "modifica el color de fondo del chat",
            "vuelve al fondo oscuro original",
            "mueve el boton de enviar a la izquierda",
            "el agente no ejecuto ninguna herramienta",
            "estado del sistema",
            "confirma si quieres que ejecute herramientas en el endpoint de agente",
            "seguridad benigna del brain sin explotar",
        ]
        for sample in samples:
            for old_name, new_name in PREDICATE_PAIRS:
                shim_result = getattr(s, old_name)(sample)
                fn_result = getattr(qp, new_name)(sample)
                self.assertEqual(
                    shim_result,
                    fn_result,
                    f"Parity mismatch on {old_name}({sample!r}): "
                    f"shim={shim_result} fn={fn_result}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
