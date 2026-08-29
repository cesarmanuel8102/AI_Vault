# BRAIN-101-R3-2 Agent V2 Cognitive Pipeline Contracts

## Document Identifier

- **Front ID:** BRAIN-101-R3-2-AGENT-V2-COGNITIVE-PIPELINE-CONTRACTS-01
- **Cycle:** 0
- **Scope:** Contract tests for Agent V2 intent router, planner, evaluator, and tool gateway surfaces
- **Domain:** testing_ci_recovery
- **Deployment:** NO_DEPLOY

## Purpose

This front closes the high-severity contract gaps identified in
`BRAIN_101_R3_1_CONTRACT_E2E_GAP_MATRIX.md` for the Agent V2 cognitive pipeline
(C2 Intent, C3 Planner, C4 Evaluator, C6 Tool Gateway, and a focused C1
Runtime Lifecycle contract).  It adds deterministic contract tests that
exercise each surface without modifying productive runtime wiring, without
starting servers, without making live HTTP calls, and without performing real
write operations.

## Contract Surface Matrix

| Surface | R3 Gap ID | Classification | Binding Test File | Notes |
|---|---|---|---|---|
| C2 Intent Router | G-H1 | **PRESENT** | `tests/contract/test_brain_101_r3_2_intent_router_contract.py` | Keyword classifier schema, route map, evidence policy, adapter evidence-source contract |
| C3 Planner | G-H2 | **PRESENT** | `tests/contract/test_brain_101_r3_2_planner_contract.py` | build_plan schema, planner class inventory, explicit tool request detection, diagnostic phrases, tool resolution |
| C4 Evaluator | G-H3 | **PRESENT** | `tests/contract/test_brain_101_r3_2_evaluator_contract.py` | LangGraphParityRuntimeV2 evaluator node criteria schema, governance compliance, repair/replan signal |
| C6 Tool Gateway | G-H4 | **PARTIAL → PRESENT** | `tests/contract/test_brain_101_r3_2_tool_gateway_contract.py` | Capability schema, read-only execution, write-tool gating, path blocking, route probe rules, bounded timeout and safe transport fallback, result normalization |
| C1 Runtime Lifecycle | G-M1 | **PARTIAL → PRESENT** | `tests/contract/test_brain_101_r3_2_runtime_lifecycle_contract.py` | Backend selector, required runtime interface, create/plan/pause/resume/cancel, checkpoint persistence and fresh-runtime resume, status constants |

### Classification Legend

- **PRESENT:** A dedicated deterministic contract test file exists and covers the surface's canonical contract.
- **PARTIAL:** An adjacent contract exists (e.g., route split) but the behavioral/schema contract is incomplete.
- **MISSING:** No contract coverage exists.

## Part 1: Intent Router Contract (C2)

**File:** `tests/contract/test_brain_101_r3_2_intent_router_contract.py`

### Verified Contracts

1. **Supported intent inventory** — `SUPPORTED_INTENTS` contains all canonical
   operational intents and excludes `god_mode`.
2. **Route map** — `INTENT_ROUTE_MAP` maps every intent to one of
   `direct_assistant`, `brain_evidence`, or `operational_agent`; trading is
   routed to `direct_assistant` for a safe refusal.
3. **Classification output schema** — `classify_intent` returns the required
   keys: `intent`, `confidence`, `language`, `risk_level`, `requires_approval`,
   `route`, `reason`, `blocked_reason`, `matched_terms`, `classifier`.
4. **Safety classification** — `trading_broker_live` is blocked;
   `code_change_request`/`memory_write` require approval; negated phrases are
   not escalated.
5. **IntentAdapter route contract** — `AgentV2IntentAdapter.select_route`
   returns a route and required metadata.
6. **Evidence-source contract** — `EVIDENCE_SOURCE_CONTRACT` contains the
   required source types with keyword lists, tools, paths, and priority.
7. **Governance policy on intents** — `decide_governance` returns the expected
   schema for allowed, blocked, approval-required, and dry-run-only intents.
8. **Evidence policy** — Brain-internal questions route through
   `brain_evidence`; generic greetings are excluded.
9. **Safety boundary** — Intent classifier and adapter source files do not
   import uvicorn, FastAPI, TestClient, os.system, or subprocess.run.

### Classification

- **C2 Intent Router:** PRESENT

## Part 2: Planner Contract (C3)

**File:** `tests/contract/test_brain_101_r3_2_planner_contract.py`

### Verified Contracts

1. **Planner class inventory** — `PLANNER_CLASSES` contains all required
   diagnostic/operational classes and excludes forbidden classes.
2. **build_plan output schema** — Returns `(classification, plan, metadata)` with
   required `step_id`, `kind`, `title`, `status`, and tool schema.
3. **Read-only scheduling** — Read-only goals schedule only read-only tools
   (e.g., `repo_status_read`, `grep_search`, `route_probe`).
4. **Explicit tool request detection** — `_detect_explicit_tool_requests`
   extracts named canonical tools and ignores generic words like "tool".
5. **Diagnostic phrase mapping** — `DIAGNOSTIC_PHRASES` maps symptoms to safe
   read-only tool sequences.
6. **Evidence policy gate** — `_requires_generic_evidence` correctly identifies
   Brain-internal questions.
7. **Tool resolution** — `_resolve_tool` maps canonical tools and returns empty
   for unknown tools.
8. **Mandatory multi-tool detection** — `parse_mandatory_tool_requests` returns
   the required schema with `requested_by_user` and `expected` fields.
9. **Safety boundary** — Planner and mandatory-tools source files do not import
   server-starting or shell-execution utilities.

### Classification

- **C3 Planner:** PRESENT

## Part 3: Evaluator Contract (C4)

**File:** `tests/contract/test_brain_101_r3_2_evaluator_contract.py`

### Verified Contracts

1. **Evaluator criteria inventory** — `LangGraphParityRuntimeV2._evaluator_node`
   emits all required criteria:
   `answered_user_intent`, `route_correct`, `classification_correct`,
   `tool_use_adequate`, `evidence_adequate`, `memory_retrieval_adequate`,
   `governance_compliant`, `answer_complete`, `finalizer_input_complete`,
   `native_helper_parity_score`, `full_parity_score`.
2. **Direct-assistant evaluation** — A direct-assistant run is marked as
   tool-adequate without tools.
3. **Brain-evidence evaluation** — A brain-evidence run without tools or evidence
   sources fails `tool_use_adequate` and `evidence_adequate`; adding tools and
   sources makes them pass.
4. **Governance compliance** — Unapproved escalation is marked non-compliant.
5. **Evaluator source/mode** — Default source is
   `deterministic_parity_evaluator`; injected evaluator is used when supplied.
6. **Repair/replan signal** — `_repair_or_replan_node` sets `repair_needed`
   based on the evaluator result.
7. **Safety boundary** — LangGraph parity runtime source does not import
   uvicorn, FastAPI, TestClient, os.system, or requests.

### Classification

- **C4 Evaluator:** PRESENT

## Part 4: Tool Gateway Contract (C6)

**File:** `tests/contract/test_brain_101_r3_2_tool_gateway_contract.py`

### Verified Contracts

1. **Capability inventory** — `ToolGatewayV2.list_capabilities()` contains all
   required read-only and approval-required tools.
2. **Capability schema** — Every capability has `name`, `description`,
   `risk_level`, `read_only`, `requires_approval`, and `allowed_modes`.
3. **Read/write separation** — Read-only tools (`file_read`, `repo_status_read`,
   `semantic_retrieve`) are marked read-only; write tools
   (`file_patch_apply_approval_required`, `git_commit_approval_required`,
   `promotion_candidate_promote`) require approval.
4. **Read-only execution** — `repo_status_read`, `file_read`, `grep_search`
   succeed in `read_only` mode.
5. **Path blocking** — `.env` and forbidden path parts are blocked.
6. **Write-tool gating** — Write tools are blocked in `read_only` mode and
   require a valid approval token in `build` mode.
7. **Route probe rules** — Only `localhost`/`127.0.0.1` routes are allowed;
   POST is restricted to the allowlisted paths; bare relative paths are
   normalized.
8. **Smoke test allowlist** — Disallowed smoke targets are rejected.
9. **Result normalization** — `ToolCallResult` always exposes `tool_name`, `ok`,
   `result`, `blocked`, `approval_required`, `error`.
10. **Unknown tool** — Unknown tools return `error == "unknown_tool"`.
11. **Safety boundary** — Tool gateway source does not import uvicorn, FastAPI,
    TestClient, or os.system. Route probes use a bounded five-second timeout;
    timeout and transport errors return a normalized failure without retrying.

### Classification

- **C6 Tool Gateway:** PRESENT (was PARTIAL; now has behavioral and schema contract)

## Part 5: Runtime Lifecycle Contract (C1)

**File:** `tests/contract/test_brain_101_r3_2_runtime_lifecycle_contract.py`

### Verified Contracts

1. **Backend selector** — `resolve_agent_v2_backend_choice` defaults to
   `langgraph_parity` and safely falls back to `native_runtime` for invalid
   values.
2. **Production interface** — Both `NativeAgentRuntimeV2` and
   `LangGraphParityRuntimeV2` implement the required lifecycle methods
   (`create_run`, `execute_run`, `plan_run`, `pause_run`, `resume_run`,
   `cancel_run`, `list_runs`, `get_run`, `get_trace`).
3. **Run identity** — `create_run` sets `run_id`, `goal`, `mode_requested`,
   `mode_effective`, `user_id`, `status`, `agent_version`, and
   `canonical_agent`.
4. **Plan persistence** — `plan_run` transitions status to `planned` and
   persists a plan list.
5. **Lifecycle transitions** — `pause`, `resume`, and `cancel` apply the
   expected status changes.
6. **Checkpoint persistence** — Native runtime writes `checkpoint.json` on
   `_save_run`.
7. **Status constants** — `STATUSES` and `MODES` contain the canonical values.
8. **Invalid transition guard** — LangGraph parity runtime rejects transitions
   from terminal statuses.
9. **Fresh-runtime recovery** — A paused run is loaded from disk and resumed by
   a newly created runtime instance, with its checkpoint state preserved.
10. **Safety boundary** — Runtime selector and native runtime source do not
   import server-starting or shell-execution utilities.

### Classification

- **C1 Runtime Lifecycle:** PRESENT (was PARTIAL; now has behavioral lifecycle contract)

## Part 6: Preserved Invariants

This front preserves all constitutional invariants:

- Human final authority: true
- Live trading enabled: false
- Real money enabled: false
- Canonical local sync: false
- Auto-merge: false
- Deployment mode: NO_DEPLOY
- P3 denial: preserved
- Forbidden target denial: preserved

No productive runtime wiring was modified.  No environment files, CI
configuration, memory/FAISS state, trading code, financial autonomy code, or
canonical local state were touched.

## Part 7: Acceptance Criteria

1. Contract tests exist for C2 Intent Router, C3 Planner, C4 Evaluator, and
   C6 Tool Gateway.
2. A focused C1 Runtime Lifecycle contract test exists covering backend
   selection, run identity, and lifecycle transitions.
3. Each contract surface is classified as PRESENT, PARTIAL, or MISSING in this
   matrix.
4. The matrix is bound to the next R3 E2E front via the gap-resolution
   dependency map.
5. All tests are deterministic and do not require live servers, LLMs, real
   money, or real writes.
6. Human final authority and disabled live trading/real money/canonical local
   sync/auto-merge are preserved.

## Part 8: Next Front Binding

The next recommended R3 E2E front is **R3.4 Full Cognitive Pipeline E2E**
(front ID to be assigned by governance).  It depends on this contract front
and will exercise the end-to-end flow:

```text
chat -> intent (C2) -> plan (C3) -> tools (C6) -> evaluate (C4) -> finalizer (C5)
```

With these contracts in place, the E2E front can assert integration-level
behavior against stable, deterministic surface contracts rather than relying on
LLM-dependent outputs.

## Part 9: Change Record

| Cycle | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-08-12 | Created R3.2 Agent V2 cognitive pipeline contract tests and evidence matrix. | OpenCode executor |

---
*End of evidence document.*
