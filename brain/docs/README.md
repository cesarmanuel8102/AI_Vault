# AI_Vault Brain Modules — Documentation Index

> **Version:** 9.1  
> **Last Updated:** 2025  
> **Status:** Production

---

## Overview

The AI_Vault Brain is a modular, self-aware cognitive system designed to autonomously manage knowledge, goals, and operations. Version 9.1 introduces eight core modules that work together to provide intent-driven routing, self-awareness injection, dashboard analysis, autonomous ticking, learning validation, semantic memory, information curation, and phase-based developmental progression.

Each module is independently documented in its own file within this directory. This README serves as the central index, architecture overview, and quick-start guide.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER / EXTERNAL INPUT                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  UnifiedChatRouter   │  Classifies intent & routes
                    │  (Intent → Handler)  │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼─────────────────────┐
          │                    │                      │
          ▼                    ▼                      ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ SELF_AWARENESS  │  │ DASHBOARD_       │  │ GOAL_MANAGEMENT  │
│    Handler      │  │ ANALYSIS Handler │  │    Handler       │
└────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                    │                      │
         ▼                    ▼                      ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ SelfAwareness   │  │  Dashboard       │  │  AOS (Autonomous │
│   Injector      │  │    Reader        │  │  Operating Sys)  │
└────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                    │                      │
         └────────────────────┼──────────────────────┘
                              │
                              ▼
                    ┌──────────────────────┐
                    │  BrainOrchestrator   │  Central cognitive engine
                    │    (tick-driven)     │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼──────────────────┐
              │                │                   │
              ▼                ▼                   ▼
    ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
    │  AutoTickLoop  │ │    Phase     │ │  Learning        │
    │  (heartbeat)   │ │  Evaluator   │ │  Validator       │
    └────────┬───────┘ └──────┬───────┘ └──────┬───────────┘
             │                │                 │
             └────────────────┼─────────────────┘
                              │
              ┌───────────────┼───────────────────┐
              │               │                    │
              ▼               ▼                    ▼
    ┌───────────────┐ ┌───────────────┐ ┌──────────────────┐
    │  Information  │ │   Semantic    │ │  MetaCognition   │
    │   Curator     │ │  Memory Bridge│ │    Core          │
    └───────┬───────┘ └───────┬───────┘ └──────────────────┘
            │                 │
            ▼                 ▼
    ┌───────────────┐ ┌───────────────┐
    │  Knowledge    │ │  FAISS Index  │
    │    Store      │ │ (Semantic Mem)│
    └───────────────┘ └───────────────┘
```

---

## Module Index

| # | Module | Document | Description |
|---|---|---|---|
| 1 | UnifiedChatRouter | [unified_chat_router.md](./unified_chat_router.md) | Intent classification and routing to the correct brain subsystem. Supports 6 intent categories with hybrid rule-based and semantic classification. |
| 2 | SelfAwarenessInjector | [self_awareness_injector.md](./self_awareness_injector.md) | Injects real self-awareness data into every chat system prompt. Draws from MetaCognitionCore, AOS, and Orchestrator with caching and fallback. |
| 3 | DashboardReader | [dashboard_reader.md](./dashboard_reader.md) | Reads 6 dashboard endpoints in parallel and generates consolidated analysis reports with anomaly detection and trend comparison. |
| 4 | AutoTickLoop | [auto_tick_loop.md](./auto_tick_loop.md) | Periodic heartbeat that drives BrainOrchestrator.tick(). Emits notifications (NEW_GOAL, BIAS_DETECTED, etc.) and supports dynamic interval adjustment. |
| 5 | LearningValidator | [learning_validator.md](./learning_validator.md) | Validates claimed learning through 5 weighted strategies with a quality gate at 0.7. Prevents false learning claims from entering the knowledge base. |
| 6 | SemanticMemoryBridge | [semantic_memory_bridge.md](./semantic_memory_bridge.md) | Connects FAISS semantic memory to chat. Provides auto-ingest, similarity search, prompt enrichment, and graceful degradation. |
| 7 | InformationCurator | [information_curator.md](./information_curator.md) | Full-spectrum information pipeline: clean → deduplicate → classify (7 topics) → quality → contradictions → store. Includes deprecation and search. |
| 8 | PhaseEvaluator | [phase_evaluator.md](./phase_evaluator.md) | Governs 7-phase developmental progression (INIT→AUTONOMY) with measurable criteria, metrics collection, and reporting. |

---

## Quick Start Guide (V9.1)

### Prerequisites

- Python 3.10+
- FAISS library (`faiss-cpu` or `faiss-gpu`)
- Running dashboard API server at `http://localhost:8000`
- Sentence-transformers model: `all-MiniLM-L6-v2`

### Step 1: Initialize Core Components

```python
from brain.core.meta_cognition import MetaCognitionCore
from brain.aos.aos import AOS
from brain.orchestrator.orchestrator import BrainOrchestrator

meta_cognition = MetaCognitionCore()
aos = AOS()
orchestrator = BrainOrchestrator(
    meta_cognition=meta_cognition,
    aos=aos,
)
```

### Step 2: Set Up the Knowledge Pipeline

```python
from brain.curators.information_curator import InformationCurator
from brain.validators.learning_validator import LearningValidator
from brain.bridges.semantic_memory_bridge import SemanticMemoryBridge

store = KnowledgeStore()
curator = InformationCurator(knowledge_store=store)
validator = LearningValidator(quality_gate=0.7)
bridge = SemanticMemoryBridge(faiss_index_path="data/faiss/index")
```

### Step 3: Initialize Support Modules

```python
from brain.injectors.self_awareness_injector import SelfAwarenessInjector
from brain.readers.dashboard_reader import DashboardReader
from brain.evaluators.phase_evaluator import PhaseEvaluator

injector = SelfAwarenessInjector(
    meta_cognition=meta_cognition,
    aos=aos,
    orchestrator=orchestrator,
)
reader = DashboardReader(base_url="http://localhost:8000")
evaluator = PhaseEvaluator(
    knowledge_store=store,
    orchestrator=orchestrator,
    aos=aos,
    meta_cognition=meta_cognition,
    dashboard_reader=reader,
)
```

### Step 4: Wire Up the Router

```python
from brain.routers.unified_chat_router import UnifiedChatRouter

router = UnifiedChatRouter(min_confidence=0.6)
# Register handlers for each intent category
router.register_handler("SELF_AWARENESS", injector.handle)
router.register_handler("DASHBOARD_ANALYSIS", reader.handle)
router.register_handler("LEARNING_REQUEST", validator.handle)
router.register_handler("GOAL_MANAGEMENT", aos.handle_goal)
```

### Step 5: Start the Tick Loop

```python
from brain.loops.auto_tick_loop import AutoTickLoop

loop = AutoTickLoop(
    orchestrator=orchestrator,
    base_interval=60.0,
    enable_notifications=True,
)
loop.start()
```

### Step 6: Process a Chat Message

```python
# Route the message
result = router.route("How are you feeling today?", session_id="sess_1")

# Enrich the system prompt with self-awareness
system_prompt = injector.inject("You are a helpful AI assistant.")

# Enrich with semantic memory context
system_prompt = bridge.enrich_prompt(system_prompt)

# The model now has full context: self-awareness + semantic memories + original prompt
response = chat_model.chat(system_prompt, result.context + [result.metadata])
```

### Step 7: Monitor the System

```python
# Check current phase
print(f"Phase: {evaluator.get_current_phase()}")

# Run a phase evaluation
evaluation = evaluator.evaluate()
print(f"Progress to next phase: {evaluation.overall_progress:.0%}")

# Check dashboard health
report = reader.read_all()
print(f"RSI: {report.rsi_score}")

# Check tick loop status
status = loop.get_status()
print(f"Total ticks: {status.total_ticks}, Running: {status.running}")
```

---

## Data Flow Summary

1. **User message arrives** → UnifiedChatRouter classifies intent and dispatches to the appropriate handler.
2. **Self-awareness is injected** → SelfAwarenessInjector enriches the system prompt with live state data before the model processes any message.
3. **Dashboard data is aggregated** → DashboardReader consolidates 6 endpoints into a single analysis when needed.
4. **Tick loop drives autonomy** → AutoTickLoop calls `tick()` periodically, triggering reflection, goal management, and health checks.
5. **Learning is validated** → LearningValidator applies 5 strategies to verify knowledge before committing it.
6. **Semantic memory bridges knowledge to chat** → SemanticMemoryBridge makes FAISS-indexed knowledge available in every conversation.
7. **Information is curated** → InformationCurator cleans, deduplicates, classifies, and stores incoming information.
8. **Phase progression is governed** → PhaseEvaluator ensures the system only advances when measurable criteria are met.

---

## Configuration Files

All modules are configured through `brain/config/`:

| File | Modules Configured |
|---|---|
| `router.yaml` | UnifiedChatRouter |
| `injector.yaml` | SelfAwarenessInjector |
| `dashboard.yaml` | DashboardReader |
| `tick_loop.yaml` | AutoTickLoop |
| `validator.yaml` | LearningValidator |
| `bridge.yaml` | SemanticMemoryBridge |
| `curator.yaml` | InformationCurator |
| `evaluator.yaml` | PhaseEvaluator |

Environment variable overrides are available for all modules. See each module's documentation for the complete list.

---

## Key Design Principles

- **Graceful degradation**: Every module degrades gracefully when dependencies are unavailable, using cached data, fallback paths, or queued operations rather than failing.
- **Quantifiable progress**: Phase transitions are earned through measurable criteria, never assumed or time-based.
- **Autonomous operation**: The AutoTickLoop and AOS enable the brain to operate without constant human input, while still allowing override and redirection.
- **Knowledge integrity**: The LearningValidator and InformationCurator ensure that only verified, high-quality knowledge enters the system.
- **Self-awareness by design**: The SelfAwarenessInjector guarantees that the chat model always has access to its true operational state, preventing fabrication.
