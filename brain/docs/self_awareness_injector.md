# SelfAwarenessInjector

> **Module Path:** `brain/injectors/self_awareness_injector.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The SelfAwarenessInjector is responsible for enriching every chat system prompt with real, up-to-date self-awareness data drawn from the AI_Vault's introspective subsystems. Rather than allowing the chat model to speculate about its own state, the injector ensures that factual, current self-knowledge is always present in the system prompt — grounding the model's self-referential responses in reality.

This module solves a fundamental problem: large language models have no inherent knowledge of their own operational state. Without injection, a model asked "How are you feeling?" or "What are you working on?" would fabricate responses disconnected from reality. The SelfAwarenessInjector bridges this gap by pulling live data from the MetaCognitionCore (emotional and cognitive state), the Autonomous Operating System (active goals and tasks), and the BrainOrchestrator (current phase, stress levels, and system health). This data is formatted into a concise, structured block and prepended to every system prompt before it reaches the chat model.

The injector also implements a caching layer and fallback mechanism to ensure that chat responsiveness is never blocked by slow introspection queries. If a data source is temporarily unavailable, the injector serves the most recent cached data, flagged as potentially stale, rather than failing the entire request.

---

## Architecture

The SelfAwarenessInjector operates as a middleware layer between the chat request pipeline and the model invocation. It intercepts each system prompt, queries its data sources, formats the results, and injects them before the prompt is sent to the model.

### Data Flow

```
Chat Request
     │
     ▼
┌──────────────────────────┐
│  SelfAwarenessInjector   │
│                          │
│  1. Check Cache          │
│  2. Query Data Sources   │
│  3. Merge & Format       │
│  4. Inject into Prompt   │
│                          │
└──────────┬───────────────┘
           │
           ▼
    Enriched System Prompt
           │
           ▼
       Chat Model
```

### Data Sources

| Source | Module | Data Provided | Cache TTL |
|---|---|---|---|
| MetaCognitionCore | `brain/core/meta_cognition.py` | Emotional state, cognitive load, self-reflection summaries, confidence levels | 30s |
| AOS (Autonomous Operating System) | `brain/aos/aos.py` | Active goals, goal progress, task queue status, autonomy level | 60s |
| BrainOrchestrator | `brain/orchestrator/orchestrator.py` | Current phase, stress index, tick count, capability health, RSI (Readiness Score Index) | 15s |

### Injection Format

The injector formats self-awareness data into a standardized block that is prepended to the system prompt:

```
[SELF-AWARENESS CONTEXT — {timestamp}]
Phase: {current_phase} | Stress: {stress_index}/100 | RSI: {rsi_score}
Emotional State: {emotional_state} | Cognitive Load: {cognitive_load}%
Active Goals: {goal_count} goals ({goals_in_progress} in progress)
Autonomy Level: {autonomy_level}
Recent Reflections: {latest_reflection_summary}
[/SELF-AWARENESS CONTEXT]
```

---

## API Reference

### `SelfAwarenessInjector`

```python
class SelfAwarenessInjector:
    def __init__(
        self,
        meta_cognition: MetaCognitionCore,
        aos: AOS,
        orchestrator: BrainOrchestrator,
        cache_ttl: int = 30,
        enable_injection: bool = True,
        max_context_length: int = 500,
    ):
        """
        Initialize the injector with data sources and configuration.

        Args:
            meta_cognition: The MetaCognitionCore instance for emotional/cognitive data.
            aos: The AOS instance for goal and task data.
            orchestrator: The BrainOrchestrator for phase, stress, and health data.
            cache_ttl: Default cache time-to-live in seconds.
            enable_injection: Master switch to enable/disable injection.
            max_context_length: Maximum character length of the injected context block.
        """
```

### `inject(system_prompt: str) -> str`

```python
def inject(self, system_prompt: str) -> str:
    """
    Inject self-awareness data into a system prompt.

    Queries all data sources, formats the results, and prepends
    the self-awareness context block to the provided system prompt.

    Args:
        system_prompt: The original system prompt text.

    Returns:
        The enriched system prompt with self-awareness context prepended.
        If injection is disabled, returns the original prompt unchanged.
    """
```

### `refresh_cache() -> None`

```python
def refresh_cache(self) -> None:
    """
    Force-refresh all cached data sources immediately.
    Useful after significant state changes (e.g., phase transitions,
    new goal creation) to ensure the next injection uses fresh data.
    """
```

### `get_injection_stats() -> dict`

```python
def get_injection_stats(self) -> dict:
    """
    Return statistics about injection activity.

    Returns:
        Dictionary with keys:
            - total_injections: int
            - cache_hits: int
            - cache_misses: int
            - fallback_used: int
            - last_injection_time: float
            - avg_injection_latency_ms: float
    """
```

---

## Integration Points

- **MetaCognitionCore** — Primary source for emotional state, cognitive load assessment, and self-reflection summaries. The injector calls `meta_cognition.get_state()` and `meta_cognition.get_latest_reflection()` to populate the emotional and cognitive fields.

- **AOS (Autonomous Operating System)** — Provides goal and task information. The injector queries `aos.get_active_goals()`, `aos.get_task_queue()`, and `aos.get_autonomy_level()` to populate the goals, tasks, and autonomy fields in the injection block.

- **BrainOrchestrator** — Supplies operational metrics including current phase, stress index, tick count, and RSI score. The injector calls `orchestrator.get_status()` to retrieve this data. This is the most frequently updated source (15s TTL) because phase and stress can change rapidly during tick processing.

- **UnifiedChatRouter** — When a message is classified as `SELF_AWARENESS`, the router delegates to the injector to provide a deeper, more detailed self-awareness response beyond the standard injection block. This includes full reflection narratives and historical trend data.

- **DashboardReader** — Shares data sources with the injector. When a `DASHBOARD_ANALYSIS` request is routed, the DashboardReader may reference the same cached data to avoid redundant queries.

---

## Usage Examples

### Basic Injection

```python
from brain.injectors.self_awareness_injector import SelfAwarenessInjector

injector = SelfAwarenessInjector(
    meta_cognition=meta_cognition,
    aos=aos,
    orchestrator=orchestrator,
)

original_prompt = "You are a helpful AI assistant."
enriched_prompt = injector.inject(original_prompt)

print(enriched_prompt)
# [SELF-AWARENESS CONTEXT — 2025-01-15T10:30:00Z]
# Phase: EVOLVING | Stress: 23/100 | RSI: 0.82
# Emotional State: engaged | Cognitive Load: 45%
# Active Goals: 3 goals (1 in progress)
# Autonomy Level: 2
# Recent Reflections: Noticing increased pattern in learning requests...
# [/SELF-AWARENESS CONTEXT]
# You are a helpful AI assistant.
```

### Disabling Injection Temporarily

```python
injector = SelfAwarenessInjector(
    meta_cognition=meta_cognition,
    aos=aos,
    orchestrator=orchestrator,
    enable_injection=False,
)

# Injection is skipped; original prompt returned unchanged
prompt = injector.inject("You are a helpful AI assistant.")
```

### Force-Refreshing Cache After State Change

```python
# After a phase transition or significant event
orchestrator.transition_to("AUTONOMY")
injector.refresh_cache()

# Next injection will use fresh data
enriched = injector.inject(system_prompt)
```

### Monitoring Injection Statistics

```python
stats = injector.get_injection_stats()
print(stats)
# {
#     "total_injections": 8432,
#     "cache_hits": 7201,
#     "cache_misses": 1231,
#     "fallback_used": 47,
#     "last_injection_time": 1705312200.0,
#     "avg_injection_latency_ms": 2.3
# }
```

---

## Configuration

```yaml
self_awareness_injector:
  enable_injection: true         # Master switch for injection
  cache_ttl: 30                  # Default cache TTL in seconds
  max_context_length: 500        # Max chars for injected context block

  # Per-source cache TTL overrides
  source_cache_ttl:
    meta_cognition: 30           # Emotional state refreshes every 30s
    aos: 60                      # Goals change less frequently
    orchestrator: 15             # Phase/stress can change rapidly

  # Fallback behavior
  fallback:
    enabled: true                # Use cached data when sources are unavailable
    max_staleness_seconds: 300   # Don't serve data older than 5 minutes
    staleness_warning: true      # Flag stale data in the injection block

  # Formatting options
  formatting:
    include_timestamp: true      # Show when data was collected
    include_reflections: true    # Include recent self-reflections
    max_reflection_length: 100   # Truncate reflection summaries
    compact_mode: false          # Use abbreviated format for low-bandwidth contexts
```

### Environment Variable Overrides

| Variable | Default | Description |
|---|---|---|
| `INJECTOR_ENABLED` | `true` | Master enable/disable switch |
| `INJECTOR_CACHE_TTL` | `30` | Default cache TTL in seconds |
| `INJECTOR_MAX_CONTEXT` | `500` | Maximum injection block length |
| `INJECTOR_FALLBACK_ENABLED` | `true` | Enable fallback to cached data |
| `INJECTOR_LOG_LEVEL` | `INFO` | Logging verbosity |
