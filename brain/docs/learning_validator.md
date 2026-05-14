# LearningValidator

> **Module Path:** `brain/validators/learning_validator.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The LearningValidator ensures that claimed learning is genuine. When the AI_Vault brain system acquires new knowledge — whether through explicit user teaching, autonomous study, or information ingestion — the LearningValidator applies a rigorous, multi-strategy assessment to verify that the knowledge has been truly internalized and can be reliably used. It prevents the system from claiming to "know" something it has only superficially encountered, which would erode trust and lead to unreliable behavior.

The validator employs five distinct assessment strategies, each with a different weight, to produce a composite learning quality score. This weighted approach ensures that no single strategy can inflate or deflate the overall score disproportionately. The composite score is then compared against a configurable quality gate threshold (default: 0.7). Only learning that exceeds this threshold is committed to the knowledge base; anything below is flagged for additional study or rejected entirely.

This module is essential for maintaining the integrity of the brain's knowledge base. Without it, the system would be vulnerable to false learning claims — for example, reading a document once and then asserting mastery of its content. The LearningValidator enforces depth and reliability by requiring evidence of understanding across multiple dimensions before certifying any learning outcome.

---

## Architecture

The LearningValidator uses a weighted composite scoring model. Each of the five strategies produces an independent score from 0.0 to 1.0, and these scores are combined using their respective weights to produce the final composite score.

```
Learning Claim
      │
      ▼
┌─────────────────────────────────────────────┐
│            Strategy Pipeline                 │
│                                             │
│  ┌──────────────────────┐  Weight: 0.30     │
│  │ Capability Assessment │──────────┐       │
│  └──────────────────────┘          │       │
│  ┌──────────────────────┐  Weight: 0.25     │
│  │   Test Questions     │──────────┤       │
│  └──────────────────────┘          │       │
│  ┌──────────────────────┐  Weight: 0.20     │
│  │  Consistency Check   │──────────┤       │
│  └──────────────────────┘          ├──▶ Composite Score
│  ┌──────────────────────┐  Weight: 0.15     │
│  │   Gap Resolution     │──────────┤       │
│  └──────────────────────┘          │       │
│  ┌──────────────────────┐  Weight: 0.10     │
│  │   Before/After       │──────────┘       │
│  └──────────────────────┘                  │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │  Quality Gate  │ ── Composite ≥ 0.7? ──▶ COMMIT or REJECT
              └────────────────┘
```

### Strategy Details

#### 1. Capability Assessment (Weight: 0.30)

The highest-weighted strategy directly tests whether the claimed capability can be demonstrated. If the learning claim is "I understand Python decorators," the capability assessment generates a practical task that requires using decorators and evaluates the result. This strategy carries the most weight because it provides the most direct evidence of functional knowledge.

#### 2. Test Questions (Weight: 0.25)

Generates a set of targeted questions about the learned material and evaluates the answers for correctness, completeness, and depth. Questions range from factual recall to conceptual understanding and application scenarios. This strategy catches cases where a capability can be mimicked but underlying understanding is shallow.

#### 3. Consistency Check (Weight: 0.20)

Verifies that the new learning is logically consistent with existing knowledge. If the new learning contradicts established facts without adequate explanation, the consistency score is penalized. This prevents the system from incorporating knowledge that creates internal contradictions in its world model.

#### 4. Gap Resolution (Weight: 0.15)

Assesses whether the learning actually resolves the knowledge gap that motivated it. This ensures that learning is targeted and relevant — not just any knowledge, but the specific knowledge that was needed. If the original gap was "understanding async/await in Rust" but the learning covered JavaScript Promises instead, the gap resolution score would be low.

#### 5. Before/After Comparison (Weight: 0.10)

Compares the system's behavior or knowledge state before and after the learning claim. If there is no measurable difference, the learning is considered ineffective regardless of other scores. This is the lowest-weighted strategy because it can be noisy (some learning is subtle or latent), but it serves as a useful sanity check.

---

## API Reference

### `LearningValidator`

```python
class LearningValidator:
    def __init__(
        self,
        quality_gate: float = 0.7,
        strategies: dict[str, float] = None,
        test_question_count: int = 5,
        consistency_depth: int = 3,
    ):
        """
        Initialize the LearningValidator.

        Args:
            quality_gate: Minimum composite score to accept learning (0.0–1.0).
            strategies: Override default strategy weights. Keys are strategy names,
                        values are weights. Must sum to 1.0.
            test_question_count: Number of test questions to generate per assessment.
            consistency_depth: How many layers of existing knowledge to check for consistency.
        """
```

### `validate(claim: LearningClaim) -> ValidationResult`

```python
def validate(self, claim: LearningClaim) -> ValidationResult:
    """
    Validate a learning claim using all five strategies.

    Args:
        claim: A LearningClaim containing:
            - topic: str           — The subject of the claimed learning.
            - source: str          — Where the learning came from.
            - claimed_knowledge: str — Summary of what was learned.
            - original_gap: str    — The knowledge gap that motivated learning (if any).
            - before_state: dict   — Knowledge state before learning.
            - after_state: dict    — Knowledge state after learning.

    Returns:
        ValidationResult containing:
            - composite_score: float       — Weighted composite score.
            - passed: bool                 — Whether score exceeds quality_gate.
            - strategy_scores: dict        — Individual scores per strategy.
            - recommendations: list[str]   — Suggestions for improvement if failed.
            - details: dict                — Detailed per-strategy assessment data.
    """
```

### `validate_capability_only(claim: LearningClaim) -> float`

```python
def validate_capability_only(self, claim: LearningClaim) -> float:
    """
    Run only the Capability Assessment strategy.
    Useful for quick sanity checks before running the full validation pipeline.

    Args:
        claim: The learning claim to assess.

    Returns:
        Capability assessment score (0.0–1.0).
    """
```

### `get_strategy_weights() -> dict[str, float]`

```python
def get_strategy_weights(self) -> dict[str, float]:
    """
    Return the current strategy weights.

    Returns:
        Dictionary mapping strategy names to their weights.
        e.g., {"capability_assessment": 0.30, "test_questions": 0.25, ...}
    """
```

### `ValidationResult`

```python
@dataclass
class ValidationResult:
    composite_score: float
    passed: bool
    strategy_scores: dict
    recommendations: list
    details: dict
```

---

## Integration Points

- **UnifiedChatRouter** — When a `LEARNING_REQUEST` is classified, the router creates a `LearningClaim` and submits it to the validator. Only validated learning is committed to the knowledge base and reported as successful to the user.

- **InformationCurator** — The curator's pipeline submits ingested information as potential learning claims. The validator ensures that curated information meets the quality bar before it is stored as verified knowledge.

- **BrainOrchestrator** — During tick processing, the orchestrator may identify knowledge gaps and trigger autonomous learning. The validator confirms whether the self-directed learning was effective before closing the gap.

- **AutoTickLoop** — When a `GAP_DISCOVERED` notification leads to autonomous learning, the validator's result determines whether the gap can be marked as resolved or whether additional study is needed.

- **SemanticMemoryBridge** — Validated learning is ingested into the FAISS semantic memory index, making it available for future search and prompt enrichment. Only learning that passes the quality gate is indexed.

---

## Usage Examples

### Validating a Learning Claim

```python
from brain.validators.learning_validator import LearningValidator, LearningClaim

validator = LearningValidator(quality_gate=0.7)

claim = LearningClaim(
    topic="Python Decorators",
    source="user_teaching",
    claimed_knowledge="Decorators are functions that modify other functions. They use @syntax.",
    original_gap="Understanding Python decorator patterns",
    before_state={"decorators": "unknown"},
    after_state={"decorators": "can use @staticmethod, @classmethod, custom decorators"},
)

result = validator.validate(claim)

print(result.composite_score)  # 0.78
print(result.passed)           # True
print(result.strategy_scores)
# {
#     "capability_assessment": 0.85,
#     "test_questions": 0.72,
#     "consistency_check": 0.80,
#     "gap_resolution": 0.75,
#     "before_after": 0.65
# }
```

### Failed Validation with Recommendations

```python
claim = LearningClaim(
    topic="Quantum Computing",
    source="autonomous_study",
    claimed_knowledge="Qubits can be 0 and 1 at the same time.",
    original_gap="Understanding quantum gate operations",
    before_state={"quantum": "none"},
    after_state={"quantum": "superposition concept only"},
)

result = validator.validate(claim)

print(result.composite_score)  # 0.52
print(result.passed)           # False
print(result.recommendations)
# [
#     "Deepen understanding: current knowledge is superficial",
#     "Gap not resolved: 'quantum gate operations' still unclear",
#     "No measurable capability improvement detected"
# ]
```

### Quick Capability Check

```python
score = validator.validate_capability_only(claim)
if score < 0.5:
    print("Capability assessment failed — skip full validation")
else:
    result = validator.validate(claim)
```

### Custom Strategy Weights

```python
validator = LearningValidator(
    quality_gate=0.75,
    strategies={
        "capability_assessment": 0.40,  # Emphasize practical capability
        "test_questions": 0.30,
        "consistency_check": 0.15,
        "gap_resolution": 0.10,
        "before_after": 0.05,
    },
)
```

---

## Configuration

```yaml
learning_validator:
  quality_gate: 0.7                    # Minimum composite score to accept learning
  test_question_count: 5               # Questions generated per assessment
  consistency_depth: 3                 # Layers of knowledge to check for consistency

  # Strategy weights (must sum to 1.0)
  strategy_weights:
    capability_assessment: 0.30
    test_questions: 0.25
    consistency_check: 0.20
    gap_resolution: 0.15
    before_after: 0.10

  # Per-strategy thresholds
  strategy_thresholds:
    capability_assessment:
      min_pass: 0.5            # Below this, auto-reject regardless of composite
    test_questions:
      min_correct_ratio: 0.6   # Must answer at least 60% correctly
    consistency_check:
      max_contradictions: 2    # Allow up to 2 minor contradictions
    gap_resolution:
      min_coverage: 0.5        # Must address at least 50% of the original gap
    before_after:
      min_delta: 0.1           # Must show at least 10% measurable change

  # Behavior on validation failure
  on_failure:
    auto_retry: true            # Automatically attempt re-learning
    max_retries: 3              # Maximum retry attempts
    retry_delay_seconds: 60     # Wait before retrying
    log_failure: true           # Log all validation failures for analysis
