# SemanticMemoryBridge

> **Module Path:** `brain/bridges/semantic_memory_bridge.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The SemanticMemoryBridge connects the AI_Vault's FAISS-based semantic memory index to the chat subsystem, enabling the brain to retrieve and inject relevant memories into conversations based on semantic similarity rather than exact keyword matching. This bridge transforms the FAISS vector store from a standalone knowledge index into an active participant in every chat interaction, enriching responses with contextually relevant past knowledge, learned facts, and curated information.

Without this bridge, the brain's semantic memory would be an isolated island of knowledge — queryable only through direct API calls and disconnected from the conversational experience. The SemanticMemoryBridge makes semantic memory first-class: it auto-ingests validated learning, supports real-time similarity search, enriches chat prompts with retrieved context, and gracefully degrades when the FAISS index is unavailable or slow. This ensures that the chat system always benefits from the brain's accumulated knowledge without being blocked by indexing issues.

The bridge also handles the lifecycle of semantic memory entries, including automatic ingestion patterns that watch for new validated learning from the LearningValidator and new curated information from the InformationCurator, indexing them into FAISS as they become available. This keeps the semantic index fresh and comprehensive without requiring manual intervention.

---

## Architecture

The SemanticMemoryBridge operates as a bidirectional connector between the FAISS index and the chat pipeline. It ingests knowledge on one side and retrieves it on the other, with caching and fallback mechanisms ensuring reliability.

```
┌──────────────────┐         ┌──────────────────────┐         ┌──────────────┐
│  Knowledge       │         │  SemanticMemoryBridge │         │  Chat        │
│  Producers       │         │                      │         │  Subsystem   │
│                  │  Ingest │                      │ Retrieve│              │
│  LearningValidator├────────▶│  ┌──────────────┐   ├────────▶│  System      │
│  InformationCurator│        │  │ FAISS Index  │   │         │  Prompt      │
│  Manual Ingest   ├────────▶│  └──────────────┘   │         │              │
│                  │         │                      │         │              │
└──────────────────┘         │  ┌──────────────┐   │         └──────────────┘
                             │  │ Cache Layer  │   │
                             │  └──────────────┘   │
                             │                      │
                             │  ┌──────────────┐   │
                             │  │ Fallback     │   │
                             │  │ Handler      │   │
                             │  └──────────────┘   │
                             └──────────────────────┘
```

### Auto-Ingest Patterns

The bridge monitors several sources for new knowledge to index:

1. **Validated Learning** — When the LearningValidator certifies a learning claim, the bridge automatically ingests the validated knowledge into FAISS with appropriate metadata (topic, source, timestamp, validation score).

2. **Curated Information** — When the InformationCurator completes its pipeline and stores new curated entries, the bridge ingests them with classification metadata (topic, quality score, deprecation status).

3. **Manual Ingestion** — The bridge exposes an `ingest()` method for programmatic addition of entries, used by scripts, tests, and manual knowledge management operations.

### Search and Retrieval

The bridge provides semantic similarity search over the FAISS index. Given a query string, it:
1. Embeds the query using the same embedding model used for ingestion.
2. Searches the FAISS index for the top-k most similar vectors.
3. Returns the associated text entries with similarity scores and metadata.
4. Filters results by configurable minimum similarity threshold.

### Graceful Degradation

If the FAISS index is unavailable (e.g., during reindexing, after a crash, or due to resource constraints), the bridge enters degradation mode:
- **Search operations** return an empty result set with a degradation warning, rather than raising an exception.
- **Enrichment operations** return the original prompt unchanged.
- **Ingestion operations** queue entries for later ingestion when the index becomes available again.
- All degradation events are logged for monitoring and alerting.

---

## API Reference

### `SemanticMemoryBridge`

```python
class SemanticMemoryBridge:
    def __init__(
        self,
        faiss_index_path: str = "data/faiss/index",
        embedding_model: str = "all-MiniLM-L6-v2",
        min_similarity: float = 0.6,
        max_results: int = 5,
        cache_enabled: bool = True,
        cache_ttl: int = 300,
        auto_ingest: bool = True,
    ):
        """
        Initialize the SemanticMemoryBridge.

        Args:
            faiss_index_path: Path to the FAISS index directory.
            embedding_model: Name of the sentence-transformer model for embeddings.
            min_similarity: Minimum cosine similarity for search results.
            max_results: Maximum number of results returned by search.
            cache_enabled: Whether to cache search results.
            cache_ttl: Cache time-to-live in seconds.
            auto_ingest: Whether to automatically ingest from knowledge producers.
        """
```

### `search(query: str, top_k: int = None, filters: dict = None) -> list[MemoryResult]`

```python
def search(self, query: str, top_k: int = None, filters: dict = None) -> list[MemoryResult]:
    """
    Search semantic memory for entries similar to the query.

    Args:
        query: The search query text.
        top_k: Override maximum number of results (defaults to self.max_results).
        filters: Optional metadata filters (e.g., {"topic": "python", "min_score": 0.8}).

    Returns:
        List of MemoryResult objects, each containing:
            - text: str          — The retrieved memory text.
            - similarity: float  — Cosine similarity score.
            - metadata: dict     — Associated metadata (topic, source, timestamp, etc.).
            - entry_id: str      — Unique identifier for the memory entry.
    """
```

### `enrich_prompt(prompt: str, context_window: int = 3) -> str`

```python
def enrich_prompt(self, prompt: str, context_window: int = 3) -> str:
    """
    Enrich a chat prompt with relevant semantic memories.

    Searches the FAISS index for memories similar to the prompt content
    and injects the top results as contextual information.

    Args:
        prompt: The chat prompt to enrich.
        context_window: Maximum number of memories to inject.

    Returns:
        The enriched prompt with memory context prepended.
        If no relevant memories are found, returns the original prompt.
        If the bridge is in degradation mode, returns the original prompt.
    """
```

### `ingest(text: str, metadata: dict = None) -> str`

```python
def ingest(self, text: str, metadata: dict = None) -> str:
    """
    Manually ingest a text entry into the semantic memory index.

    Args:
        text: The text content to index.
        metadata: Optional metadata to associate with the entry.

    Returns:
        The unique entry_id assigned to the ingested entry.

    Raises:
        IngestionError: If the FAISS index is unavailable and queueing is disabled.
    """
```

### `get_status() -> BridgeStatus`

```python
def get_status(self) -> BridgeStatus:
    """
    Return current bridge status.

    Returns:
        BridgeStatus containing:
            - index_available: bool       — Whether the FAISS index is accessible.
            - index_size: int             — Number of entries in the index.
            - degradation_mode: bool      — Whether the bridge is degraded.
            - pending_ingestions: int     — Entries queued for later ingestion.
            - cache_hit_rate: float       — Cache hit rate (0.0–1.0).
            - last_search_latency_ms: float
    """
```

### `MemoryResult`

```python
@dataclass
class MemoryResult:
    text: str
    similarity: float
    metadata: dict
    entry_id: str
```

---

## Integration Points

- **LearningValidator** — When learning passes validation, the bridge's auto-ingest mechanism indexes the knowledge into FAISS. The validator's `ValidationResult` includes metadata that the bridge uses to enrich the FAISS entry (topic, validation score, source).

- **InformationCurator** — Curated and classified information entries are automatically ingested into the semantic index. The curator provides classification metadata (topic, quality score, deprecation status) that the bridge stores alongside the text.

- **SelfAwarenessInjector** — The injector may call `enrich_prompt()` to add relevant semantic memories to self-awareness responses, allowing the system to reference past learnings and reflections when discussing its own state.

- **UnifiedChatRouter** — For `GENERAL_CONVERSATION` and `LEARNING_REQUEST` intents, the router may use the bridge to enrich prompts with relevant prior knowledge, making responses more informed and contextually aware.

- **BrainOrchestrator** — During tick processing, the orchestrator queries the bridge to check knowledge coverage for specific topics, informing gap detection and autonomous learning decisions.

---

## Usage Examples

### Basic Semantic Search

```python
from brain.bridges.semantic_memory_bridge import SemanticMemoryBridge

bridge = SemanticMemoryBridge(faiss_index_path="data/faiss/index")

results = bridge.search("Python async programming patterns")
for result in results:
    print(f"[{result.similarity:.2f}] {result.text[:80]}...")
    print(f"  Topic: {result.metadata.get('topic', 'N/A')}")

# [0.89] Async programming in Python uses async/await syntax...
#   Topic: python
# [0.82] Event loops manage async task execution in Python...
#   Topic: python
# [0.71] JavaScript Promises are similar to Python Futures...
#   Topic: javascript
```

### Enriching a Chat Prompt

```python
original_prompt = "Explain how to implement a retry pattern in distributed systems."
enriched = bridge.enrich_prompt(original_prompt, context_window=3)

print(enriched)
# [SEMANTIC MEMORY CONTEXT]
# 1. (0.84) Circuit breaker patterns prevent cascading failures in distributed systems...
# 2. (0.79) Exponential backoff with jitter is recommended for retry strategies...
# 3. (0.72) Distributed consensus requires handling partial failures gracefully...
# [/SEMANTIC MEMORY CONTEXT]
# Explain how to implement a retry pattern in distributed systems.
```

### Manual Ingestion

```python
entry_id = bridge.ingest(
    text="The CAP theorem states that distributed systems can guarantee at most two of: "
         "Consistency, Availability, and Partition tolerance.",
    metadata={
        "topic": "distributed_systems",
        "source": "user_teaching",
        "validation_score": 0.95,
        "timestamp": "2025-01-15T10:30:00Z",
    },
)
print(f"Indexed as: {entry_id}")  # "entry_a1b2c3d4"
```

### Searching with Filters

```python
results = bridge.search(
    query="design patterns",
    top_k=10,
    filters={"topic": "software_engineering", "min_score": 0.8},
)
```

### Checking Bridge Status

```python
status = bridge.get_status()
print(status)
# BridgeStatus(
#     index_available=True,
#     index_size=4523,
#     degradation_mode=False,
#     pending_ingestions=0,
#     cache_hit_rate=0.73,
#     last_search_latency_ms=8.5,
# )
```

### Handling Degradation Gracefully

```python
# When FAISS is unavailable, search returns empty results
results = bridge.search("quantum entanglement")
if not results and bridge.get_status().degradation_mode:
    print("Semantic memory is temporarily unavailable. Using fallback context.")
```

---

## Configuration

```yaml
semantic_memory_bridge:
  faiss_index_path: "data/faiss/index"    # Path to FAISS index directory
  embedding_model: "all-MiniLM-L6-v2"     # Sentence-transformer model name
  min_similarity: 0.6                      # Minimum cosine similarity for results
  max_results: 5                           # Default max search results
  auto_ingest: true                        # Auto-ingest from knowledge producers

  # Cache configuration
  cache:
    enabled: true
    ttl: 300                               # Cache TTL in seconds
    max_size: 1000                         # Maximum cached query entries

  # Graceful degradation
  degradation:
    queue_ingestions: true                 # Queue entries when index is unavailable
    max_queue_size: 1000                   # Maximum pending ingestions
    retry_interval: 30                     # Seconds between retry attempts
    alert_on_degradation: true             # Emit alert when entering degradation mode

  # Enrichment configuration
  enrichment:
    context_window: 3                      # Number of memories to inject
    max_context_chars: 1000                # Maximum chars for injected context
    include_metadata: false                # Include metadata in enrichment block
    separator: "\n"                        # Separator between memory entries
    header: "[SEMANTIC MEMORY CONTEXT]"    # Header for enrichment block

  # Index management
  index:
    auto_reindex: false                    # Auto-reindex on corruption
    reindex_on_startup: false              # Rebuild index on bridge initialization
    backup_before_reindex: true            # Create backup before reindexing
