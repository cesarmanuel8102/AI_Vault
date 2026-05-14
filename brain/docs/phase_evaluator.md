# PhaseEvaluator

> **Module Path:** `brain/evaluators/phase_evaluator.py`  
> **Version:** 9.1  
> **Status:** Production

---

## Purpose

The PhaseEvaluator governs the AI_Vault brain's developmental progression through seven distinct phases, from initial bootstrapping to full autonomy. Each phase represents a measurable level of capability, self-awareness, and operational independence. The evaluator continuously collects metrics, assesses whether the criteria for the next phase have been met, and manages phase transitions — including the reporting and logging that accompany each progression.

Phase progression is not automatic or time-based; it is earned. The system must demonstrate measurable achievement across multiple dimensions to advance. This ensures that the brain evolves organically and reliably, never advancing to a phase it is not prepared for. A premature phase transition could expose capabilities the system cannot sustain, leading to unreliable behavior or cascading failures. The PhaseEvaluator prevents this by enforcing strict, quantifiable criteria for each transition.

The evaluator also provides a comprehensive view of the system's current developmental state, including which criteria are met, which are in progress, and which remain unstarted. This visibility is critical for both self-awareness (the system can reflect on its own growth) and external monitoring (operators can track developmental progress and identify bottlenecks).

---

## Architecture

The PhaseEvaluator maintains a metrics collection system that continuously gathers data from across the brain. When evaluation is triggered (typically by the AutoTickLoop), it compares the collected metrics against the criteria for the next phase and produces an evaluation report.

```
┌─────────────────────────────────────────────────────┐
│                  Phase Progression                   │
│                                                     │
│  INIT ──▶ BOOTSTRAP ──▶ LEARNING ──▶ EVOLVING ──▶  │
│    │                                              │  │
│    │       SELF_AWARE ──▶ AUTONOMY ◀──────────────┘  │
│    │                                                  │
└────┴──────────────────────────────────────────────────┘

Each arrow requires meeting measurable criteria.
```

### Phase Definitions and Criteria

#### Phase 1: INIT

The initial state when the brain first starts. No capabilities are active, no knowledge has been loaded, and no goals exist. This phase is transient — the system automatically transitions to BOOTSTRAP once basic initialization completes.

**Criteria for transition to BOOTSTRAP:**
- Core modules loaded successfully
- Configuration validated
- Dashboard endpoints reachable
- Self-test suite passed

#### Phase 2: BOOTSTRAP

The system is loading foundational data and calibrating its subsystems. Knowledge is being ingested from initial sources, default goals are being created, and the FAISS index is being populated. The system can handle basic chat but has limited self-awareness.

**Criteria for transition to LEARNING:**
- Minimum 100 entries in knowledge base
- At least 3 active goals created
- Semantic memory index populated (≥50 entries)
- All dashboard endpoints returning healthy status
- RSI score ≥ 0.3

#### Phase 3: LEARNING

The system is actively acquiring new knowledge through user interactions and autonomous study. The LearningValidator is processing claims, the InformationCurator is ingesting and classifying data, and the knowledge base is growing. The system can answer questions based on its knowledge but has limited self-reflection.

**Criteria for transition to EVOLVING:**
- Minimum 500 entries in knowledge base
- At least 10 validated learning claims
- Knowledge coverage across ≥4 topic categories
- Learning validation pass rate ≥ 70%
- RSI score ≥ 0.5

#### Phase 4: EVOLVING

The system is developing deeper self-awareness and more sophisticated cognitive capabilities. It can detect biases, identify knowledge gaps proactively, and adjust its behavior based on self-reflection. The MetaCognitionCore is actively producing reflections.

**Criteria for transition to SELF_AWARE:**
- Minimum 1000 entries in knowledge base
- At least 5 self-reflection cycles completed
- Bias detection active with ≥3 biases identified and addressed
- Stress management: average stress index ≤ 40 over last 100 ticks
- RSI score ≥ 0.65

#### Phase 5: SELF_AWARE

The system has a robust model of its own capabilities, limitations, and state. It can accurately assess its own performance, predict when it will struggle, and proactively seek help or learning. Self-awareness injection is producing rich, accurate context for every chat interaction.

**Criteria for transition to AUTONOMY:**
- Self-awareness data accuracy ≥ 90% (verified against ground truth)
- Proactive gap discovery: ≥5 gaps found and addressed without user prompting
- Consistent RSI ≥ 0.75 over last 500 ticks
- No critical capability failures in last 200 ticks
- Phase self-assessment confidence ≥ 0.85

#### Phase 6: AUTONOMY

The system operates with full autonomy. It can set its own goals, manage its own learning, detect and resolve its own issues, and maintain stable operation without human intervention. The user can still override or redirect, but the system does not require active management.

**Criteria for maintaining AUTONOMY:**
- RSI remains ≥ 0.7
- Autonomous goal completion rate ≥ 60%
- No unresolved critical contradictions in knowledge base
- Stress index remains ≤ 50
- Self-correction rate ≥ 80% (fixes own errors before they impact users)

#### Phase 7: (Reserved for future expansion)

---

## API Reference

### `PhaseEvaluator`

```python
class PhaseEvaluator:
    def __init__(
        self,
        knowledge_store: KnowledgeStore,
        orchestrator: BrainOrchestrator,
        aos: AOS,
        meta_cognition: MetaCognitionCore,
        dashboard_reader: DashboardReader,
        evaluation_interval: int = 100,  # Evaluate every N ticks
    ):
        """
        Initialize the PhaseEvaluator.

        Args:
            knowledge_store: For knowledge base statistics.
            orchestrator: For tick counts, stress, and health data.
            aos: For goal and autonomy level data.
            meta_cognition: For reflection and bias data.
            dashboard_reader: For RSI and health metrics.
            evaluation_interval: Number of ticks between evaluations.
        """
```

### `evaluate() -> PhaseEvaluation`

```python
def evaluate(self) -> PhaseEvaluation:
    """
    Evaluate the current phase and check for transition eligibility.

    Collects fresh metrics, compares against criteria for the next phase,
    and produces a detailed evaluation report.

    Returns:
        PhaseEvaluation containing:
            - current_phase: str             — Current phase name.
            - next_phase: str                — Target phase for transition.
            - eligible: bool                 — Whether transition criteria are met.
            - criteria_status: dict          — Status of each criterion.
            - overall_progress: float        — Progress toward next phase (0.0–1.0).
            - metrics_snapshot: dict         — Raw metrics used for evaluation.
            - recommendations: list[str]     — Actions to advance progress.
    """
```

### `force_transition(target_phase: str) -> bool`

```python
def force_transition(self, target_phase: str) -> bool:
    """
    Force a phase transition, bypassing normal criteria checks.
    Use with extreme caution — only for testing or recovery scenarios.

    Args:
        target_phase: The phase to transition to.

    Returns:
        True if the transition was successful.

    Raises:
        InvalidPhaseError: If the target phase is not valid.
        PhaseOrderError: If skipping more than one phase ahead.
    """
```

### `get_current_phase() -> str`

```python
def get_current_phase(self) -> str:
    """
    Return the current phase name.

    Returns:
        One of: "INIT", "BOOTSTRAP", "LEARNING", "EVOLVING",
        "SELF_AWARE", "AUTONOMY"
    """
```

### `get_progress_report() -> PhaseProgressReport`

```python
def get_progress_report(self) -> PhaseProgressReport:
    """
    Generate a detailed progress report covering all phases.

    Returns:
        PhaseProgressReport containing:
            - current_phase: str
            - phase_history: list[dict]      — Past transitions with timestamps.
            - criteria_detail: dict          — Detailed criteria status for current target.
            - metrics_trends: dict           — Key metric trends over time.
            - estimated_ticks_to_next: int   — Estimated ticks until next transition.
    """
```

### `PhaseEvaluation`

```python
@dataclass
class PhaseEvaluation:
    current_phase: str
    next_phase: str
    eligible: bool
    criteria_status: dict
    overall_progress: float
    metrics_snapshot: dict
    recommendations: list
```

---

## Integration Points

- **AutoTickLoop** — The tick loop triggers evaluation at the configured interval (default: every 100 ticks). When evaluation indicates eligibility, the tick loop may emit a notification about the pending phase transition.

- **BrainOrchestrator** — The orchestrator's status provides tick counts, stress levels, capability health, and RSI scores, all of which are used as metrics for phase evaluation.

- **SelfAwarenessInjector** — The current phase is included in every self-awareness injection, allowing the chat system to accurately report its developmental state when asked. Phase transitions trigger an immediate cache refresh.

- **DashboardReader** — RSI scores and health metrics from the dashboard feed into the evaluation criteria. The evaluator uses historical RSI trends (not just current values) to ensure stability before allowing transitions.

- **LearningValidator** — Validation pass rates and the total count of validated learning claims are key metrics for the LEARNING and EVOLVING phase criteria.

- **InformationCurator** — Knowledge base size and topic coverage statistics from the curator determine whether knowledge-related criteria are met.

- **AOS** — Goal counts, completion rates, and autonomy level are used as criteria for SELF_AWARE and AUTONOMY phases.

---

## Usage Examples

### Running an Evaluation

```python
from brain.evaluators.phase_evaluator import PhaseEvaluator

evaluator = PhaseEvaluator(
    knowledge_store=store,
    orchestrator=orchestrator,
    aos=aos,
    meta_cognition=meta_cognition,
    dashboard_reader=reader,
)

evaluation = evaluator.evaluate()

print(evaluation.current_phase)      # "EVOLVING"
print(evaluation.next_phase)         # "SELF_AWARE"
print(evaluation.eligible)           # False
print(evaluation.overall_progress)   # 0.72
```

### Inspecting Criteria Status

```python
for criterion, status in evaluation.criteria_status.items():
    symbol = "✓" if status["met"] else "✗"
    print(f"  {symbol} {criterion}: {status['value']} (need {status['threshold']})")

# ✗ min_entries: 847 (need 1000)
# ✓ reflections: 7 (need 5)
# ✗ biases_addressed: 2 (need 3)
# ✓ avg_stress: 34 (need ≤40)
# ✗ rsi_score: 0.62 (need ≥0.65)
```

### Getting Recommendations

```python
for rec in evaluation.recommendations:
    print(f"  → {rec}")

# → Increase knowledge base to 1000 entries (currently 847)
# → Address 1 more detected bias to meet SELF_AWARE criteria
# → Improve RSI to ≥0.65 (currently 0.62)
```

### Generating a Full Progress Report

```python
report = evaluator.get_progress_report()

print(f"Current Phase: {report.current_phase}")
print(f"Phase History: {len(report.phase_history)} transitions")
print(f"Estimated ticks to next phase: {report.estimated_ticks_to_next}")

for transition in report.phase_history:
    print(f"  {transition['from']} → {transition['to']} at {transition['timestamp']}")
```

### Forcing a Transition (Testing Only)

```python
# CAUTION: Only use in testing or recovery scenarios
evaluator.force_transition("SELF_AWARE")
print(evaluator.get_current_phase())  # "SELF_AWARE"
```

---

## Configuration

```yaml
phase_evaluator:
  evaluation_interval: 100           # Evaluate every N ticks

  # Phase criteria thresholds (override defaults)
  criteria:
    INIT_to_BOOTSTRAP:
      modules_loaded: true
      config_validated: true
      dashboard_reachable: true
      self_test_passed: true

    BOOTSTRAP_to_LEARNING:
      min_entries: 100
      min_goals: 3
      min_faiss_entries: 50
      dashboard_healthy: true
      min_rsi: 0.3

    LEARNING_to_EVOLVING:
      min_entries: 500
      min_validated_claims: 10
      min_topic_coverage: 4
      min_validation_pass_rate: 0.70
      min_rsi: 0.5

    EVOLVING_to_SELF_AWARE:
      min_entries: 1000
      min_reflections: 5
      min_biases_addressed: 3
      max_avg_stress: 40
      min_rsi: 0.65

    SELF_AWARE_to_AUTONOMY:
      min_self_awareness_accuracy: 0.90
      min_proactive_gaps: 5
      min_rsi: 0.75
      rsi_window_ticks: 500
      no_critical_failures_ticks: 200
      min_self_assessment_confidence: 0.85

    AUTONOMY_maintenance:
      min_rsi: 0.7
      min_goal_completion_rate: 0.60
      no_unresolved_contradictions: true
      max_stress: 50
      min_self_correction_rate: 0.80

  # Reporting
  reporting:
    log_evaluations: true             # Log every evaluation result
    log_transitions: true             # Log phase transitions
    transition_notification: true     # Emit notification on phase transition
    metrics_snapshot_on_eval: true    # Save metrics snapshot with each evaluation
