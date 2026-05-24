"""
P2-E Commit 4D-RealWriteCanaryPlan Unit Tests

Tests for SemanticMemoryRealWriteCanaryPlan and related classes.
"""

import pytest
from datetime import datetime
from typing import Dict, Any

from brain.semantic_memory_real_write_canary_plan import (
    SemanticMemoryCanaryDecision,
    SemanticMemoryCanarySeverity,
    SemanticMemoryCanaryFinding,
    SemanticMemoryRealWriteCanaryPlanReport,
    SemanticMemoryRealWriteCanaryPlan,
)
from brain.semantic_memory_decision_gate_evidence_adapter import (
    SemanticMemoryEvidenceAdapterStatus,
    SemanticMemoryDecisionGateEvidenceAdapter,
)


class TestSemanticMemoryCanaryDecision:
    """Tests for SemanticMemoryCanaryDecision enum."""
    
    def test_decision_block_exists(self):
        """Test BLOCK decision exists."""
        assert SemanticMemoryCanaryDecision.BLOCK == "BLOCK"
    
    def test_decision_noop_only_exists(self):
        """Test NOOP_ONLY decision exists."""
        assert SemanticMemoryCanaryDecision.NOOP_ONLY == "NOOP_ONLY"
    
    def test_decision_candidate_ready_exists(self):
        """Test CANDIDATE_READY decision exists."""
        assert SemanticMemoryCanaryDecision.CANDIDATE_READY == "CANDIDATE_READY"
    
    def test_decision_manual_review_exists(self):
        """Test MANUAL_REVIEW decision exists."""
        assert SemanticMemoryCanaryDecision.MANUAL_REVIEW == "MANUAL_REVIEW"
    
    def test_all_decisions_present(self):
        """Test all 4 decisions are present."""
        decisions = list(SemanticMemoryCanaryDecision)
        assert len(decisions) == 4
        assert SemanticMemoryCanaryDecision.BLOCK in decisions
        assert SemanticMemoryCanaryDecision.NOOP_ONLY in decisions
        assert SemanticMemoryCanaryDecision.CANDIDATE_READY in decisions
        assert SemanticMemoryCanaryDecision.MANUAL_REVIEW in decisions


class TestSemanticMemoryCanarySeverity:
    """Tests for SemanticMemoryCanarySeverity enum."""
    
    def test_severity_info_exists(self):
        """Test INFO severity exists."""
        assert SemanticMemoryCanarySeverity.INFO == "INFO"
    
    def test_severity_warning_exists(self):
        """Test WARNING severity exists."""
        assert SemanticMemoryCanarySeverity.WARNING == "WARNING"
    
    def test_severity_blocker_exists(self):
        """Test BLOCKER severity exists."""
        assert SemanticMemoryCanarySeverity.BLOCKER == "BLOCKER"
    
    def test_severity_critical_exists(self):
        """Test CRITICAL severity exists."""
        assert SemanticMemoryCanarySeverity.CRITICAL == "CRITICAL"
    
    def test_all_severities_present(self):
        """Test all 4 severities are present."""
        severities = list(SemanticMemoryCanarySeverity)
        assert len(severities) == 4
        assert SemanticMemoryCanarySeverity.INFO in severities
        assert SemanticMemoryCanarySeverity.WARNING in severities
        assert SemanticMemoryCanarySeverity.BLOCKER in severities
        assert SemanticMemoryCanarySeverity.CRITICAL in severities


class TestSemanticMemoryCanaryFinding:
    """Tests for SemanticMemoryCanaryFinding dataclass."""
    
    def test_finding_creation_basic(self):
        """Test basic finding creation."""
        finding = SemanticMemoryCanaryFinding(
            code="TEST_CODE",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Test message",
        )
        assert finding.code == "TEST_CODE"
        assert finding.severity == SemanticMemoryCanarySeverity.INFO
        assert finding.message == "Test message"
        assert finding.evidence == {}
        assert finding.timestamp_utc is not None
    
    def test_finding_creation_with_evidence(self):
        """Test finding creation with evidence."""
        finding = SemanticMemoryCanaryFinding(
            code="TEST_WITH_EVIDENCE",
            severity=SemanticMemoryCanarySeverity.WARNING,
            message="Test with evidence",
            evidence={"key": "value", "number": 42},
        )
        assert finding.evidence == {"key": "value", "number": 42}
    
    def test_finding_to_dict(self):
        """Test finding to_dict conversion."""
        finding = SemanticMemoryCanaryFinding(
            code="TEST_DICT",
            severity=SemanticMemoryCanarySeverity.BLOCKER,
            message="Test dict",
            evidence={"test": True},
        )
        d = finding.to_dict()
        assert d["code"] == "TEST_DICT"
        assert d["severity"] == "BLOCKER"
        assert d["message"] == "Test dict"
        assert d["evidence"] == {"test": True}
        assert "timestamp_utc" in d
    
    def test_finding_severity_variations(self):
        """Test finding with different severities."""
        for sev in SemanticMemoryCanarySeverity:
            finding = SemanticMemoryCanaryFinding(
                code=f"TEST_{sev.name}",
                severity=sev,
                message=f"Test {sev.name}",
            )
            assert finding.severity == sev


class TestSemanticMemoryRealWriteCanaryPlanReport:
    """Tests for SemanticMemoryRealWriteCanaryPlanReport dataclass."""
    
    def test_report_creation_defaults(self):
        """Test report creation with defaults."""
        report = SemanticMemoryRealWriteCanaryPlanReport(
            canary_id="test_canary_123",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryCanaryDecision.NOOP_ONLY,
            status="TEST",
            findings=[],
            blocker_count=0,
            warning_count=0,
            info_count=0,
            critical_count=0,
        )
        assert report.canary_id == "test_canary_123"
        assert report.allow_real_write == False
        assert report.dry_run_only == True
        assert report.can_execute_real_write == False
    
    def test_report_invariants_always_false(self):
        """Test report invariants are always False/True as expected."""
        report = SemanticMemoryRealWriteCanaryPlanReport(
            canary_id="test",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryCanaryDecision.CANDIDATE_READY,
            status="TEST",
            findings=[],
            blocker_count=0,
            warning_count=0,
            info_count=0,
            critical_count=0,
            allow_real_write=False,  # Explicit
            dry_run_only=True,  # Explicit
            can_execute_real_write=False,  # Explicit
        )
        assert report.allow_real_write == False
        assert report.dry_run_only == True
        assert report.can_execute_real_write == False
    
    def test_report_with_findings(self):
        """Test report with findings."""
        findings = [
            SemanticMemoryCanaryFinding(
                code="TEST_FINDING",
                severity=SemanticMemoryCanarySeverity.INFO,
                message="Test finding",
            ),
        ]
        report = SemanticMemoryRealWriteCanaryPlanReport(
            canary_id="test",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryCanaryDecision.NOOP_ONLY,
            status="TEST",
            findings=findings,
            blocker_count=0,
            warning_count=0,
            info_count=1,
            critical_count=0,
        )
        assert len(report.findings) == 1
        assert report.info_count == 1
    
    def test_report_to_dict(self):
        """Test report to_dict conversion."""
        finding = SemanticMemoryCanaryFinding(
            code="TEST",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Test",
        )
        report = SemanticMemoryRealWriteCanaryPlanReport(
            canary_id="test_canary",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryCanaryDecision.NOOP_ONLY,
            status="NOOP",
            findings=[finding],
            blocker_count=0,
            warning_count=0,
            info_count=1,
            critical_count=0,
            allow_real_write=False,
            dry_run_only=True,
            can_execute_real_write=False,
        )
        d = report.to_dict()
        assert d["canary_id"] == "test_canary"
        assert d["decision"] == "NOOP_ONLY"
        assert d["allow_real_write"] == False
        assert d["dry_run_only"] == True
        assert d["can_execute_real_write"] == False
        assert len(d["findings"]) == 1


class TestSemanticMemoryRealWriteCanaryPlan:
    """Tests for SemanticMemoryRealWriteCanaryPlan class."""
    
    def test_canary_plan_initialization(self):
        """Test canary plan initialization."""
        plan = SemanticMemoryRealWriteCanaryPlan(repo_root=".")
        assert plan._repo_root is not None
        assert plan._canary_id.startswith("canary_")
        assert plan._created_at is not None
    
    def test_canary_plan_initialization_with_path(self):
        """Test canary plan initialization with Path."""
        from pathlib import Path
        plan = SemanticMemoryRealWriteCanaryPlan(repo_root=Path("."))
        assert isinstance(plan._repo_root, Path)
    
    def test_canary_codes_exist(self):
        """Test that canary codes dictionary exists."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        assert hasattr(plan, 'CANARY_CODES')
        assert "ADAPTER_VALIDATION_PASSED" in plan.CANARY_CODES
        assert "REAL_WRITE_BLOCKED" in plan.CANARY_CODES
        assert "DRY_RUN_ENFORCED" in plan.CANARY_CODES
    
    def test_evaluate_canary_plan_no_bundle(self):
        """Test canary evaluation without evidence bundle."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan(evidence_bundle=None)
        assert report.canary_id.startswith("canary_")
        assert report.allow_real_write == False
        assert report.dry_run_only == True
        assert report.can_execute_real_write == False
        assert report.evidence_bundle_valid == False
    
    def test_evaluate_canary_plan_with_valid_bundle(self):
        """Test canary evaluation with valid evidence bundle."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        
        # Create a valid evidence bundle
        bundle = {
            "bundle_id": "test_bundle_123",
            "producer": "test_producer",
            "created_at_utc": datetime.now().isoformat(),
            "git_state": {
                "head_commit": "abc123",
                "branch": "main",
                "commits_ahead": 0,
                "dirty_files_count": 0,
                "staged_files_count": 0,
            },
            "risk_summary": {
                "total_extra_files": 0,
                "critical_extra_files": [],
                "dependency_hits": [],
                "high_risk_hits": 0,
            },
            "security_validation": {
                "passed": True,
                "has_subprocess": False,
                "has_faiss": False,
                "has_bridge": False,
                "has_add_memory": False,
            },
            "test_results": {
                "all_tests_passed": True,
                "test_count": 10,
            },
            "smoke_results": {
                "all_smokes_passed": True,
                "smoke_count": 3,
            },
        }
        
        report = plan.evaluate_canary_plan(evidence_bundle=bundle)
        assert report.allow_real_write == False
        assert report.dry_run_only == True
        assert report.can_execute_real_write == False
        # Should have findings
        assert len(report.findings) > 0
    
    def test_evaluate_canary_plan_safety_invariants_passed(self):
        """Test that safety invariants are always passed."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan()
        assert report.safety_invariants_passed == True
    
    def test_create_noop_canary_report(self):
        """Test creating noop canary report."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.create_noop_canary_report()
        assert report.decision == SemanticMemoryCanaryDecision.NOOP_ONLY
        assert report.status == "NOOP_DEFAULT"
        assert report.allow_real_write == False
        assert report.dry_run_only == True
        assert report.can_execute_real_write == False
    
    def test_create_noop_canary_report_has_findings(self):
        """Test noop report has expected findings."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.create_noop_canary_report()
        assert len(report.findings) > 0
        # Check for expected findings
        codes = [f.code for f in report.findings]
        assert "CANARY_PLAN_ACTIVE" in codes
        assert "NOOP_OPERATION_ONLY" in codes
    
    def test_block_canary(self):
        """Test blocking canary."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.block_canary(reason="Test block reason")
        assert report.decision == SemanticMemoryCanaryDecision.BLOCK
        assert report.status == "BLOCKED"
        assert report.allow_real_write == False
        assert "Test block reason" in report.blockers
    
    def test_block_canary_with_critical_finding(self):
        """Test block canary creates critical finding."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.block_canary(reason="Critical block")
        critical_findings = [f for f in report.findings if f.severity == SemanticMemoryCanarySeverity.CRITICAL]
        assert len(critical_findings) > 0
    
    def test_summarize_canary_plan(self):
        """Test summarize canary plan."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        summary = plan.summarize_canary_plan()
        assert summary["canary_version"] == "P2-E-Commit-4D-RealWriteCanaryPlan"
        assert summary["allow_real_write"] == False
        assert summary["dry_run_only"] == True
        assert summary["can_execute_real_write"] == False
        assert "decision_states" in summary
        assert "limitations" in summary
        assert "invariants" in summary
    
    def test_summarize_has_decision_states(self):
        """Test summary has all decision states."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        summary = plan.summarize_canary_plan()
        states = summary["decision_states"]
        assert "BLOCK" in states
        assert "NOOP_ONLY" in states
        assert "CANDIDATE_READY" in states
        assert "MANUAL_REVIEW" in states
    
    def test_summarize_has_limitations(self):
        """Test summary has limitations list."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        summary = plan.summarize_canary_plan()
        limitations = summary["limitations"]
        assert len(limitations) > 0
        # Check some key limitations
        assert any("subprocess" in lim.lower() for lim in limitations)
        assert any("write" in lim.lower() for lim in limitations)
    
    def test_summarize_has_invariants(self):
        """Test summary has invariants list."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        summary = plan.summarize_canary_plan()
        invariants = summary["invariants"]
        assert len(invariants) >= 3
        assert any("allow_real_write=False" in inv for inv in invariants)
        assert any("dry_run_only=True" in inv for inv in invariants)
    
    def test_canary_plan_requires_manual_review_by_default(self):
        """Test canary plan requires manual review by default."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan()
        assert report.requires_manual_review == True
    
    def test_canary_plan_adapter_initialized(self):
        """Test that evidence adapter is initialized."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        assert hasattr(plan, '_adapter')
        assert plan._adapter is not None
    
    def test_report_counts_calculated_correctly(self):
        """Test report counts are calculated correctly."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan()
        
        # Verify counts match actual findings
        blocker_count = sum(1 for f in report.findings if f.severity == SemanticMemoryCanarySeverity.BLOCKER)
        warning_count = sum(1 for f in report.findings if f.severity == SemanticMemoryCanarySeverity.WARNING)
        info_count = sum(1 for f in report.findings if f.severity == SemanticMemoryCanarySeverity.INFO)
        critical_count = sum(1 for f in report.findings if f.severity == SemanticMemoryCanarySeverity.CRITICAL)
        
        assert report.blocker_count == blocker_count
        assert report.warning_count == warning_count
        assert report.info_count == info_count
        assert report.critical_count == critical_count


class TestCanaryPlanInvariants:
    """Tests for canary plan invariants."""
    
    def test_no_subprocess_in_module(self):
        """Verify no subprocess import in module."""
        import ast
        import inspect
        from brain import semantic_memory_real_write_canary_plan as module
        
        source = inspect.getsource(module)
        tree = ast.parse(source)
        
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module)
        
        assert "subprocess" not in imports
    
    def test_no_faiss_in_module(self):
        """Verify no faiss import in module."""
        import ast
        import inspect
        from brain import semantic_memory_real_write_canary_plan as module

        source = inspect.getsource(module)
        tree = ast.parse(source)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        assert "faiss" not in imports

    def test_no_semantic_memory_bridge_in_module(self):
        """Verify no semantic_memory_bridge import in module."""
        import ast
        import inspect
        from brain import semantic_memory_real_write_canary_plan as module

        source = inspect.getsource(module)
        tree = ast.parse(source)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        assert "semantic_memory_bridge" not in imports

    def test_no_add_memory_in_module(self):
        """Verify no add_memory calls in module."""
        import ast
        import inspect
        from brain import semantic_memory_real_write_canary_plan as module

        source = inspect.getsource(module)
        tree = ast.parse(source)

        # Check for function calls named 'add_memory'
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "add_memory":
                    assert False, "add_memory call found in module"
                # Also check attribute access like something.add_memory
                if isinstance(node.func, ast.Attribute) and node.func.attr == "add_memory":
                    assert False, "add_memory method call found in module"
    
    def test_allow_real_write_always_false_in_evaluate(self):
        """Verify allow_real_write is always False in evaluate results."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan()
        assert report.allow_real_write == False
    
    def test_dry_run_only_always_true_in_evaluate(self):
        """Verify dry_run_only is always True in evaluate results."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan()
        assert report.dry_run_only == True
    
    def test_can_execute_real_write_always_false_in_evaluate(self):
        """Verify can_execute_real_write is always False in evaluate results."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan()
        assert report.can_execute_real_write == False


class TestCanaryPlanWithEvidenceBundle:
    """Tests for canary plan with evidence bundles."""
    
    def test_canary_with_accepted_adapter_status(self):
        """Test canary with accepted adapter status."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        
        bundle = {
            "bundle_id": "test_bundle",
            "producer": "test",
            "created_at_utc": datetime.now().isoformat(),
            "git_state": {
                "head_commit": "abc123",
                "branch": "main",
                "commits_ahead": 0,
                "dirty_files_count": 0,
                "staged_files_count": 0,
            },
            "risk_summary": {
                "total_extra_files": 0,
                "critical_extra_files": [],
                "dependency_hits": [],
                "high_risk_hits": 0,
            },
            "security_validation": {
                "passed": True,
                "has_subprocess": False,
                "has_faiss": False,
                "has_bridge": False,
                "has_add_memory": False,
            },
            "test_results": {
                "all_tests_passed": True,
                "test_count": 10,
            },
            "smoke_results": {
                "all_smokes_passed": True,
                "smoke_count": 3,
            },
        }
        
        report = plan.evaluate_canary_plan(evidence_bundle=bundle)
        # Verify the report has expected structure
        assert report.adapter_report_id is not None
        assert report.adapter_status is not None
    
    def test_canary_report_with_bundle_has_adapter_info(self):
        """Test canary report includes adapter info when bundle provided."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        
        bundle = {
            "bundle_id": "test_bundle_456",
            "producer": "test_producer",
            "created_at_utc": datetime.now().isoformat(),
            "git_state": {
                "head_commit": "abc123",
                "branch": "main",
                "commits_ahead": 0,
                "dirty_files_count": 0,
                "staged_files_count": 0,
            },
            "risk_summary": {
                "total_extra_files": 0,
                "critical_extra_files": [],
                "dependency_hits": [],
                "high_risk_hits": 0,
            },
            "security_validation": {
                "passed": True,
                "has_subprocess": False,
                "has_faiss": False,
                "has_bridge": False,
                "has_add_memory": False,
            },
            "test_results": {
                "all_tests_passed": True,
                "test_count": 10,
            },
            "smoke_results": {
                "all_smokes_passed": True,
                "smoke_count": 3,
            },
        }
        
        report = plan.evaluate_canary_plan(evidence_bundle=bundle)
        assert report.metadata["evidence_bundle_provided"] == True
        assert report.metadata["bundle_id"] == "test_bundle_456"


class TestCanaryPlanEdgeCases:
    """Tests for edge cases."""
    
    def test_canary_plan_empty_bundle(self):
        """Test canary plan with empty bundle."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        report = plan.evaluate_canary_plan(evidence_bundle={})
        assert report.allow_real_write == False
        assert report.dry_run_only == True
    
    def test_canary_plan_partial_bundle(self):
        """Test canary plan with partial bundle."""
        plan = SemanticMemoryRealWriteCanaryPlan()
        partial_bundle = {
            "bundle_id": "partial",
            "producer": "test",
        }
        report = plan.evaluate_canary_plan(evidence_bundle=partial_bundle)
        assert report.allow_real_write == False
        assert report.dry_run_only == True
    
    def test_finding_with_complex_evidence(self):
        """Test finding with complex nested evidence."""
        finding = SemanticMemoryCanaryFinding(
            code="COMPLEX_EVIDENCE",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Complex evidence test",
            evidence={
                "nested": {
                    "deep": {
                        "value": 123,
                        "list": [1, 2, 3],
                    },
                },
                "array": ["a", "b", "c"],
            },
        )
        d = finding.to_dict()
        assert d["evidence"]["nested"]["deep"]["value"] == 123
        assert d["evidence"]["array"] == ["a", "b", "c"]
    
    def test_report_with_blockers_and_warnings(self):
        """Test report with blockers and warnings lists."""
        report = SemanticMemoryRealWriteCanaryPlanReport(
            canary_id="test",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryCanaryDecision.BLOCK,
            status="BLOCKED",
            findings=[],
            blocker_count=2,
            warning_count=1,
            info_count=0,
            critical_count=0,
            blockers=["Blocker 1", "Blocker 2"],
            warnings=["Warning 1"],
        )
        assert len(report.blockers) == 2
        assert len(report.warnings) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
