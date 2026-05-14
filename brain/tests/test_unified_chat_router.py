"""
Tests for UnifiedChatRouter — brain/unified_chat_router.py
51 tests covering classify(), enrich_system_prompt(), should_use_agent(),
confidence scores, edge cases, singleton, and pattern compilation.
"""

import pytest
from unittest.mock import patch

from brain.unified_chat_router import (
    UnifiedChatRouter,
    IntentCategory,
    RoutingDecision,
    get_router,
    SELF_AWARENESS_PATTERNS,
    DASHBOARD_PATTERNS,
    LEARNING_PATTERNS,
    GOAL_PATTERNS,
    AGENT_PATTERNS,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def router():
    return UnifiedChatRouter()


# ─── IntentCategory enum tests ───────────────────────────────────────────────

class TestIntentCategory:
    def test_general_conversation_value(self):
        assert IntentCategory.GENERAL_CONVERSATION.value == "general_conversation"

    def test_self_awareness_value(self):
        assert IntentCategory.SELF_AWARENESS.value == "self_awareness"

    def test_dashboard_analysis_value(self):
        assert IntentCategory.DASHBOARD_ANALYSIS.value == "dashboard_analysis"

    def test_learning_request_value(self):
        assert IntentCategory.LEARNING_REQUEST.value == "learning_request"

    def test_goal_management_value(self):
        assert IntentCategory.GOAL_MANAGEMENT.value == "goal_management"

    def test_agent_task_value(self):
        assert IntentCategory.AGENT_TASK.value == "agent_task"

    def test_all_categories_count(self):
        assert len(IntentCategory) == 6


# ─── classify() — SELF_AWARENESS ────────────────────────────────────────────

class TestClassifySelfAwareness:
    def test_classify_self_awareness_spanish_que_puedes_hacer(self, router):
        decision = router.classify("¿Qué puedes hacer?")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_spanish_que_no_puedes(self, router):
        decision = router.classify("¿Qué no puedes hacer?")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_spanish_limitaciones(self, router):
        decision = router.classify("¿Cuáles son tus limitaciones?")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_spanish_autoconciencia(self, router):
        decision = router.classify("Hablame de autoconciencia")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_spanish_estado_interno(self, router):
        decision = router.classify("¿Cómo estás internamente?")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_english_what_can_you_do(self, router):
        decision = router.classify("What can you do?")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_english_self_awareness(self, router):
        decision = router.classify("Tell me about self-awareness")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_english_know_your_limits(self, router):
        decision = router.classify("You should know your limits")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_spanish_stress_level(self, router):
        decision = router.classify("¿Cuál es tu stress level?")
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_classify_self_awareness_spanish_fase_autonomia(self, router):
        decision = router.classify("¿En qué fase de autonomía estás?")
        assert decision.category == IntentCategory.SELF_AWARENESS


# ─── classify() — DASHBOARD_ANALYSIS ─────────────────────────────────────────

class TestClassifyDashboard:
    def test_classify_dashboard_spanish_analiza(self, router):
        decision = router.classify("Analiza el dashboard")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS

    def test_classify_dashboard_spanish_panel(self, router):
        decision = router.classify("Muestra el panel de control")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS

    def test_classify_dashboard_spanish_estado_sistema(self, router):
        decision = router.classify("¿Cuál es el estado del sistema?")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS

    def test_classify_dashboard_english_health_check(self, router):
        decision = router.classify("Show me the health check results")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS

    def test_classify_dashboard_english_dashboard(self, router):
        decision = router.classify("Show me the dashboard")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS

    def test_classify_dashboard_spanish_rsi(self, router):
        decision = router.classify("¿Cómo está la resiliencia?")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS

    def test_classify_dashboard_spanish_servicios_caidos(self, router):
        decision = router.classify("¿Hay servicios caídos?")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS

    def test_classify_dashboard_english_needs_attention(self, router):
        decision = router.classify("What needs attention?")
        assert decision.category == IntentCategory.DASHBOARD_ANALYSIS


# ─── classify() — LEARNING_REQUEST ───────────────────────────────────────────

class TestClassifyLearning:
    def test_classify_learning_spanish_aprende(self, router):
        decision = router.classify("Aprende sobre trading")
        assert decision.category == IntentCategory.LEARNING_REQUEST

    def test_classify_learning_english_learn(self, router):
        decision = router.classify("I want to learn Python")
        assert decision.category == IntentCategory.LEARNING_REQUEST

    def test_classify_learning_spanish_investiga(self, router):
        decision = router.classify("Investiga este tema")
        assert decision.category == IntentCategory.LEARNING_REQUEST

    def test_classify_learning_english_research(self, router):
        decision = router.classify("Research this topic")
        assert decision.category == IntentCategory.LEARNING_REQUEST

    def test_classify_learning_spanish_ensena(self, router):
        decision = router.classify("Enseña sobre machine learning")
        assert decision.category == IntentCategory.LEARNING_REQUEST

    def test_classify_learning_spanish_brecha_conocimiento(self, router):
        decision = router.classify("Tengo una brecha de conocimiento")
        assert decision.category == IntentCategory.LEARNING_REQUEST


# ─── classify() — GOAL_MANAGEMENT ───────────────────────────────────────────

class TestClassifyGoal:
    def test_classify_goal_spanish_crea_objetivo(self, router):
        decision = router.classify("Crea un objetivo de aprendizaje")
        assert decision.category == IntentCategory.GOAL_MANAGEMENT

    def test_classify_goal_english_create_goal(self, router):
        decision = router.classify("Create a goal for this week")
        assert decision.category == IntentCategory.GOAL_MANAGEMENT

    def test_classify_goal_spanish_aos(self, router):
        decision = router.classify("¿Cómo va el AOS?")
        assert decision.category == IntentCategory.GOAL_MANAGEMENT

    def test_classify_goal_english_active_goals(self, router):
        decision = router.classify("Show me active goals")
        assert decision.category == IntentCategory.GOAL_MANAGEMENT

    def test_classify_goal_spanish_progreso(self, router):
        decision = router.classify("¿Cuál es el progreso de objetivos?")
        assert decision.category == IntentCategory.GOAL_MANAGEMENT


# ─── classify() — AGENT_TASK ─────────────────────────────────────────────────

class TestClassifyAgent:
    def test_classify_agent_spanish_ejecuta(self, router):
        decision = router.classify("Ejecuta el script de prueba")
        assert decision.category == IntentCategory.AGENT_TASK

    def test_classify_agent_english_run(self, router):
        decision = router.classify("Run the test suite")
        assert decision.category == IntentCategory.AGENT_TASK

    def test_classify_agent_english_debug(self, router):
        decision = router.classify("Debug this issue")
        assert decision.category == IntentCategory.AGENT_TASK

    def test_classify_agent_spanish_diagnostica(self, router):
        decision = router.classify("Diagnostica el problema")
        assert decision.category == IntentCategory.AGENT_TASK

    def test_classify_agent_file_extension(self, router):
        decision = router.classify("Revisa el archivo config.py")
        assert decision.category == IntentCategory.AGENT_TASK

    def test_classify_agent_spanish_instala(self, router):
        decision = router.classify("Instala la dependencia")
        assert decision.category == IntentCategory.AGENT_TASK

    def test_classify_agent_spanish_escanea(self, router):
        decision = router.classify("Escanea los puertos")
        assert decision.category == IntentCategory.AGENT_TASK


# ─── classify() — GENERAL_CONVERSATION ───────────────────────────────────────

class TestClassifyGeneral:
    def test_classify_general_greeting(self, router):
        decision = router.classify("Hola, buenos días")
        assert decision.category == IntentCategory.GENERAL_CONVERSATION

    def test_classify_general_question(self, router):
        decision = router.classify("¿Cómo está el clima hoy?")
        assert decision.category == IntentCategory.GENERAL_CONVERSATION

    def test_classify_general_thanks(self, router):
        decision = router.classify("Gracias por tu ayuda")
        assert decision.category == IntentCategory.GENERAL_CONVERSATION

    def test_classify_general_random(self, router):
        decision = router.classify("Me gusta el café")
        assert decision.category == IntentCategory.GENERAL_CONVERSATION


# ─── RoutingDecision structure ───────────────────────────────────────────────

class TestRoutingDecision:
    def test_decision_has_category(self, router):
        decision = router.classify("Hola")
        assert hasattr(decision, "category")

    def test_decision_has_confidence(self, router):
        decision = router.classify("Hola")
        assert hasattr(decision, "confidence")
        assert 0.0 <= decision.confidence <= 1.0

    def test_decision_has_matched_patterns(self, router):
        decision = router.classify("Aprende esto")
        assert hasattr(decision, "matched_patterns")
        assert isinstance(decision.matched_patterns, list)

    def test_decision_has_metadata(self, router):
        decision = router.classify("Hola")
        assert hasattr(decision, "metadata")
        assert isinstance(decision.metadata, dict)

    def test_general_no_matched_patterns(self, router):
        decision = router.classify("Hola mundo")
        assert decision.matched_patterns == []

    def test_general_has_reason_metadata(self, router):
        decision = router.classify("Hola mundo")
        assert decision.metadata.get("reason") == "no_pattern_matched"


# ─── Confidence scores ───────────────────────────────────────────────────────

class TestConfidence:
    def test_general_confidence_is_high(self, router):
        decision = router.classify("Hola")
        assert decision.confidence >= 0.5

    def test_pattern_match_confidence_boosted(self, router):
        decision = router.classify("Aprende esto")
        assert decision.confidence > 0.3

    def test_confidence_capped_at_095(self, router):
        decision = router.classify("¿Qué puedes hacer? ¿Cuáles son tus limitaciones? Autoconciencia")
        assert decision.confidence <= 0.95

    def test_matched_patterns_populated(self, router):
        decision = router.classify("Aprende esto")
        assert len(decision.matched_patterns) > 0


# ─── enrich_system_prompt() ──────────────────────────────────────────────────

class TestEnrichSystemPrompt:
    def test_enrich_self_awareness(self, router):
        decision = RoutingDecision(
            category=IntentCategory.SELF_AWARENESS,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("Base prompt", decision)
        assert "HONESTAMENTE" in result

    def test_enrich_self_awareness_with_block(self, router):
        decision = RoutingDecision(
            category=IntentCategory.SELF_AWARENESS,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("Base prompt", decision,
                                              self_awareness_block="Capacidades: 5")
        assert "Capacidades: 5" in result

    def test_enrich_dashboard_analysis(self, router):
        decision = RoutingDecision(
            category=IntentCategory.DASHBOARD_ANALYSIS,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("Base prompt", decision)
        assert "Analiza" in result or "dashboard" in result.lower()

    def test_enrich_dashboard_with_block(self, router):
        decision = RoutingDecision(
            category=IntentCategory.DASHBOARD_ANALYSIS,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("Base prompt", decision,
                                              dashboard_block="Score: 0.9")
        assert "Score: 0.9" in result

    def test_enrich_learning_request(self, router):
        decision = RoutingDecision(
            category=IntentCategory.LEARNING_REQUEST,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("Base prompt", decision)
        assert "aprender" in result.lower()

    def test_enrich_goal_management(self, router):
        decision = RoutingDecision(
            category=IntentCategory.GOAL_MANAGEMENT,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("Base prompt", decision)
        assert "objetivos" in result.lower()

    def test_enrich_agent_task(self, router):
        decision = RoutingDecision(
            category=IntentCategory.AGENT_TASK,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("Base prompt", decision)
        assert "ORAV" in result

    def test_enrich_general_no_addition(self, router):
        decision = RoutingDecision(
            category=IntentCategory.GENERAL_CONVERSATION,
            confidence=0.9,
        )
        result = router.enrich_system_prompt("Base prompt", decision)
        assert result == "Base prompt"

    def test_enrich_preserves_base_prompt(self, router):
        decision = RoutingDecision(
            category=IntentCategory.SELF_AWARENESS,
            confidence=0.8,
        )
        result = router.enrich_system_prompt("My base prompt", decision)
        assert "My base prompt" in result


# ─── should_use_agent() ──────────────────────────────────────────────────────

class TestShouldUseAgent:
    def test_agent_task_high_confidence(self, router):
        decision = RoutingDecision(
            category=IntentCategory.AGENT_TASK,
            confidence=0.8,
        )
        assert router.should_use_agent(decision) is True

    def test_agent_task_low_confidence(self, router):
        decision = RoutingDecision(
            category=IntentCategory.AGENT_TASK,
            confidence=0.3,
        )
        assert router.should_use_agent(decision) is False

    def test_dashboard_high_confidence(self, router):
        decision = RoutingDecision(
            category=IntentCategory.DASHBOARD_ANALYSIS,
            confidence=0.8,
        )
        assert router.should_use_agent(decision) is True

    def test_dashboard_low_confidence(self, router):
        decision = RoutingDecision(
            category=IntentCategory.DASHBOARD_ANALYSIS,
            confidence=0.4,
        )
        assert router.should_use_agent(decision) is False

    def test_self_awareness_never_uses_agent(self, router):
        decision = RoutingDecision(
            category=IntentCategory.SELF_AWARENESS,
            confidence=0.9,
        )
        assert router.should_use_agent(decision) is False

    def test_learning_never_uses_agent(self, router):
        decision = RoutingDecision(
            category=IntentCategory.LEARNING_REQUEST,
            confidence=0.9,
        )
        assert router.should_use_agent(decision) is False

    def test_goal_never_uses_agent(self, router):
        decision = RoutingDecision(
            category=IntentCategory.GOAL_MANAGEMENT,
            confidence=0.9,
        )
        assert router.should_use_agent(decision) is False

    def test_general_never_uses_agent(self, router):
        decision = RoutingDecision(
            category=IntentCategory.GENERAL_CONVERSATION,
            confidence=0.9,
        )
        assert router.should_use_agent(decision) is False

    def test_agent_exactly_at_threshold(self, router):
        decision = RoutingDecision(
            category=IntentCategory.AGENT_TASK,
            confidence=0.5,
        )
        assert router.should_use_agent(decision) is False


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_message(self, router):
        decision = router.classify("")
        assert decision.category == IntentCategory.GENERAL_CONVERSATION

    def test_very_long_message(self, router):
        msg = "Aprende " * 1000
        decision = router.classify(msg)
        assert decision.category == IntentCategory.LEARNING_REQUEST

    def test_mixed_language_self_awareness(self, router):
        decision = router.classify("What can you do? ¿Cuáles son tus limitaciones?")
        # Should match self-awareness patterns from both languages
        assert decision.category == IntentCategory.SELF_AWARENESS

    def test_whitespace_only_message(self, router):
        decision = router.classify("   \t\n  ")
        assert decision.category == IntentCategory.GENERAL_CONVERSATION

    def test_special_characters_message(self, router):
        decision = router.classify("!@#$%^&*()")
        assert decision.category == IntentCategory.GENERAL_CONVERSATION

    def test_case_insensitive_matching(self, router):
        decision1 = router.classify("APRENDE esto")
        decision2 = router.classify("aprende esto")
        assert decision1.category == decision2.category


# ─── Pattern compilation ─────────────────────────────────────────────────────

class TestPatternCompilation:
    def test_patterns_compiled_on_init(self, router):
        assert len(router._compiled) == 5

    def test_all_non_general_categories_compiled(self, router):
        expected = {
            IntentCategory.SELF_AWARENESS,
            IntentCategory.DASHBOARD_ANALYSIS,
            IntentCategory.LEARNING_REQUEST,
            IntentCategory.GOAL_MANAGEMENT,
            IntentCategory.AGENT_TASK,
        }
        assert set(router._compiled.keys()) == expected

    def test_compiled_patterns_are_regex(self, router):
        import re
        for category, patterns in router._compiled.items():
            for p in patterns:
                assert isinstance(p, re.Pattern)

    def test_self_awareness_pattern_count(self, router):
        assert len(router._compiled[IntentCategory.SELF_AWARENESS]) == len(SELF_AWARENESS_PATTERNS)

    def test_dashboard_pattern_count(self, router):
        assert len(router._compiled[IntentCategory.DASHBOARD_ANALYSIS]) == len(DASHBOARD_PATTERNS)

    def test_learning_pattern_count(self, router):
        assert len(router._compiled[IntentCategory.LEARNING_REQUEST]) == len(LEARNING_PATTERNS)

    def test_goal_pattern_count(self, router):
        assert len(router._compiled[IntentCategory.GOAL_MANAGEMENT]) == len(GOAL_PATTERNS)

    def test_agent_pattern_count(self, router):
        assert len(router._compiled[IntentCategory.AGENT_TASK]) == len(AGENT_PATTERNS)


# ─── get_router() singleton ──────────────────────────────────────────────────

class TestGetRouter:
    def test_get_router_returns_instance(self):
        # Reset singleton
        import brain.unified_chat_router as mod
        mod._router = None
        r = get_router()
        assert isinstance(r, UnifiedChatRouter)

    def test_get_router_singleton(self):
        import brain.unified_chat_router as mod
        mod._router = None
        r1 = get_router()
        r2 = get_router()
        assert r1 is r2

    def test_get_router_creates_new_after_reset(self):
        import brain.unified_chat_router as mod
        mod._router = None
        r1 = get_router()
        mod._router = None
        r2 = get_router()
        assert r1 is not r2
