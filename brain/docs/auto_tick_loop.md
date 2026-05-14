# AutoTickLoop

> **Module Path:** `brain/loops/auto_tick_loop.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The AutoTickLoop is the heartbeat of the AI_Vault brain system. It periodically invokes `BrainOrchestrator.tick()`, which drives the entire cognitive cycle — from self-reflection and goal evaluation to learning consolidation and phase progression. Without the AutoTickLoop, the brain would be purely reactive, only processing when a user sends a message. The tick loop gives the brain an autonomous rhythm, enabling it to proactively manage its own state, detect issues, and evolve even during idle periods.

Each tick represents a single cognitive cycle. During a tick, the orchestrator evaluates current goals, checks system health, processes pending learning items, runs self-reflection routines, and updates internal metrics. The results of each tick are analyzed by the AutoTickLoop to determine whether any notifications should be generated — for example, if a new goal has been created, if a cognitive bias has been detected, if a capability has failed, if stress levels are high, or if a knowledge gap has been discovered.

The loop is designed for resilience. It handles tick failures gracefully, logs all errors without crashing, and implements configurable backoff strategies when the system is under stress. The loop can be paused, resumed, and reconfigured at runtime without restarting the entire brain system.

---

## Architecture

The AutoTickLoop runs as an asynchronous background task. It uses a configurable interval to sleep between ticks, and it supports dynamic interval adjustment based on system stress and activity levels.

```
┌─────────────────────────────────────┐
│          AutoTickLoop               │
│                                     │
│  ┌─────────┐    ┌───────────────┐  │
│  │  Sleep   │───▶│  tick() call  │  │
│  │ Interval │    └───────┬───────┘  │
│  └─────────┘            │          │
│                         ▼          │
│              ┌──────────────────┐   │
│              │ Analyze Results  │   │
│              └────────┬─────────┘   │
│                       │             │
│              ┌────────▼─────────┐   │
│              │ Emit Notifications│  │
│              └────────┬─────────┘   │
│                       │             │
│              ┌────────▼─────────┐   │
│              │ Adjust Interval  │───┘ (dynamic backoff)
│              └──────────────────┘
└─────────────────────────────────────┘
```

### Notification Types

The AutoTickLoop monitors tick results and emits notifications when specific conditions are met. These notifications are consumed by the user-facing notification system and by other brain subsystems.

| Notification Type | Trigger | Severity | Example |
|---|---|---|---|
| `NEW_GOAL` | A new goal has been created by the AOS or suggested by the system | `INFO` | "New goal created: Improve Rust knowledge" |
| `BIAS_DETECTED` | The MetaCognitionCore has detected a cognitive bias in recent reasoning | `WARNING` | "Confirmation bias detected in goal evaluation" |
| `CAPABILITY_FAILED` | A capability module reported a failure during execution | `ERROR` | "Capability 'web_scraper' failed: connection timeout" |
| `STRESS_HIGH` | The system stress index has exceeded the configured threshold | `WARNING` | "Stress index at 78/100 — consider reducing concurrent tasks" |
| `GAP_DISCOVERED` | A knowledge gap has been identified during self-reflection | `INFO` | "Knowledge gap discovered: No data on 'distributed systems consensus'" |

### Dynamic Interval Adjustment

The tick interval is not static. The AutoTickLoop adjusts the interval based on the system's current state:

- **Normal operation:** Uses the configured `base_interval` (default: 60 seconds).
- **High activity:** When the tick produces significant results (new goals, discoveries, learning), the interval is shortened to `base_interval * activity_multiplier` to be more responsive.
- **High stress:** When the stress index exceeds the threshold, the interval is lengthened to `base_interval * stress_multiplier` to reduce cognitive load.
- **Idle periods:** When consecutive ticks produce no significant results, the interval gradually increases up to `max_interval` to conserve resources.

---

## API Reference

### `AutoTickLoop`

```python
class AutoTickLoop:
    def __init__(
        self,
        orchestrator: BrainOrchestrator,
        base_interval: float = 60.0,
        max_interval: float = 300.0,
        activity_multiplier: float = 0.5,
        stress_multiplier: float = 2.0,
        stress_threshold: float = 70.0,
        enable_notifications: bool = True,
    ):
        """
        Initialize the AutoTickLoop.

        Args:
            orchestrator: The BrainOrchestrator instance whose tick() will be called.
            base_interval: Base time in seconds between ticks.
            max_interval: Maximum time in seconds between ticks (idle cap).
            activity_multiplier: Factor to reduce interval during high activity.
            stress_multiplier: Factor to increase interval during high stress.
            stress_threshold: Stress index above which stress backoff is applied.
            enable_notifications: Whether to emit notifications on tick results.
        """
```

### `start() -> None`

```python
def start(self) -> None:
    """
    Start the tick loop as a background task.
    The loop will run indefinitely until stop() is called.
    Safe to call multiple times; subsequent calls are no-ops if already running.
    """
```

### `stop() -> None`

```python
def stop(self) -> None:
    """
    Gracefully stop the tick loop.
    Waits for the current tick to complete before shutting down.
    """
```

### `pause() -> None`

```python
def pause(self) -> None:
    """
    Pause the loop without stopping it entirely.
    The loop will skip tick() calls until resume() is called.
    Useful during maintenance or known busy periods.
    """
```

### `resume() -> None`

```python
def resume(self) -> None:
    """
    Resume a paused loop.
    The next tick will execute immediately, then return to the normal interval.
    """
```

### `get_status() -> TickLoopStatus`

```python
def get_status(self) -> TickLoopStatus:
    """
    Return current loop status.

    Returns:
        TickLoopStatus containing:
            - running: bool
            - paused: bool
            - current_interval: float
            - total_ticks: int
            - last_tick_time: float
            - last_tick_duration_ms: float
            - notifications_emitted: int
    """
```

### `force_tick() -> TickResult`

```python
def force_tick(self) -> TickResult:
    """
    Force an immediate tick outside the normal schedule.
    Useful for testing or when a subsystem knows a state change has occurred
    that should be processed immediately.

    Returns:
        The TickResult from the orchestrator.tick() call.
    """
```

---

## Integration Points

- **BrainOrchestrator** — The core integration point. The AutoTickLoop calls `orchestrator.tick()` on every cycle and processes the resulting `TickResult` to determine notifications and interval adjustments.

- **NotificationSystem** — All emitted notifications (`NEW_GOAL`, `BIAS_DETECTED`, etc.) are sent to the NotificationSystem, which handles delivery to the user interface, logging, and any registered listeners.

- **DashboardReader** — The AutoTickLoop periodically reads the `/brain/rsi` endpoint to check system health and stress levels. If stress is high, it adjusts the tick interval accordingly and may emit a `STRESS_HIGH` notification.

- **SelfAwarenessInjector** — The injector's cache is force-refreshed after significant tick results (e.g., phase transitions, new goals) so that subsequent chat interactions reflect the latest state.

- **PhaseEvaluator** — Tick results are fed into the PhaseEvaluator's metrics collection system, which accumulates the data needed for phase progression decisions.

---

## Usage Examples

### Starting the Tick Loop

```python
from brain.loops.auto_tick_loop import AutoTickLoop

loop = AutoTickLoop(
    orchestrator=orchestrator,
    base_interval=60.0,
    enable_notifications=True,
)

loop.start()
print("Tick loop running in background")
```

### Pausing and Resuming

```python
# Pause during a known maintenance window
loop.pause()

# ... maintenance completes ...

loop.resume()  # Triggers an immediate tick, then resumes normal interval
```

### Forcing an Immediate Tick

```python
# After a significant external event (e.g., user sets a critical goal)
result = loop.force_tick()

print(result.notifications)
# [Notification(type="NEW_GOAL", message="New goal: Launch product by Q2")]
```

### Monitoring Loop Status

```python
status = loop.get_status()
print(status)
# TickLoopStatus(
#     running=True,
#     paused=False,
#     current_interval=45.0,  # Shortened due to high activity
#     total_ticks=1583,
#     last_tick_time=1705312200.0,
#     last_tick_duration_ms=127.5,
#     notifications_emitted=234
# )
```

### Handling Notifications

```python
from brain.loops.auto_tick_loop import NotificationType

# Register a custom notification handler
def on_notification(notification):
    if notification.type == NotificationType.BIAS_DETECTED:
        print(f"[BIAS ALERT] {notification.message}")
    elif notification.type == NotificationType.STRESS_HIGH:
        print(f"[STRESS] {notification.message}")

loop.on_notification = on_notification
```

---

## Configuration

```yaml
auto_tick_loop:
  base_interval: 60.0              # Seconds between ticks (normal operation)
  max_interval: 300.0              # Maximum interval (idle cap)
  activity_multiplier: 0.5         # Interval reduction factor during high activity
  stress_multiplier: 2.0           # Interval increase factor during high stress
  stress_threshold: 70.0           # Stress index that triggers backoff
  enable_notifications: true       # Emit notifications on tick results

  # Notification-specific configuration
  notifications:
    NEW_GOAL:
      enabled: true
      severity: "INFO"
    BIAS_DETECTED:
      enabled: true
      severity: "WARNING"
      cooldown_seconds: 300        # Don't repeat same bias notification within 5 min
    CAPABILITY_FAILED:
      enabled: true
      severity: "ERROR"
      cooldown_seconds: 60
    STRESS_HIGH:
      enabled: true
      severity: "WARNING"
      cooldown_seconds: 600
    GAP_DISCOVERED:
      enabled: true
      severity: "INFO"
      cooldown_seconds: 180

  # Tick loop endpoints (for health checks)
  endpoints:
    health_check: "/health"
    rsi_check: "/brain/rsi"
    stress_check: "/brain/metrics"

  # Error handling
  error_handling:
    max_consecutive_failures: 5    # Pause loop after this many consecutive failures
    failure_backoff: 2.0           # Multiply interval by this on each failure
    auto_resume_after_seconds: 300 # Auto-resume after pause due to failures
```

### Environment Variable Overrides

| Variable | Default | Description |
|---|---|---|
| `TICK_LOOP_BASE_INTERVAL` | `60.0` | Override base tick interval |
| `TICK_LOOP_MAX_INTERVAL` | `300.0` | Override maximum tick interval |
| `TICK_LOOP_ENABLED` | `true` | Master enable/disable for the loop |
| `TICK_LOOP_NOTIFICATIONS` | `true` | Enable/disable notification emission |
| `TICK_LOOP_LOG_LEVEL` | `INFO` | Logging verbosity |
