"""B7-STRANGLER-03 behavior smoke tests for session_query_predicates.

Each predicate is checked with at least one positive and one negative case to
guard against accidental semantic regressions during the strangler extraction.

These tests deliberately exercise BOTH the standalone functions in
``brain_v9.core.session_query_predicates`` and the shim methods on
``BrainSession`` (constructed via ``__new__`` to avoid heavy init).
"""
from __future__ import annotations

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_TMP_AGENT = os.path.join(_REPO_ROOT, "tmp_agent")
if _TMP_AGENT not in sys.path:
    sys.path.insert(0, _TMP_AGENT)

from brain_v9.core import session_query_predicates as qp  # noqa: E402
from brain_v9.core.session import BrainSession  # noqa: E402


class TestB7QueryPredicatesBehaviorSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = BrainSession.__new__(BrainSession)

    # ---- core fastpath predicates ----------------------------------------

    def test_is_confirmation(self):
        for pos in ("si", "sí", "ok", "dale", "yes", "go ahead", "proceed"):
            self.assertTrue(qp.is_confirmation(pos), pos)
            self.assertTrue(self.session._is_confirmation(pos), pos)
        for neg in (
            "",
            "explica el sistema en detalle por favor",  # too long / not a confirm
            "no",
            "podrias explicar mejor",
        ):
            self.assertFalse(qp.is_confirmation(neg), neg)
            self.assertFalse(self.session._is_confirmation(neg), neg)

    def test_is_tool_confirmation_request_response(self):
        pos = "confirma si quieres que ejecute las herramientas en el endpoint de agente"
        self.assertTrue(qp.is_tool_confirmation_request_response(pos))
        self.assertTrue(self.session._is_tool_confirmation_request_response(pos))
        for neg in ("hola", "el sistema esta operativo"):
            self.assertFalse(qp.is_tool_confirmation_request_response(neg))

    def test_is_dashboard_query(self):
        self.assertTrue(qp.is_dashboard_query("abre el dashboard"))
        self.assertFalse(qp.is_dashboard_query("explica el contenido del dashboard"))
        self.assertFalse(qp.is_dashboard_query("hola"))

    def test_is_greeting_query(self):
        for pos in ("hola", "hello", "hi", "buenas", "buenos dias"):
            self.assertTrue(qp.is_greeting_query(pos))
        for neg in ("explica el brain", "modifica el archivo"):
            self.assertFalse(qp.is_greeting_query(neg))

    def test_is_capabilities_query(self):
        self.assertTrue(qp.is_capabilities_query("que puedes hacer"))
        self.assertTrue(qp.is_capabilities_query("what can you do"))
        self.assertFalse(qp.is_capabilities_query("explica el routing"))

    def test_is_llm_status_query(self):
        self.assertTrue(qp.is_llm_status_query("que modelo estas usando"))
        self.assertFalse(qp.is_llm_status_query("hola"))
        self.assertFalse(qp.is_llm_status_query("modelo de negocio"))

    def test_is_brain_status_query(self):
        self.assertTrue(qp.is_brain_status_query("estado del brain"))
        self.assertTrue(qp.is_brain_status_query("brain status ahora"))
        self.assertFalse(qp.is_brain_status_query("dame el clima"))

    # ---- deep analysis predicates ----------------------------------------

    def test_looks_like_deep_analysis(self):
        self.assertTrue(qp.looks_like_deep_analysis("analiza profundamente el sistema"))
        self.assertFalse(qp.looks_like_deep_analysis("hola"))

    def test_is_deep_brain_analysis_query(self):
        self.assertTrue(qp.is_deep_brain_analysis_query("analiza profundamente el brain"))
        self.assertFalse(qp.is_deep_brain_analysis_query("hola"))
        # missing scope marker -> False
        self.assertFalse(qp.is_deep_brain_analysis_query("analiza profundamente el cafe"))

    def test_is_deep_risk_edge_strategy_pipeline(self):
        self.assertTrue(qp.is_deep_risk_analysis_query("analiza profundamente el riesgo"))
        self.assertTrue(qp.is_deep_edge_analysis_query("analiza profundamente el edge"))
        self.assertTrue(qp.is_deep_strategy_analysis_query("analiza profundamente la estrategia"))
        self.assertTrue(qp.is_deep_pipeline_analysis_query("analiza profundamente el pipeline"))
        self.assertFalse(qp.is_deep_risk_analysis_query("hola"))
        self.assertFalse(qp.is_deep_edge_analysis_query("hola"))
        self.assertFalse(qp.is_deep_strategy_analysis_query("hola"))
        self.assertFalse(qp.is_deep_pipeline_analysis_query("hola"))

    # ---- self-build / consciousness --------------------------------------

    def test_is_self_build_query(self):
        self.assertTrue(qp.is_self_build_query("autoconstruccion"))
        self.assertTrue(qp.is_self_build_query("self improvement"))
        self.assertFalse(qp.is_self_build_query("hola"))

    def test_is_self_build_resolution_query(self):
        self.assertTrue(
            qp.is_self_build_resolution_query("autoconstruccion detenida resuelvelo")
        )
        self.assertTrue(
            qp.is_self_build_resolution_query("automejora bloqueada como lo resuelvo")
        )
        self.assertFalse(qp.is_self_build_resolution_query("autoconstruccion"))
        self.assertFalse(qp.is_self_build_resolution_query("hola"))

    def test_is_consciousness_query(self):
        self.assertTrue(qp.is_consciousness_query("eres autoconsciente"))
        self.assertTrue(qp.is_consciousness_query("self-aware mode"))
        self.assertFalse(qp.is_consciousness_query("hola"))

    # ---- code change / temporal / grounded -------------------------------

    def test_is_code_change_request(self):
        self.assertTrue(qp.is_code_change_request("modifica session.py"))
        self.assertTrue(qp.is_code_change_request("crea un archivo .py"))
        self.assertFalse(qp.is_code_change_request("hola"))
        # action without scope keyword -> False
        self.assertFalse(qp.is_code_change_request("modifica algo"))

    def test_is_temporal_query(self):
        self.assertTrue(qp.is_temporal_query("hoy"))
        self.assertTrue(qp.is_temporal_query("cambios recientes"))
        self.assertTrue(qp.is_temporal_query("ultima actividad"))
        self.assertFalse(qp.is_temporal_query("hola mundo"))

    def test_is_grounded_code_analysis_query(self):
        self.assertTrue(
            qp.is_grounded_code_analysis_query("analiza tmp_agent/brain_v9/core/session.py revisa")
        )
        # path present but no analysis verb -> False
        self.assertFalse(
            qp.is_grounded_code_analysis_query("borra tmp_agent/strategies/foo.py")
        )
        # no path -> False
        self.assertFalse(qp.is_grounded_code_analysis_query("analiza el sistema"))

    # ---- benign security / chat review -----------------------------------

    def test_is_benign_security_audit_query(self):
        self.assertTrue(
            qp.is_benign_security_audit_query("auditoria de seguridad del brain sin explotar")
        )
        # harmful marker present -> False
        self.assertFalse(
            qp.is_benign_security_audit_query("auditoria de seguridad del brain hackear bypass")
        )
        self.assertFalse(qp.is_benign_security_audit_query("hola"))

    def test_is_chat_interaction_review_query(self):
        self.assertTrue(
            qp.is_chat_interaction_review_query("revisa las interacciones que estan fallando")
        )
        self.assertFalse(qp.is_chat_interaction_review_query("hola"))

    def test_is_brain_diagnostic_analysis_query(self):
        self.assertTrue(
            qp.is_brain_diagnostic_analysis_query("explica por que falla el routing del brain")
        )
        self.assertFalse(qp.is_brain_diagnostic_analysis_query("hola"))

    # ---- recent activity / chat UI tweaks --------------------------------

    def test_is_recent_activity_query(self):
        self.assertTrue(qp.is_recent_activity_query("que has hecho ultimamente"))
        self.assertTrue(qp.is_recent_activity_query("tu actividad reciente"))
        self.assertFalse(qp.is_recent_activity_query("hola"))

    def test_is_chat_ui_background_change_query(self):
        self.assertTrue(
            qp.is_chat_ui_background_change_query("modifica el color de fondo del chat")
        )
        self.assertFalse(qp.is_chat_ui_background_change_query("hola"))

    def test_is_chat_ui_background_restore_query(self):
        self.assertTrue(
            qp.is_chat_ui_background_restore_query("vuelve al fondo oscuro original")
        )
        self.assertFalse(qp.is_chat_ui_background_restore_query("hola"))

    def test_is_chat_send_button_move_query(self):
        self.assertTrue(
            qp.is_chat_send_button_move_query("mueve el boton de enviar a la izquierda")
        )
        self.assertFalse(qp.is_chat_send_button_move_query("hola"))

    # ---- codex / abstract / operational ----------------------------------

    def test_is_codex_role_query(self):
        self.assertTrue(qp.is_codex_role_query("que carril principal usa codex"))
        # comparison verb disqualifies role-only intent
        self.assertFalse(qp.is_codex_role_query("compara codex tecnicamente"))
        self.assertFalse(qp.is_codex_role_query("hola"))

    def test_is_codex_comparison_query(self):
        self.assertTrue(qp.is_codex_comparison_query("compara codex con code tecnicamente"))
        self.assertFalse(qp.is_codex_comparison_query("hola"))

    def test_is_abstract_reasoning_query(self):
        self.assertTrue(
            qp.is_abstract_reasoning_query("si todos los humanos son mortales puedes concluir")
        )
        self.assertFalse(qp.is_abstract_reasoning_query("hola"))

    def test_is_operational_agent_query(self):
        self.assertTrue(qp.is_operational_agent_query("estado del brain"))
        self.assertTrue(qp.is_operational_agent_query("revisa puertos"))
        self.assertFalse(qp.is_operational_agent_query("xxxxx"))

    # ---- canned failure --------------------------------------------------

    def test_looks_like_canned_failure(self):
        self.assertTrue(qp.looks_like_canned_failure(""))
        self.assertTrue(qp.looks_like_canned_failure("(sin respuesta)"))
        self.assertTrue(
            qp.looks_like_canned_failure("el agente no ejecutó ninguna herramienta")
        )
        self.assertFalse(qp.looks_like_canned_failure("respuesta valida del brain"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
