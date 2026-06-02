"""B7-STRANGLER-02 — Behavior smoke tests for ChatMetrics post-extraction.

Minimal, fast (no disk persistence required) sanity checks that the relocated
ChatMetrics class still behaves identically to its in-session.py origin for
the most-used code paths. Persistence side effects are isolated by
monkeypatching the module-level _CHAT_METRICS_PATH onto a tmp_path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("C:/AI_VAULT/tmp_agent")))


class TestB7ChatMetricsBehaviorSmoke:
    def test_default_dict_shape(self, tmp_path, monkeypatch):
        # Force a fresh-state instance by pointing _CHAT_METRICS_PATH at empty tmp_path
        from brain_v9.core import session_chat_metrics as scm
        monkeypatch.setattr(scm, "_CHAT_METRICS_PATH", tmp_path / "chat_metrics.json")
        cm = scm.ChatMetrics()
        for key in (
            "total_conversations", "success", "failed", "routes",
            "agent_tool_calls_ok", "agent_tool_calls_fail", "avg_latency_ms",
            "errors", "validators", "routing_log",
        ):
            assert key in cm.data, f"Missing key: {key}"
        assert set(cm.data["routes"].keys()) == {"command", "fastpath", "agent", "llm"}
        assert cm.data["routes"]["command"] == 0
        assert cm.data["routes"]["fastpath"] == 0
        assert cm.data["routes"]["agent"] == 0
        assert cm.data["routes"]["llm"] == 0

    def test_record_increments_counters(self, tmp_path, monkeypatch):
        # Isolate persistence path so test does not touch real state file
        from brain_v9.core import session_chat_metrics as scm
        monkeypatch.setattr(scm, "_CHAT_METRICS_PATH", tmp_path / "chat_metrics.json")

        cm = scm.ChatMetrics()
        before = cm.data["total_conversations"]
        cm.record(route="agent", success=True, latency_ms=12.0)
        cm.record(route="llm", success=False, latency_ms=34.5, error_type="timeout")
        assert cm.data["total_conversations"] == before + 2
        assert cm.data["success"] >= 1
        assert cm.data["failed"] >= 1
        assert cm.data["routes"]["agent"] >= 1
        assert cm.data["routes"]["llm"] >= 1
        assert cm.data["errors"].get("timeout", 0) >= 1

    def test_record_validator(self, tmp_path, monkeypatch):
        from brain_v9.core import session_chat_metrics as scm
        monkeypatch.setattr(scm, "_CHAT_METRICS_PATH", tmp_path / "chat_metrics.json")
        cm = scm.ChatMetrics()
        cm.record_validator("R3.1_repeated_phrase")
        cm.record_validator("R3.1_repeated_phrase", count=2)
        assert cm.data["validators"]["R3.1_repeated_phrase"] == 3

    def test_snapshot_returns_dict(self, tmp_path, monkeypatch):
        from brain_v9.core import session_chat_metrics as scm
        monkeypatch.setattr(scm, "_CHAT_METRICS_PATH", tmp_path / "chat_metrics.json")
        cm = scm.ChatMetrics()
        cm.record(route="fastpath", success=True, latency_ms=5.0)
        snap = cm.snapshot()
        assert isinstance(snap, dict)
        assert snap.get("total_conversations", 0) >= 1

    def test_singleton_identity(self):
        from brain_v9.core.session import get_chat_metrics
        cm1 = get_chat_metrics()
        cm2 = get_chat_metrics()
        assert cm1 is cm2

    def test_soft_arbitration_classmethod_toggle(self):
        from brain_v9.core.session import ChatMetrics
        original = ChatMetrics._SOFT_ARBITRATION_ENABLED
        try:
            ChatMetrics.enable_soft_arbitration(True)
            assert ChatMetrics._SOFT_ARBITRATION_ENABLED is True
            ChatMetrics.enable_soft_arbitration(False)
            assert ChatMetrics._SOFT_ARBITRATION_ENABLED is False
        finally:
            ChatMetrics._SOFT_ARBITRATION_ENABLED = original

    def test_get_routing_stats_returns_dict_when_empty(self, tmp_path, monkeypatch):
        from brain_v9.core import session_chat_metrics as scm
        monkeypatch.setattr(scm, "_CHAT_METRICS_PATH", tmp_path / "chat_metrics.json")
        cm = scm.ChatMetrics()
        stats = cm.get_routing_stats()
        assert isinstance(stats, dict)

    def test_force_persist_writes_file(self, tmp_path, monkeypatch):
        from brain_v9.core import session_chat_metrics as scm
        path = tmp_path / "chat_metrics.json"
        monkeypatch.setattr(scm, "_CHAT_METRICS_PATH", path)
        cm = scm.ChatMetrics()
        cm.record(route="command", success=True, latency_ms=1.0)
        cm.force_persist()
        assert path.exists(), "force_persist() must write the metrics file"
