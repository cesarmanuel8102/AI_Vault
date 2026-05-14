# DashboardReader

> **Module Path:** `brain/readers/dashboard_reader.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The DashboardReader is a consolidated analysis engine that reads data from six distinct dashboard endpoints and synthesizes the results into a single, coherent health and status report for the AI_Vault brain system. Rather than requiring a user or subsystem to query each endpoint individually and manually correlate the results, the DashboardReader performs all six queries in parallel, normalizes the responses, detects cross-endpoint anomalies and correlations, and produces a unified analysis.

This module is critical for operational visibility. When a user asks "How is the system doing?" or when the AutoTickLoop detects a potential issue, the DashboardReader provides the definitive answer by aggregating data across all subsystems. It can identify problems that are only visible when multiple endpoints are considered together — for example, a healthy `/health` endpoint combined with a degraded `/brain/health` endpoint might indicate that the core server is fine but the brain subsystem is under stress.

The reader also supports historical comparison, allowing callers to compare the current dashboard state against a previous snapshot to detect trends, regressions, or improvements. This is particularly useful for the PhaseEvaluator, which uses dashboard trends as input to phase progression decisions.

---

## Architecture

The DashboardReader uses a fan-out/fan-in pattern. When `read_all()` is called, it dispatches six concurrent HTTP requests (one per endpoint), waits for all responses, and then passes the results through a consolidation pipeline.

```
read_all()
     │
     ▼
┌─────────────────────────────────┐
│     Parallel Endpoint Queries   │
│                                 │
│  ┌─────────┐  ┌──────────────┐ │
│  │ /health │  │ /brain/health│ │
│  └─────────┘  └──────────────┘ │
│  ┌──────────────┐ ┌───────────┐ │
│  │/brain/metrics│ │ /brain/rsi│ │
│  └──────────────┘ └───────────┘ │
│  ┌───────────────┐┌────────────┐│
│  │/autonomy/status││/upgrade/status│
│  └───────────────┘└────────────┘│
└────────────┬────────────────────┘
             │
             ▼
┌────────────────────┐
│  Normalization     │ ── Standardize response formats
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  Cross-Analysis    │ ── Detect correlations & anomalies
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  Report Generation │ ── Produce consolidated DashboardReport
└────────────────────┘
```

### Endpoint Descriptions

| Endpoint | Purpose | Key Data |
|---|---|---|
| `/health` | Overall system health check | Server uptime, memory usage, CPU load, disk space |
| `/brain/health` | Brain subsystem health | Module status, capability availability, error rates |
| `/brain/metrics` | Brain performance metrics | Tick frequency, response times, throughput, latency percentiles |
| `/brain/rsi` | Readiness Score Index | RSI score (0–1), contributing factors, trend direction |
| `/autonomy/status` | Autonomous operation status | Autonomy level, active goals, task queue depth, decision history |
| `/upgrade/status` | System upgrade status | Available upgrades, current version, upgrade history, compatibility |

---

## API Reference

### `DashboardReader`

```python
class DashboardReader:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 5.0,
        parallel_queries: bool = True,
        retry_count: int = 2,
    ):
        """
        Initialize the DashboardReader.

        Args:
            base_url: Base URL for the dashboard API server.
            timeout: Maximum time in seconds to wait for each endpoint response.
            parallel_queries: Whether to query endpoints concurrently.
            retry_count: Number of retries for failed endpoint queries.
        """
```

### `read_all() -> DashboardReport`

```python
def read_all(self) -> DashboardReport:
    """
    Query all six dashboard endpoints and generate a consolidated report.

    Returns:
        DashboardReport containing:
            - timestamp: str              — ISO 8601 timestamp of the report.
            - endpoint_data: dict         — Raw data from each endpoint.
            - health_summary: str         — Human-readable overall health summary.
            - anomalies: list[Anomaly]    — Detected cross-endpoint anomalies.
            - rsi_score: float            — Current Readiness Score Index.
            - recommendations: list[str]  — Actionable recommendations.
            - raw_responses: dict         — Unprocessed endpoint responses (for debugging).
    """
```

### `read_endpoint(endpoint: str) -> dict`

```python
def read_endpoint(self, endpoint: str) -> dict:
    """
    Query a single dashboard endpoint.

    Args:
        endpoint: One of the six endpoint paths (e.g., "/health", "/brain/rsi").

    Returns:
        Parsed JSON response as a dictionary.

    Raises:
        DashboardReadError: If the endpoint is unreachable after retries.
    """
```

### `compare(previous: DashboardReport) -> DashboardDiff`

```python
def compare(self, previous: DashboardReport) -> DashboardDiff:
    """
    Compare the current dashboard state against a previous snapshot.

    Args:
        previous: A previously captured DashboardReport.

    Returns:
        DashboardDiff containing:
            - changed_fields: list[str]      — Fields that changed.
            - new_anomalies: list[Anomaly]   — Anomalies not present in previous.
            - resolved_anomalies: list[Anomaly] — Anomalies that were resolved.
            - rsi_delta: float               — Change in RSI score.
            - trend: str                     — "improving", "degrading", or "stable".
    """
```

### `DashboardReport`

```python
@dataclass
class DashboardReport:
    timestamp: str
    endpoint_data: dict
    health_summary: str
    anomalies: list
    rsi_score: float
    recommendations: list
    raw_responses: dict
```

---

## Integration Points

- **UnifiedChatRouter** — When a message is classified as `DASHBOARD_ANALYSIS`, the router calls `DashboardReader.read_all()` and passes the resulting `DashboardReport` to the chat model for interpretation and response generation.

- **AutoTickLoop** — The tick loop periodically reads dashboard data to detect issues that should trigger notifications (e.g., STRESS_HIGH, CAPABILITY_FAILED). It calls `read_endpoint("/brain/rsi")` on each tick and `read_all()` when anomalies are detected.

- **PhaseEvaluator** — Uses RSI score trends from the DashboardReader as one of the inputs for phase progression decisions. A consistently high RSI over time supports advancing to the next phase.

- **SelfAwarenessInjector** — Shares the `/brain/health` and `/brain/rsi` data sources. The injector may reference cached DashboardReader data to avoid redundant queries.

- **NotificationSystem** — Anomalies detected by the DashboardReader are forwarded to the notification system, which generates alerts for the user or the AutoTickLoop.

---

## Usage Examples

### Basic Full Dashboard Read

```python
from brain.readers.dashboard_reader import DashboardReader

reader = DashboardReader(base_url="http://localhost:8000")
report = reader.read_all()

print(report.health_summary)
# "System is healthy. Brain subsystem operating at 94% efficiency.
#  RSI: 0.87 (improving). 2 active goals in progress. No pending upgrades."

print(report.rsi_score)  # 0.87
print(len(report.anomalies))  # 0
```

### Reading a Single Endpoint

```python
rsi_data = reader.read_endpoint("/brain/rsi")
print(rsi_data)
# {
#     "rsi_score": 0.87,
#     "contributing_factors": {
#         "capability_health": 0.92,
#         "goal_progress": 0.78,
#         "stress_index": 0.15,
#         "knowledge_coverage": 0.83
#     },
#     "trend": "improving",
#     "last_updated": "2025-01-15T10:30:00Z"
# }
```

### Comparing Dashboard Snapshots

```python
import time

previous_report = reader.read_all()
time.sleep(300)  # Wait 5 minutes

current_report = reader.read_all()
diff = reader.compare(previous_report)

print(diff.trend)  # "improving"
print(diff.rsi_delta)  # 0.03
print(diff.new_anomalies)  # []
print(diff.resolved_anomalies)  # [Anomaly(type="HIGH_LATENCY", ...)]
```

### Handling Endpoint Failures Gracefully

```python
reader = DashboardReader(base_url="http://unreachable-host:8000", retry_count=1)

try:
    report = reader.read_all()
except DashboardReadError as e:
    print(f"Dashboard unavailable: {e}")
    # Fall back to cached or default data
```

---

## Configuration

```yaml
dashboard_reader:
  base_url: "http://localhost:8000"  # Dashboard API base URL
  timeout: 5.0                        # Per-endpoint timeout in seconds
  parallel_queries: true               # Query all endpoints concurrently
  retry_count: 2                       # Retries per failed endpoint
  retry_delay: 1.0                     # Seconds between retries

  # Anomaly detection thresholds
  anomaly_detection:
    rsi_drop_threshold: 0.15           # Flag if RSI drops by this much between reads
    stress_spike_threshold: 30         # Flag if stress increases by this many points
    error_rate_threshold: 0.05         # Flag if error rate exceeds 5%
    latency_percentile_threshold: 2.0  # Flag if p99 latency exceeds 2x baseline

  # Report formatting
  reporting:
    max_summary_length: 500            # Max chars for health_summary
    include_raw_responses: false        # Include raw endpoint responses in report
    include_recommendations: true       # Generate actionable recommendations
    max_recommendations: 5              # Limit number of recommendations
```

### Environment Variable Overrides

| Variable | Default | Description |
|---|---|---|
| `DASHBOARD_BASE_URL` | `http://localhost:8000` | Override base URL |
| `DASHBOARD_TIMEOUT` | `5.0` | Override per-endpoint timeout |
| `DASHBOARD_PARALLEL` | `true` | Disable parallel queries |
| `DASHBOARD_RETRY_COUNT` | `2` | Override retry count |
| `DASHBOARD_LOG_LEVEL` | `INFO` | Logging verbosity |
