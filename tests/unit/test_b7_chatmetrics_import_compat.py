"""B7-STRANGLER-02 — Backward-compat import tests for ChatMetrics extraction.

After moving ChatMetrics from brain_v9/core/session.py to
brain_v9/core/session_chat_metrics.py, the legacy import surface MUST remain
intact:

    from brain_v9.core.session import ChatMetrics, get_chat_metrics, BrainSession
    from brain_v9.core.session import _GLOBAL_CHAT_METRICS  # used by main.py

In particular, the PEP 562 module __getattr__ proxy in session.py must return
the live singleton (mutated lazily by get_chat_metrics()) — not a stale None.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))


class TestB7ChatMetricsImportCompat:
    def test_legacy_imports_from_session_resolve(self):
        from brain_v9.core.session import ChatMetrics, get_chat_metrics, BrainSession  # noqa: F401
        assert callable(ChatMetrics)
        assert callable(get_chat_metrics)
        assert callable(BrainSession)

    def test_chatmetrics_is_same_object_as_new_module(self):
        from brain_v9.core.session import ChatMetrics as CM_legacy
        from brain_v9.core.session_chat_metrics import ChatMetrics as CM_new
        assert CM_legacy is CM_new, "ChatMetrics class identity must be preserved across re-export"

    def test_get_chat_metrics_is_same_function(self):
        from brain_v9.core.session import get_chat_metrics as f_legacy
        from brain_v9.core.session_chat_metrics import get_chat_metrics as f_new
        assert f_legacy is f_new

    def test_global_chat_metrics_proxy_returns_live_singleton(self):
        """main.py does `from brain_v9.core.session import _GLOBAL_CHAT_METRICS`.

        After get_chat_metrics() is called, that import must yield the live
        singleton (not None).
        """
        from brain_v9.core.session import get_chat_metrics
        cm = get_chat_metrics()
        # Re-import name AFTER lazy creation — must observe live ref via __getattr__
        from brain_v9.core.session import _GLOBAL_CHAT_METRICS
        assert _GLOBAL_CHAT_METRICS is cm
        # And it must be the same object referenced by the new module
        from brain_v9.core import session_chat_metrics as scm
        assert scm._GLOBAL_CHAT_METRICS is cm

    def test_global_chat_metrics_data_attribute_accessible(self):
        """main.py:1924 reads `_GLOBAL_CHAT_METRICS.data.get('validators', {})`."""
        from brain_v9.core.session import get_chat_metrics
        get_chat_metrics()
        from brain_v9.core.session import _GLOBAL_CHAT_METRICS
        assert _GLOBAL_CHAT_METRICS is not None
        assert hasattr(_GLOBAL_CHAT_METRICS, "data")
        assert isinstance(_GLOBAL_CHAT_METRICS.data, dict)
        assert "validators" in _GLOBAL_CHAT_METRICS.data

    def test_class_attributes_preserved(self):
        from brain_v9.core.session import ChatMetrics
        assert hasattr(ChatMetrics, "_PERSIST_EVERY")
        assert hasattr(ChatMetrics, "_SOFT_ARBITRATION_ENABLED")
        assert hasattr(ChatMetrics, "enable_soft_arbitration")
        assert ChatMetrics._SOFT_ARBITRATION_ENABLED is False

    def test_brain_session_uses_singleton(self):
        """BrainSession.__init__ binds self.chat_metrics = get_chat_metrics()."""
        from brain_v9.core.session import get_chat_metrics
        cm = get_chat_metrics()
        # We cannot easily instantiate BrainSession (heavy deps), but assert
        # the function reference inside the module module-resolves to the
        # singleton accessor we expect.
        from brain_v9.core import session as session_mod
        assert session_mod.get_chat_metrics() is cm
