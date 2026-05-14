"""
Tests for AutoTickLoop — brain/auto_tick_loop.py
33 tests covering start/stop/pause/resume, force_tick, _process_tick_result,
notification management, TickNotification, get_status, MAX_NOTIFICATIONS, and edge cases.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch

from brain.auto_tick_loop import (
    AutoTickLoop,
    TickNotification,
    NotificationType,
    get_auto_tick_loop,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def loop():
    return AutoTickLoop(interval=0.1)


@pytest.fixture
def mock_orchestrator():
    orch = Mock()
    orch.tick = AsyncMock(return_value={
        "new_goals": [],
        "biases_detected": {},
        "signals": {
            "stress_level": 0.3,
            "resilience_mode": "normal",
            "knowledge_gap_count": 2,
            "capability_unreliable_pct": 0.1,
        },
    })
    return orch


# ─── NotificationType enum ───────────────────────────────────────────────────

class TestNotificationType:
    def test_new_goal(self):
        assert NotificationType.NEW_GOAL.value == "new_goal"

    def test_bias_detected(self):
        assert NotificationType.BIAS_DETECTED.value == "bias_detected"

    def test_capability_failed(self):
        assert NotificationType.CAPABILITY_FAILED.value == "capability_failed"

    def test_stress_high(self):
        assert NotificationType.STRESS_HIGH.value == "stress_high"

    def test_gap_discovered(self):
        assert NotificationType.GAP_DISCOVERED.value == "gap_discovered"

    def test_tick_complete(self):
        assert NotificationType.TICK_COMPLETE.value == "tick_complete"

    def test_all_types_count(self):
        assert len(NotificationType) == 6


# ─── TickNotification ────────────────────────────────────────────────────────

class TestTickNotification:
    def test_creation(self):
        notif = TickNotification(
            notification_type=NotificationType.NEW_GOAL,
            message="New goal created",
        )
        assert notif.notification_type == NotificationType.NEW_GOAL
        assert notif.message == "New goal created"
        assert notif.read is False

    def test_default_values(self):
        notif = TickNotification(
            notification_type=NotificationType.TICK_COMPLETE,
            message="Done",
        )
        assert notif.data == {}
        assert notif.read is False
        assert notif.timestamp > 0

    def test_custom_data(self):
        notif = TickNotification(
            notification_type=NotificationType.BIAS_DETECTED,
            message="Bias found",
            data={"bias_type": "confirmation"},
        )
        assert notif.data["bias_type"] == "confirmation"


# ─── Start / Stop / Pause / Resume ───────────────────────────────────────────

class TestStartStopPauseResume:
    @pytest.mark.asyncio
    async def test_start(self, loop):
        await loop.start()
        assert loop.running is True
        await loop.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, loop):
        await loop.start()
        await loop.start()  # Should not create another task
        assert loop.running is True
        await loop.stop()

    @pytest.mark.asyncio
    async def test_stop(self, loop):
        await loop.start()
        await loop.stop()
        assert loop.running is False
        assert loop.paused is False

    @pytest.mark.asyncio
    async def test_pause(self, loop):
        loop.paused = False
        await loop.pause()
        assert loop.paused is True

    @pytest.mark.asyncio
    async def test_resume(self, loop):
        loop.paused = True
        await loop.resume()
        assert loop.paused is False

    @pytest.mark.asyncio
    async def test_start_stop_cycle(self, loop):
        await loop.start()
        assert loop.running is True
        await loop.stop()
        assert loop.running is False
        # Can restart
        await loop.start()
        assert loop.running is True
        await loop.stop()


# ─── force_tick() ─────────────────────────────────────────────────────────────

class TestForceTick:
    @pytest.mark.asyncio
    async def test_force_tick_with_orchestrator(self, loop, mock_orchestrator):
        loop.set_orchestrator(mock_orchestrator)
        result = await loop.force_tick()
        assert isinstance(result, dict)
        mock_orchestrator.tick.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_tick_no_orchestrator(self, loop):
        result = await loop.force_tick()
        assert result == {"error": "orchestrator_not_set"}

    @pytest.mark.asyncio
    async def test_force_tick_increments_count(self, loop, mock_orchestrator):
        loop.set_orchestrator(mock_orchestrator)
        await loop.force_tick()
        assert loop.tick_count == 1

    @pytest.mark.asyncio
    async def test_force_tick_updates_last_tick_time(self, loop, mock_orchestrator):
        loop.set_orchestrator(mock_orchestrator)
        before = time.time()
        await loop.force_tick()
        assert loop.last_tick_time >= before

    @pytest.mark.asyncio
    async def test_force_tick_error_handling(self, loop):
        orch = Mock()
        orch.tick = AsyncMock(side_effect=RuntimeError("boom"))
        loop.set_orchestrator(orch)
        result = await loop.force_tick()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_force_tick_error_adds_notification(self, loop):
        orch = Mock()
        orch.tick = AsyncMock(side_effect=RuntimeError("boom"))
        loop.set_orchestrator(orch)
        await loop.force_tick()
        assert len(loop.notifications) > 0


# ─── _process_tick_result() — notification types ─────────────────────────────

class TestProcessTickResult:
    def test_new_goals_notification(self, loop):
        result = {"new_goals": ["goal1", "goal2"]}
        loop._process_tick_result(result)
        assert any(n.notification_type == NotificationType.NEW_GOAL for n in loop.notifications)

    def test_bias_detected_notification(self, loop):
        result = {"biases_detected": {"biases": ["confirmation_bias"]}}
        loop._process_tick_result(result)
        assert any(n.notification_type == NotificationType.BIAS_DETECTED for n in loop.notifications)

    def test_stress_high_notification(self, loop):
        result = {"signals": {"stress_level": 0.8, "resilience_mode": "degraded",
                               "knowledge_gap_count": 1, "capability_unreliable_pct": 0.1}}
        loop._process_tick_result(result)
        assert any(n.notification_type == NotificationType.STRESS_HIGH for n in loop.notifications)

    def test_stress_normal_no_notification(self, loop):
        result = {"signals": {"stress_level": 0.3, "resilience_mode": "normal",
                               "knowledge_gap_count": 1, "capability_unreliable_pct": 0.1}}
        loop._process_tick_result(result)
        assert not any(n.notification_type == NotificationType.STRESS_HIGH for n in loop.notifications)

    def test_gap_discovered_notification(self, loop):
        result = {"signals": {"stress_level": 0.3, "resilience_mode": "normal",
                               "knowledge_gap_count": 8, "capability_unreliable_pct": 0.1}}
        loop._process_tick_result(result)
        assert any(n.notification_type == NotificationType.GAP_DISCOVERED for n in loop.notifications)

    def test_few_gaps_no_notification(self, loop):
        result = {"signals": {"stress_level": 0.3, "resilience_mode": "normal",
                               "knowledge_gap_count": 3, "capability_unreliable_pct": 0.1}}
        loop._process_tick_result(result)
        assert not any(n.notification_type == NotificationType.GAP_DISCOVERED for n in loop.notifications)

    def test_capability_failed_notification(self, loop):
        result = {"signals": {"stress_level": 0.3, "resilience_mode": "normal",
                               "knowledge_gap_count": 1, "capability_unreliable_pct": 0.6}}
        loop._process_tick_result(result)
        assert any(n.notification_type == NotificationType.CAPABILITY_FAILED for n in loop.notifications)

    def test_capability_ok_no_notification(self, loop):
        result = {"signals": {"stress_level": 0.3, "resilience_mode": "normal",
                               "knowledge_gap_count": 1, "capability_unreliable_pct": 0.3}}
        loop._process_tick_result(result)
        assert not any(n.notification_type == NotificationType.CAPABILITY_FAILED for n in loop.notifications)

    def test_empty_result_no_notifications(self, loop):
        result = {}
        loop._process_tick_result(result)
        assert len(loop.notifications) == 0

    def test_multiple_notifications(self, loop):
        result = {
            "new_goals": ["g1"],
            "biases_detected": {"biases": ["b1"]},
            "signals": {"stress_level": 0.9, "resilience_mode": "critical",
                         "knowledge_gap_count": 10, "capability_unreliable_pct": 0.8},
        }
        loop._process_tick_result(result)
        types = {n.notification_type for n in loop.notifications}
        assert NotificationType.NEW_GOAL in types
        assert NotificationType.BIAS_DETECTED in types
        assert NotificationType.STRESS_HIGH in types
        assert NotificationType.GAP_DISCOVERED in types
        assert NotificationType.CAPABILITY_FAILED in types


# ─── Notification management ─────────────────────────────────────────────────

class TestNotificationManagement:
    def test_get_notifications(self, loop):
        loop.notifications = [
            TickNotification(NotificationType.NEW_GOAL, "g1"),
            TickNotification(NotificationType.BIAS_DETECTED, "b1"),
        ]
        notifs = loop.get_notifications()
        assert len(notifs) == 2

    def test_get_notifications_marks_read(self, loop):
        loop.notifications = [
            TickNotification(NotificationType.NEW_GOAL, "g1"),
        ]
        loop.get_notifications()
        assert loop.notifications[0].read is True

    def test_get_notifications_unread_only(self, loop):
        read_notif = TickNotification(NotificationType.NEW_GOAL, "read")
        read_notif.read = True
        unread_notif = TickNotification(NotificationType.BIAS_DETECTED, "unread")
        loop.notifications = [read_notif, unread_notif]
        notifs = loop.get_notifications(unread_only=True)
        assert len(notifs) == 1

    def test_get_notifications_limited_to_50(self, loop):
        loop.notifications = [
            TickNotification(NotificationType.NEW_GOAL, f"n{i}")
            for i in range(60)
        ]
        notifs = loop.get_notifications()
        assert len(notifs) == 50


# ─── get_status() ────────────────────────────────────────────────────────────

class TestGetStatus:
    def test_status_initial(self, loop):
        status = loop.get_status()
        assert status["running"] is False
        assert status["paused"] is False
        assert status["tick_count"] == 0
        assert status["notifications_count"] == 0
        assert status["unread_count"] == 0

    def test_status_with_notifications(self, loop):
        loop.notifications = [
            TickNotification(NotificationType.NEW_GOAL, "g1"),
            TickNotification(NotificationType.BIAS_DETECTED, "b1"),
        ]
        status = loop.get_status()
        assert status["notifications_count"] == 2
        assert status["unread_count"] == 2

    def test_status_with_read_notifications(self, loop):
        notif = TickNotification(NotificationType.NEW_GOAL, "g1")
        notif.read = True
        loop.notifications = [notif]
        status = loop.get_status()
        assert status["unread_count"] == 0


# ─── MAX_NOTIFICATIONS limit ─────────────────────────────────────────────────

class TestMaxNotifications:
    def test_max_notifications_constant(self):
        assert AutoTickLoop.MAX_NOTIFICATIONS == 100

    def test_notifications_trimmed_at_limit(self, loop):
        # Add more than MAX_NOTIFICATIONS
        for i in range(110):
            loop._add_notification(NotificationType.TICK_COMPLETE, f"msg_{i}")
        assert len(loop.notifications) <= AutoTickLoop.MAX_NOTIFICATIONS

    def test_notifications_keeps_recent(self, loop):
        for i in range(110):
            loop._add_notification(NotificationType.TICK_COMPLETE, f"msg_{i}")
        # The oldest should be trimmed
        first_msg = loop.notifications[0].message
        assert first_msg != "msg_0"


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_no_orchestrator_force_tick(self, loop):
        result = await loop.force_tick()
        assert result == {"error": "orchestrator_not_set"}

    @pytest.mark.asyncio
    async def test_tick_error_creates_notification(self, loop):
        orch = Mock()
        orch.tick = AsyncMock(side_effect=Exception("fail"))
        loop.set_orchestrator(orch)
        await loop.force_tick()
        assert len(loop.notifications) > 0
        assert loop.notifications[0].notification_type == NotificationType.TICK_COMPLETE

    def test_set_orchestrator(self, loop, mock_orchestrator):
        loop.set_orchestrator(mock_orchestrator)
        assert loop._orchestrator is mock_orchestrator

    def test_default_interval(self):
        loop = AutoTickLoop()
        assert loop.interval == AutoTickLoop.DEFAULT_INTERVAL

    def test_custom_interval(self):
        loop = AutoTickLoop(interval=30.0)
        assert loop.interval == 30.0


# ─── get_auto_tick_loop() singleton ──────────────────────────────────────────

class TestGetAutoTickLoop:
    def test_returns_instance(self):
        import brain.auto_tick_loop as mod
        mod._loop = None
        lp = get_auto_tick_loop()
        assert isinstance(lp, AutoTickLoop)

    def test_singleton(self):
        import brain.auto_tick_loop as mod
        mod._loop = None
        lp1 = get_auto_tick_loop()
        lp2 = get_auto_tick_loop()
        assert lp1 is lp2

    def test_custom_interval(self):
        import brain.auto_tick_loop as mod
        mod._loop = None
        lp = get_auto_tick_loop(interval=120.0)
        assert lp.interval == 120.0
