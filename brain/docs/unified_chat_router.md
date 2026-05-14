# UnifiedChatRouter

> **Module Path:** `brain/routers/unified_chat_router.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The UnifiedChatRouter is the central intent classification and routing engine for the AI_Vault brain system. Every incoming user message passes through this router before being dispatched to the appropriate brain subsystem. Its primary responsibility is to analyze the semantic content of a user's message, classify it into one of six well-defined intent categories, and route it to the correct handler with all necessary context attached.

Without the UnifiedChatRouter, the brain would have no principled way to decide which subsystem should handle a given request. This would lead to ambiguous dispatching, missed intents, and inconsistent user experiences. The router ensures that casual conversation, deep self-reflection, dashboard analysis, learning requests, goal management, and agent tasks are each handled by the subsystem specifically designed for them. It acts as the brain's "prefrontal cortex" — making rapid, context-aware decisions about message flow before deeper processing occurs.

The router also plays a critical role in observability. Every classification decision is logged with confidence scores, enabling downstream analysis of routing accuracy and intent distribution over time. This data feeds back into the self-awareness loop, allowing the system to detect when certain intent categories are being under-served or mis-routed.

---

## Architecture

The UnifiedChatRouter follows a pipeline architecture consisting of three sequential stages: **Preprocessing**, **Classification**, and **Dispatch**. Each stage is isolated and independently testable, allowing for targeted improvements without affecting the entire pipeline.

### Preprocessing Stage

Incoming raw messages are normalized before classification. This includes trimming whitespace, collapsing repeated punctuation, lowercasing for pattern matching (while preserving the original casing for downstream use), and extracting any embedded commands or mentions (e.g., `@dashboard`, `#goal`). The preprocessor also attaches conversation context — the last N messages from the session — which the classifier can use to resolve ambiguous intents.

### Classification Stage

The classifier uses a hybrid approach combining rule-based heuristics with semantic similarity scoring. Rule-based patterns handle high-confidence, unambiguous cases (e.g., messages starting with "analyze dashboard" are always `DASHBOARD_ANALYSIS`). For ambiguous cases, the system computes semantic similarity between the message and representative embeddings for each intent category, selecting the category with the highest confidence score above a minimum threshold.

### Intent Categories

| Category | Description | Example Triggers |
|---|---|---|
| `GENERAL_CONVERSATION` | Casual chat, greetings, off-topic remarks | "Hey, how are you?", "What's up?" |
| `SELF_AWARENESS` | Questions about the system's own state, feelings, or identity | "How are you feeling?", "What are you aware of?" |
| `DASHBOARD_ANALYSIS` | Requests to read, interpret, or act on dashboard data | "Show me the health report", "Analyze my metrics" |
| `LEARNING_REQUEST` | Explicit or implicit requests to learn, study, or acquire new knowledge | "Learn about quantum computing", "Teach me Rust" |
| `GOAL_MANAGEMENT` | Creating, updating, reviewing, or deleting goals | "Set a goal to read more", "What are my goals?" |
| `AGENT_TASK` | Delegating work to autonomous agents or task runners | "Run the scraper", "Deploy the update" |

### Dispatch Stage

Once classified, the message is dispatched to the corresponding handler. Each handler receives the original message, the classified intent, the confidence score, and the attached conversation context. If the confidence score falls below the configurable `min_confidence` threshold, the message is routed to `GENERAL_CONVERSATION` as a safe fallback.

```
User Message
     │
     ▼
┌──────────────┐
│ Preprocessor │ ── Normalize, extract context
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Classifier  │ ── Rules + Semantic Similarity
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Dispatcher │ ── Route to handler
└──────────────┘
```

---

## API Reference

### `UnifiedChatRouter`

```python
class UnifiedChatRouter:
    def __init__(
        self,
        min_confidence: float = 0.6,
        context_window: int = 5,
        enable_semantic: bool = True,
    ):
        """
        Initialize the router.

        Args:
            min_confidence: Minimum confidence score to accept a classification.
                            Below this, the message falls back to GENERAL_CONVERSATION.
            context_window: Number of previous messages to include as context.
            enable_semantic: Whether to use semantic similarity for ambiguous cases.
        """
```

### `route(message: str, session_id: str) -> RoutingResult`

```python
def route(self, message: str, session_id: str) -> RoutingResult:
    """
    Classify and route a user message.

    Args:
        message: The raw user message text.
        session_id: The current session identifier for context retrieval.

    Returns:
        RoutingResult containing:
            - intent: str           — The classified intent category.
            - confidence: float     — Confidence score (0.0–1.0).
            - handler: Callable     — The resolved handler function.
            - context: list[str]    — Attached conversation context.
            - metadata: dict        — Additional routing metadata.

    Raises:
        RoutingError: If classification fails entirely.
    """
```

### `RoutingResult`

```python
@dataclass
class RoutingResult:
    intent: str
    confidence: float
    handler: Callable
    context: list[str]
    metadata: dict
```

### `get_routing_stats() -> dict`

```python
def get_routing_stats(self) -> dict:
    """
    Return aggregate routing statistics since last reset.

    Returns:
        Dictionary with keys:
            - total_routed: int
            - by_intent: dict[str, int]
            - avg_confidence: float
            - low_confidence_count: int
    """
```

---

## Integration Points

The UnifiedChatRouter integrates with several core brain subsystems:

- **SelfAwarenessInjector** — When a message is classified as `SELF_AWARENESS`, the router passes control to the injector, which enriches the response with real-time self-awareness data from MetaCognitionCore, AOS, and the Orchestrator.

- **DashboardReader** — Messages classified as `DASHBOARD_ANALYSIS` are forwarded to the DashboardReader, which fetches live data from the six dashboard endpoints and generates a consolidated analysis report.

- **LearningValidator** — `LEARNING_REQUEST` messages are handed off to the learning pipeline, where the LearningValidator assesses whether the requested knowledge has been genuinely acquired.

- **GoalManager (AOS)** — `GOAL_MANAGEMENT` messages are routed to the Autonomous Operating System's goal manager, which handles CRUD operations on goals and returns status updates.

- **AgentTaskRunner** — `AGENT_TASK` messages are dispatched to the task runner, which executes autonomous agent workflows and returns task status.

- **ConversationLogger** — Every routing decision is logged, regardless of category, ensuring a complete audit trail of intent classifications and confidence scores over time.

---

## Usage Examples

### Basic Routing

```python
from brain.routers.unified_chat_router import UnifiedChatRouter

router = UnifiedChatRouter(min_confidence=0.6)

result = router.route("How are you feeling today?", session_id="sess_abc123")
print(result.intent)       # "SELF_AWARENESS"
print(result.confidence)   # 0.92
```

### Dashboard Analysis Request

```python
result = router.route("Analyze the dashboard and tell me what's wrong", session_id="sess_abc123")
print(result.intent)       # "DASHBOARD_ANALYSIS"
print(result.confidence)   # 0.88

# Access the handler directly
analysis = result.handler(result.context)
print(analysis.summary)
```

### Goal Management

```python
result = router.route("I want to set a goal to exercise 3 times a week", session_id="sess_abc123")
print(result.intent)       # "GOAL_MANAGEMENT"
```

### Low Confidence Fallback

```python
result = router.route("hmm maybe", session_id="sess_abc123")
print(result.intent)       # "GENERAL_CONVERSATION"  (fallback)
print(result.confidence)   # 0.35  (below threshold)
```

### Checking Routing Statistics

```python
stats = router.get_routing_stats()
print(stats)
# {
#     "total_routed": 1247,
#     "by_intent": {
#         "GENERAL_CONVERSATION": 412,
#         "SELF_AWARENESS": 198,
#         "DASHBOARD_ANALYSIS": 156,
#         "LEARNING_REQUEST": 231,
#         "GOAL_MANAGEMENT": 167,
#         "AGENT_TASK": 83
#     },
#     "avg_confidence": 0.81,
#     "low_confidence_count": 94
# }
```

---

## Configuration

The UnifiedChatRouter is configured through the `brain/config/router.yaml` file or via constructor arguments. Below are all configurable options with their defaults and descriptions.

```yaml
unified_chat_router:
  min_confidence: 0.6          # Minimum confidence to accept classification
  context_window: 5            # Number of previous messages for context
  enable_semantic: true        # Use semantic similarity for ambiguous cases
  semantic_model: "all-MiniLM-L6-v2"  # Embedding model for similarity
  fallback_intent: "GENERAL_CONVERSATION"  # Intent when confidence is low
  log_all_routes: true         # Log every routing decision
  cache_classifications: true  # Cache results for identical messages
  cache_ttl_seconds: 300       # Time-to-live for cached classifications

  # Per-intent rule patterns (extendable)
  intent_rules:
    SELF_AWARENESS:
      - "how are you feeling"
      - "what are you aware of"
      - "describe your state"
    DASHBOARD_ANALYSIS:
      - "analyze dashboard"
      - "show health"
      - "check metrics"
    LEARNING_REQUEST:
      - "learn about"
      - "teach me"
      - "study"
    GOAL_MANAGEMENT:
      - "set a goal"
      - "my goals"
      - "update goal"
    AGENT_TASK:
      - "run agent"
      - "execute task"
      - "deploy"
```

### Environment Variable Overrides

| Variable | Default | Description |
|---|---|---|
| `ROUTER_MIN_CONFIDENCE` | `0.6` | Override minimum confidence threshold |
| `ROUTER_SEMANTIC_DISABLED` | `false` | Disable semantic classification entirely |
| `ROUTER_CONTEXT_WINDOW` | `5` | Override context window size |
| `ROUTER_LOG_LEVEL` | `INFO` | Logging verbosity for routing events |
