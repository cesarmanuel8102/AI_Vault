"""
P2-E Commit 4D-EvidenceInjection: Tests unitarios para SemanticMemoryExternalEvidenceContract
"""

import sys
from pathlib import Path

# Add parent directory to path to import brain module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from brain.semantic_memory_external_evidence_contract import (
    SemanticMemoryExternalEvidenceContract,
    SemanticMemoryEvidenceStatus,
    SemanticMemoryEvidenceSeverity,
    SemanticMemoryEvidenceFinding,
    SemanticMemoryExternalEvidenceBundle,
    SemanticMemoryExternalEvidenceValidationReport,
)


class TestSemanticMemoryExternalEvidenceContract:
    """Tests para el contrato de evidencia externa."""
    
    def test_empty_bundle_returns_rejected(self, tmp_path):
        """Test que bundle vacío devuelve REJECTED."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        report = contract.validate_bundle_read_only({})
        
        assert report.status == SemanticMemoryEvidenceStatus.REJECTED
        assert report.blocker_count > 0
    
    def test_missing_git_state_returns_rejected(self, tmp_path):
        """Test que falta git_state devuelve REJECTED."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-1",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {},
            "risk_summary": {"verified": True},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True},
            "smoke_summary": {"verified": True},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        assert report.status == SemanticMemoryEvidenceStatus.REJECTED
        missing = any("MISSING_GIT_STATE" in f.code for f in report.findings)
        assert missing
    
    def test_git_state_not_verified_returns_blocker(self, tmp_path):
        """Test que git_state not verified devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-2",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": False},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        not_verified = any("GIT_STATE_NOT_VERIFIED" in f.code for f in report.findings)
        assert not_verified
        assert any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
    
    def test_pending_commits_returns_blocker(self, tmp_path):
        """Test que pending commits > 0 devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-3",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 1, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        pending = any("PENDING_COMMITS" in f.code for f in report.findings)
        assert pending
        assert any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
    
    def test_staged_files_returns_blocker(self, tmp_path):
        """Test que staged files non-empty devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-4",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": ["file.py"]},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        staged = any("STAGED_FILES" in f.code for f in report.findings)
        assert staged
        assert any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
    
    def test_memory_semantic_in_commit_returns_blocker(self, tmp_path):
        """Test que memory_semantic_in_commit True devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-5",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {
                "verified": True, "pending_commits_vs_origin": 0, "staged_files": [],
                "memory_semantic_in_commit": True,
            },
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        mem = any("MEMORY_SEMANTIC_IN_COMMIT" in f.code for f in report.findings)
        assert mem
        assert any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
    
    def test_tmp_agent_strategies_in_commit_returns_blocker(self, tmp_path):
        """Test que tmp_agent_strategies_in_commit True devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-6",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {
                "verified": True, "pending_commits_vs_origin": 0, "staged_files": [],
                "tmp_agent_strategies_in_commit": True,
            },
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        tmp = any("TMP_AGENT_STRATEGIES_IN_COMMIT" in f.code for f in report.findings)
        assert tmp
    
    def test_nul_in_commit_returns_blocker(self, tmp_path):
        """Test que nul_in_commit True devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-7",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {
                "verified": True, "pending_commits_vs_origin": 0, "staged_files": [],
                "nul_in_commit": True,
            },
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        nul = any("NUL_IN_COMMIT" in f.code for f in report.findings)
        assert nul
    
    def test_runtime_active_returns_blocker(self, tmp_path):
        """Test que runtime_active True devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-8",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {
                "verified": True, "pending_commits_vs_origin": 0, "staged_files": [],
                "runtime_active": True,
            },
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        runtime = any("RUNTIME_ACTIVE" in f.code for f in report.findings)
        assert runtime
    
    def test_valid_git_state_accepted(self, tmp_path):
        """Test que git_state válido es aceptado."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-9",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {
                "verified": True, "pending_commits_vs_origin": 0, "staged_files": [],
                "memory_semantic_in_commit": False, "tmp_agent_strategies_in_commit": False,
                "nul_in_commit": False, "runtime_active": False,
            },
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True, "no_open": True, "no_subprocess": True, "no_faiss": True, "no_add_memory": True, "no_allow_real_write_true": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        # Should be accepted if all fields valid
        git_ok = not any(f.code.startswith("GIT") and f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
        assert git_ok
    
    def test_risk_summary_not_verified_returns_blocker(self, tmp_path):
        """Test que risk_summary not verified devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-10",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": False},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        risk = any("RISK_SUMMARY_NOT_VERIFIED" in f.code for f in report.findings)
        assert risk
    
    def test_unresolved_high_risk_returns_blocker(self, tmp_path):
        """Test que unresolved_high_risk_count > 0 devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-11",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 1},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        high = any("UNRESOLVED_HIGH_RISK" in f.code for f in report.findings)
        assert high
        assert any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
    
    def test_unresolved_write_like_returns_warning(self, tmp_path):
        """Test que unresolved_write_like_count > 0 devuelve warning."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-12",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0, "unresolved_write_like_count": 1},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        write = any("UNRESOLVED_WRITE_LIKE" in f.code for f in report.findings)
        assert write
    
    def test_unresolved_runtime_like_returns_warning(self, tmp_path):
        """Test que unresolved_runtime_like_count > 0 devuelve warning."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-13",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0, "unresolved_runtime_like_count": 1},
            "security_validation": {"verified": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        runtime = any("UNRESOLVED_RUNTIME_LIKE" in f.code for f in report.findings)
        assert runtime
    
    def test_security_validation_not_verified_returns_blocker(self, tmp_path):
        """Test que security_validation not verified devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-14",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": False},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        sec = any("SECURITY_VALIDATION_NOT_VERIFIED" in f.code for f in report.findings)
        assert sec
    
    def test_security_validation_critical_flags_fail(self, tmp_path):
        """Test que flags críticos de seguridad fallidos devuelven blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        critical_flags = [
            "no_open", "no_subprocess", "no_faiss", "no_requests_httpx",
            "no_semantic_memory_bridge", "no_add_memory", "no_write_ops",
            "no_delete_ops", "no_move_ops", "no_allow_real_write_true"
        ]
        
        for flag in critical_flags:
            bundle = {
                "bundle_id": f"test-{flag}",
                "created_at_utc": "2026-01-01T00:00:00",
                "producer": "test",
                "repo_root": str(tmp_path),
                "branch": "main",
                "head_hash": "abc123",
                "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
                "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
                "security_validation": {"verified": True, flag: False},
                "test_summary": {"verified": True, "failed": 0},
                "smoke_summary": {"verified": True, "failed": 0},
            }
            
            report = contract.validate_bundle_read_only(bundle)
            # Should have a blocker for this flag
            has_blocker = any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
            assert has_blocker, f"Flag {flag} should cause blocker"
    
    def test_test_summary_failed_returns_blocker(self, tmp_path):
        """Test que test_summary failed > 0 devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-15",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True, "no_open": True, "no_subprocess": True, "no_faiss": True, "no_add_memory": True, "no_allow_real_write_true": True},
            "test_summary": {"verified": True, "failed": 1},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        failed = any("TESTS_FAILED" in f.code for f in report.findings)
        assert failed
        assert any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
    
    def test_smoke_summary_failed_returns_blocker(self, tmp_path):
        """Test que smoke_summary failed > 0 devuelve blocker."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-16",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True, "no_open": True, "no_subprocess": True, "no_faiss": True, "no_add_memory": True, "no_allow_real_write_true": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 1},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        failed = any("SMOKES_FAILED" in f.code for f in report.findings)
        assert failed
        assert any(f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in report.findings)
    
    def test_complete_valid_bundle_returns_accepted(self, tmp_path):
        """Test que bundle completo válido devuelve ACCEPTED."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-17",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {
                "verified": True, "pending_commits_vs_origin": 0, "staged_files": [],
                "memory_semantic_in_commit": False, "tmp_agent_strategies_in_commit": False,
                "nul_in_commit": False, "runtime_active": False,
            },
            "risk_summary": {
                "verified": True, "unresolved_high_risk_count": 0,
                "unresolved_write_like_count": 0, "unresolved_runtime_like_count": 0,
            },
            "security_validation": {
                "verified": True, "no_open": True, "no_subprocess": True, "no_faiss": True,
                "no_requests_httpx": True, "no_semantic_memory_bridge": True, "no_add_memory": True,
                "no_write_ops": True, "no_delete_ops": True, "no_move_ops": True,
                "no_allow_real_write_true": True,
            },
            "test_summary": {
                "verified": True, "failed": 0, "passed": 33,
                "decision_gate_tests_passed": True,
                "p2e_regression_tests_passed": True,
            },
            "smoke_summary": {
                "verified": True, "failed": 0, "passed": 10,
                "decision_gate_smoke_ok": True,
                "p2e_regression_smokes_ok": True,
            },
        }
        
        report = contract.validate_bundle_read_only(bundle)
        assert report.status == SemanticMemoryEvidenceStatus.ACCEPTED
        assert report.accepted_for_decision_gate is True
    
    def test_can_execute_real_write_always_false(self, tmp_path):
        """Test que can_execute_real_write siempre es False."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-18",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True, "no_open": True, "no_subprocess": True, "no_faiss": True, "no_add_memory": True, "no_allow_real_write_true": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        assert report.can_execute_real_write is False
    
    def test_allow_real_write_always_false(self, tmp_path):
        """Test que allow_real_write siempre es False."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-19",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True, "no_open": True, "no_subprocess": True, "no_faiss": True, "no_add_memory": True, "no_allow_real_write_true": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self, tmp_path):
        """Test que dry_run_only siempre es True."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=tmp_path)
        
        bundle = {
            "bundle_id": "test-20",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": str(tmp_path),
            "branch": "main",
            "head_hash": "abc123",
            "git_state": {"verified": True, "pending_commits_vs_origin": 0, "staged_files": []},
            "risk_summary": {"verified": True, "unresolved_high_risk_count": 0},
            "security_validation": {"verified": True, "no_open": True, "no_subprocess": True, "no_faiss": True, "no_add_memory": True, "no_allow_real_write_true": True},
            "test_summary": {"verified": True, "failed": 0},
            "smoke_summary": {"verified": True, "failed": 0},
        }
        
        report = contract.validate_bundle_read_only(bundle)
        assert report.dry_run_only is True
    
    def test_block_evidence_keeps_allow_real_write_false(self):
        """Test que block_evidence mantiene allow_real_write=False."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=".")
        report = contract.block_evidence("Test block")
        
        assert report.allow_real_write is False
        assert report.status == SemanticMemoryEvidenceStatus.REJECTED
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize_contract devuelve allow_real_write=False."""
        contract = SemanticMemoryExternalEvidenceContract(repo_root=".")
        summary = contract.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True
        assert summary["can_execute_real_write"] is False
    
    def test_no_subprocess_in_module(self):
        """Test que el módulo no importa subprocess."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess", "subprocess import found"
            if isinstance(node, ast.ImportFrom):
                assert node.module != "subprocess", "subprocess import found"
    
    def test_no_open_in_productive_code(self):
        """Test que el módulo no usa open()."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "open", f"open() call found at line {node.lineno}"
    
    def test_no_copy_in_productive_code(self):
        """Test que el módulo no usa .copy()."""
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        
        assert ".copy(" not in content, ".copy() call found in productive code"
    
    def test_no_write_text_in_productive_code(self):
        """Test que el módulo no usa write_text."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "write_text", f"write_text() call found at line {node.lineno}"
    
    def test_no_unlink_in_productive_code(self):
        """Test que el módulo no usa unlink."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "unlink", f"unlink() call found at line {node.lineno}"
    
    def test_no_shutil_in_productive_code(self):
        """Test que el módulo no importa shutil."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "shutil", "shutil import found"
    
    def test_no_faiss_import_in_productive_code(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "faiss", "faiss import found"
    
    def test_no_requests_import_in_productive_code(self):
        """Test que el módulo no importa requests."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "requests", "requests import found"
    
    def test_no_semantic_memory_bridge_import_in_productive_code(self):
        """Test que el módulo no importa semantic_memory_bridge."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "semantic_memory_bridge" not in (node.module or ""), "semantic_memory_bridge import found"
    
    def test_no_add_memory_in_productive_code(self):
        """Test que el módulo no llama add_memory."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "add_memory", f"add_memory call found at line {node.lineno}"
    
    def test_no_promote_real_in_productive_code(self):
        """Test que el módulo no define promote_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "promote_real", "promote_real function found"
    
    def test_no_execute_rollback_real_in_productive_code(self):
        """Test que el módulo no define execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "execute_rollback_real", "execute_rollback_real function found"
    
    def test_no_allow_real_write_true_in_productive_code(self):
        """Test que el módulo no tiene allow_real_write=True."""
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_external_evidence_contract.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        
        assert "allow_real_write = True" not in content, "allow_real_write=True found"
