"""
Integration test — verifies all brain modules can be imported together.
"""

import pytest


class TestIntegration:
    def test_import_unified_chat_router(self):
        from brain.unified_chat_router import UnifiedChatRouter, IntentCategory, RoutingDecision, get_router
        assert UnifiedChatRouter is not None
        assert IntentCategory is not None

    def test_import_self_awareness_injector(self):
        from brain.self_awareness_injector import SelfAwarenessInjector, AwarenessBlock, get_injector
        assert SelfAwarenessInjector is not None
        assert AwarenessBlock is not None

    def test_import_dashboard_reader(self):
        from brain.dashboard_reader import DashboardReader, DashboardAnalysis, ServiceIssue, get_dashboard_reader
        assert DashboardReader is not None
        assert DashboardAnalysis is not None

    def test_import_auto_tick_loop(self):
        from brain.auto_tick_loop import AutoTickLoop, TickNotification, NotificationType, get_auto_tick_loop
        assert AutoTickLoop is not None
        assert NotificationType is not None

    def test_import_learning_validator(self):
        from brain.learning_validator import LearningValidator, ValidationStatus, ValidationStrategy, ValidationResult
        assert LearningValidator is not None
        assert ValidationStatus is not None

    def test_import_semantic_memory_bridge(self):
        from brain.semantic_memory_bridge import SemanticMemoryBridge, MemoryContext, get_semantic_memory_bridge
        assert SemanticMemoryBridge is not None
        assert MemoryContext is not None

    def test_import_information_curator(self):
        from brain.information_curator import InformationCurator, ContentTopic, QualityLevel, CuratedRecord
        assert InformationCurator is not None
        assert ContentTopic is not None

    def test_import_phase_evaluator(self):
        from brain.phase_evaluator import PhaseEvaluator, AutonomyPhase, PhaseCriterion, PhaseEvaluation
        assert PhaseEvaluator is not None
        assert AutonomyPhase is not None

    def test_all_modules_coexist(self):
        """Verify all modules can be imported in the same process without conflicts."""
        from brain.unified_chat_router import UnifiedChatRouter
        from brain.self_awareness_injector import SelfAwarenessInjector
        from brain.dashboard_reader import DashboardReader
        from brain.auto_tick_loop import AutoTickLoop
        from brain.learning_validator import LearningValidator
        from brain.semantic_memory_bridge import SemanticMemoryBridge
        from brain.information_curator import InformationCurator
        from brain.phase_evaluator import PhaseEvaluator

        # Create instances of each
        router = UnifiedChatRouter()
        injector = SelfAwarenessInjector()
        reader = DashboardReader()
        loop = AutoTickLoop()
        validator = LearningValidator()
        bridge = SemanticMemoryBridge()
        curator = InformationCurator()
        evaluator = PhaseEvaluator()

        assert all([
            router, injector, reader, loop,
            validator, bridge, curator, evaluator,
        ])
