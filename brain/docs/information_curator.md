# InformationCurator

> **Module Path:** `brain/curators/information_curator.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The InformationCurator is the brain's full-spectrum information processing pipeline. It takes raw text and file inputs, cleans and normalizes them, removes duplicates, classifies them into one of seven topic categories, assesses their quality, detects contradictions with existing knowledge, and stores the curated results for future retrieval and use. This pipeline transforms unstructured, potentially noisy information into verified, classified, and indexed knowledge that the brain can trust and act upon.

Without the InformationCurator, the brain would be overwhelmed by raw, unfiltered information. Duplicate entries would waste storage and confuse retrieval. Unclassified information would be impossible to search efficiently. Low-quality or contradictory data would corrupt the knowledge base and lead to unreliable behavior. The curator solves all of these problems by applying a rigorous, multi-stage processing pipeline before any information enters the knowledge base.

The curator also manages the lifecycle of curated information, including deprecation of outdated entries, full-text search across the curated corpus, and statistical reporting on the health and coverage of the knowledge base. This makes it not just an ingestion pipeline, but a complete information management system that ensures the brain's knowledge remains accurate, relevant, and well-organized over time.

---

## Architecture

The InformationCurator implements a seven-stage pipeline. Each stage processes the information sequentially, and each stage can reject an entry (preventing it from reaching later stages) or flag it for special handling.

```
Raw Input (text/file)
        │
        ▼
┌─────────────┐
│   1. Clean  │ ── Normalize, strip markup, fix encoding
└──────┬──────┘
       │
       ▼
┌──────────────┐
│ 2. Deduplicate│ ── Remove exact and near-duplicates
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ 3. Classify  │ ── Assign to one of 7 topic categories
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  4. Quality  │ ── Assess information quality score
└──────┬───────┘
       │
       ▼
┌──────────────┐
│5. Contradict │ ── Detect contradictions with existing knowledge
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  6. Store    │ ── Persist curated entry to knowledge base
└──────┬───────┘
       │
       ▼
   CuratedEntry
```

### Pipeline Stages

#### Stage 1: Clean

Raw inputs are cleaned and normalized. This includes stripping HTML/markup, fixing character encoding issues, normalizing whitespace, removing boilerplate text (headers, footers, navigation elements from web scrapes), and standardizing date and number formats. The cleaner preserves the semantic content while removing presentation artifacts.

#### Stage 2: Deduplicate

Duplicate and near-duplicate entries are detected and removed. Exact duplicates are trivially identified by content hashing. Near-duplicates are detected using MinHash and locality-sensitive hashing, which catches entries that are substantively identical but differ in minor formatting or wording. When a duplicate is found, the curator retains the higher-quality version and marks the other as superseded.

#### Stage 3: Classify

Each entry is classified into one of seven topic categories using a trained classifier. The categories cover the breadth of knowledge the brain is expected to manage. The classifier also produces a confidence score; entries with low classification confidence are flagged for manual review or assigned to a general "uncategorized" bucket.

| Category ID | Category Name | Description |
|---|---|---|
| `TECH` | Technology & Engineering | Programming, systems, infrastructure, tools |
| `SCIENCE` | Science & Mathematics | Physics, chemistry, biology, math, research |
| `BUSINESS` | Business & Economics | Markets, strategy, finance, management |
| `CREATIVE` | Creative & Design | Art, writing, design, music, creativity |
| `HEALTH` | Health & Wellness | Medicine, fitness, nutrition, mental health |
| `SOCIAL` | Social & Humanities | History, philosophy, culture, society |
| `META` | Meta-Knowledge | Learning strategies, self-improvement, cognition |

#### Stage 4: Quality Assessment

Each entry receives a quality score from 0.0 to 1.0 based on criteria including source reliability, information completeness, factual grounding, and structural clarity. Entries below a configurable minimum quality threshold are rejected from the pipeline.

#### Stage 5: Contradiction Detection

The entry is compared against existing knowledge in the same topic category to detect logical contradictions. If a contradiction is found, the curator flags both entries and creates a contradiction record for resolution. Contradictions are not automatically resolved — they are surfaced for the system or user to address.

#### Stage 6: Store

Curated entries are persisted to the knowledge base with all metadata (topic, quality score, source, timestamps, contradiction flags). The store also triggers the SemanticMemoryBridge's auto-ingest mechanism, which indexes the entry into FAISS for semantic search.

---

## API Reference

### `InformationCurator`

```python
class InformationCurator:
    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        min_quality: float = 0.5,
        dedup_threshold: float = 0.85,
        classification_confidence: float = 0.6,
        enable_contradiction_detection: bool = True,
    ):
        """
        Initialize the InformationCurator.

        Args:
            knowledge_store: The KnowledgeStore instance for persisting entries.
            min_quality: Minimum quality score to accept an entry.
            dedup_threshold: Similarity threshold for near-duplicate detection.
            classification_confidence: Minimum confidence for topic classification.
            enable_contradiction_detection: Whether to run contradiction detection.
        """
```

### `curate(text: str, source: str = None, metadata: dict = None) -> CurationResult`

```python
def curate(self, text: str, source: str = None, metadata: dict = None) -> CurationResult:
    """
    Run the full curation pipeline on a text input.

    Args:
        text: Raw text content to curate.
        source: Source identifier (e.g., "web", "user", "file").
        metadata: Optional additional metadata.

    Returns:
        CurationResult containing:
            - entry: CuratedEntry or None  — The curated entry (None if rejected).
            - accepted: bool               — Whether the entry was accepted.
            - stage_results: dict          — Results from each pipeline stage.
            - rejections: list[str]        — Reasons for rejection (if any).
            - contradictions: list[dict]   — Detected contradictions (if any).
    """
```

### `curate_file(file_path: str, metadata: dict = None) -> CurationResult`

```python
def curate_file(self, file_path: str, metadata: dict = None) -> CurationResult:
    """
    Run the curation pipeline on a file input.
    Supports .txt, .md, .json, and .pdf files.

    Args:
        file_path: Path to the file to curate.
        metadata: Optional additional metadata.

    Returns:
        CurationResult (same as curate()).
    """
```

### `deprecate(entry_id: str, reason: str = None) -> bool`

```python
def deprecate(self, entry_id: str, reason: str = None) -> bool:
    """
    Mark a curated entry as deprecated.
    Deprecated entries remain in the store but are excluded from search
    and enrichment by default.

    Args:
        entry_id: The unique identifier of the entry to deprecate.
        reason: Optional reason for deprecation.

    Returns:
        True if the entry was successfully deprecated, False if not found.
    """
```

### `search(query: str, topic: str = None, include_deprecated: bool = False, limit: int = 10) -> list[CuratedEntry]`

```python
def search(self, query: str, topic: str = None, include_deprecated: bool = False, limit: int = 10) -> list[CuratedEntry]:
    """
    Search curated entries by text content and optional topic filter.

    Args:
        query: Search query text.
        topic: Optional topic category filter.
        include_deprecated: Whether to include deprecated entries.
        limit: Maximum number of results.

    Returns:
        List of matching CuratedEntry objects.
    """
```

### `get_stats() -> CurationStats`

```python
def get_stats(self) -> CurationStats:
    """
    Return statistics about the curated knowledge base.

    Returns:
        CurationStats containing:
            - total_entries: int
            - by_topic: dict[str, int]
            - avg_quality: float
            - contradiction_count: int
            - deprecated_count: int
            - dedup_savings: int         — Entries avoided due to deduplication.
    """
```

---

## Integration Points

- **SemanticMemoryBridge** — When curated entries are stored, the bridge's auto-ingest mechanism indexes them into the FAISS vector store for semantic search. The curator provides the cleaned text, topic classification, and quality score as metadata.

- **LearningValidator** — The validator may reference curated entries during the Consistency Check strategy, comparing claimed learning against the curated knowledge base to detect contradictions or confirm consistency.

- **AutoTickLoop** — During tick processing, the orchestrator may trigger the curator to process pending raw inputs (e.g., queued web scrape results or file uploads). The curator's output feeds back into the tick result.

- **UnifiedChatRouter** — For `LEARNING_REQUEST` intents, the router may first search the curated knowledge base via `curator.search()` to check if the requested knowledge already exists before initiating a new learning cycle.

- **BrainOrchestrator** — Uses curator statistics (`get_stats()`) as input for knowledge coverage assessment, which contributes to gap detection and RSI scoring.

---

## Usage Examples

### Curating Text Input

```python
from brain.curators.information_curator import InformationCurator

curator = InformationCurator(knowledge_store=store)

result = curator.curate(
    text="Python's GIL (Global Interpreter Lock) ensures that only one thread "
         "executes Python bytecode at a time, which affects CPU-bound multithreading.",
    source="user_input",
)

print(result.accepted)          # True
print(result.entry.topic)       # "TECH"
print(result.entry.quality)     # 0.88
print(result.contradictions)    # []
```

### Curating a File

```python
result = curator.curate_file(
    file_path="/data/documents/distributed_systems_notes.md",
    metadata={"course": "CS-451", "semester": "Fall 2024"},
)

print(result.accepted)  # True
print(result.entry.topic)  # "TECH"
```

### Deprecating Outdated Information

```python
# Mark an entry as outdated
success = curator.deprecate(
    entry_id="entry_xyz789",
    reason="Superseded by updated research (2025)"
)
print(success)  # True
```

### Searching the Knowledge Base

```python
results = curator.search(
    query="distributed consensus algorithms",
    topic="TECH",
    limit=5,
)

for entry in results:
    print(f"[{entry.quality:.2f}] {entry.text[:60]}...")
    print(f"  Topic: {entry.topic} | Source: {entry.source}")
```

### Checking Knowledge Base Statistics

```python
stats = curator.get_stats()
print(stats)
# CurationStats(
#     total_entries=3247,
#     by_topic={
#         "TECH": 1205,
#         "SCIENCE": 634,
#         "BUSINESS": 412,
#         "CREATIVE": 289,
#         "HEALTH": 198,
#         "SOCIAL": 156,
#         "META": 353
#     },
#     avg_quality=0.79,
#     contradiction_count=23,
#     deprecated_count=87,
#     dedup_savings=412,
# )
```

### Handling Rejections

```python
result = curator.curate(
    text="asdf qwer zxcv random noise no real content",
    source="test",
)

if not result.accepted:
    print(f"Rejected at stage: {result.rejections}")
    # ["quality_assessment: score 0.12 below threshold 0.5"]
```

---

## Configuration

```yaml
information_curator:
  min_quality: 0.5                       # Minimum quality score to accept entry
  dedup_threshold: 0.85                  # Similarity threshold for near-duplicates
  classification_confidence: 0.6         # Min confidence for topic classification
  enable_contradiction_detection: true    # Enable contradiction detection stage

  # Cleaning options
  cleaning:
    strip_html: true                      # Remove HTML tags
    normalize_whitespace: true            # Collapse multiple spaces/newlines
    fix_encoding: true                    # Fix common encoding issues
    remove_boilerplate: true              # Remove web page boilerplate

  # Deduplication options
  deduplication:
    method: "minhash"                     # "minhash" or "exact_hash"
    num_perm: 128                         # MinHash permutations
    bands: 16                             # LSH bands for near-dup detection

  # Classification options
  classification:
    model: "topic_classifier_v2"          # Classifier model name
    fallback_topic: "META"                # Topic for low-confidence classifications
    min_confidence: 0.6                   # Min confidence to assign topic

  # Quality assessment
  quality:
    min_score: 0.5                        # Minimum quality to accept
    criteria:
      source_reliability_weight: 0.25
      completeness_weight: 0.25
      factual_grounding_weight: 0.30
      structural_clarity_weight: 0.20

  # Contradiction detection
  contradiction:
    enabled: true
    similarity_threshold: 0.7             # Minimum similarity to check for contradiction
    auto_flag: true                       # Auto-flag contradictions
    resolution_required: false            # Require resolution before storage

  # Deprecation
  deprecation:
    auto_deprecate_age_days: 365          # Auto-deprecate entries older than 1 year
    auto_deprecate_enabled: false         # Enable auto-deprecation (off by default)
