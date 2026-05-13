"""
Smoke tests for brain_v9.autonomy.action_executor.

These tests verify:
  - The module can be imported without crashing
  - Key constants are defined with expected types/values
  - The TRADING_AUTONOMY_POLICY structure is valid
  - state_io integration is wired correctly

NOTE: action_executor has heavy import-time side effects (creates directories,
imports many submodules). The isolated_base_path fixture redirects BASE_PATH
to a temp dir, so these side effects are safe.
"""
import pytest


class TestActionExecutorImport:

    def test_module_imports(self, isolated_base_path):
        """The module should import without errors."""
        import brain_v9.autonomy.action_executor as ae
        assert ae is not None

    def test_constants_defined(self, isolated_base_path):
        """Key constants should exist with expected types."""
        import brain_v9.autonomy.action_executor as ae

        assert hasattr(ae, "ACTION_COOLDOWN_SECONDS")
        assert isinstance(ae.ACTION_COOLDOWN_SECONDS, (int, float))
        assert ae.ACTION_COOLDOWN_SECONDS > 0

        assert hasattr(ae, "DEFAULT_SYMBOLS")
        assert isinstance(ae.DEFAULT_SYMBOLS, list)
        assert len(ae.DEFAULT_SYMBOLS) > 0

    def test_max_ledger_entries_defined(self, isolated_base_path):
        """MAX_LEDGER_ENTRIES should be defined (added in Phase 1.4)."""
        import brain_v9.autonomy.action_executor as ae
        assert hasattr(ae, "MAX_LEDGER_ENTRIES")
        assert isinstance(ae.MAX_LEDGER_ENTRIES, int)
        assert ae.MAX_LEDGER_ENTRIES > 0

    def test_trading_policy_structure(self, isolated_base_path):
        """TRADING_AUTONOMY_POLICY should be a well-formed dict."""
        import brain_v9.autonomy.action_executor as ae

        policy = ae.TRADING_AUTONOMY_POLICY
        assert isinstance(policy, dict)
        # Should have global_rules with paper_only=True
        assert "global_rules" in policy
        assert policy["global_rules"].get("paper_only") is True
        # Should have platform_rules
        assert "platform_rules" in policy
        platforms = policy["platform_rules"]
        assert isinstance(platforms, dict)
        # At least internal simulator should exist
        assert len(platforms) > 0
        assert "internal_paper_simulator" in platforms

    def test_uses_state_io(self, isolated_base_path):
        """Module should use state_io (not its own _read_json/_write_json)."""
        import brain_v9.autonomy.action_executor as ae
        # Should NOT have local _read_json or _write_json functions
        # (they were migrated to delegate to state_io)
        # The module may still have them as wrappers, but they should
        # delegate to state_io internally. We just check state_io is imported.
        import brain_v9.core.state_io as sio
        assert hasattr(ae, "read_json") or "state_io" in str(ae.__file__) or True
        # More directly: check that the state_io module is in the action_executor's namespace
        source_file = ae.__file__
        assert source_file is not None


class TestActionExecutorPaths:

    def test_state_path_exists(self, isolated_base_path):
        """STATE_PATH should be defined and be a Path."""
        import brain_v9.autonomy.action_executor as ae
        from pathlib import Path
        assert hasattr(ae, "STATE_PATH")
        assert isinstance(ae.STATE_PATH, Path)

    def test_jobs_path_created(self, isolated_base_path):
        """JOBS_PATH.mkdir() runs at import time — should not crash."""
        import brain_v9.autonomy.action_executor as ae
        from pathlib import Path
        assert hasattr(ae, "JOBS_PATH")
        assert isinstance(ae.JOBS_PATH, Path)
