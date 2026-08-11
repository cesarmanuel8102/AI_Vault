# BRAIN-101-R3-1 Contract and E2E Gap Matrix

## Document Identifier

- **Front ID:** BRAIN-101-R3-1-CONTRACT-E2E-GAP-MATRIX-01
- **Cycle:** 0
- **Scope:** Documentation-only contract and E2E gap matrix against the current roadmap baseline
- **Domain:** testing_ci_recovery
- **Deployment:** NO_DEPLOY

## Purpose

This document records the complete contract and end-to-end gap matrix for R3 (Testing, CI, Recovery, and Rollback) against the current BRAIN-101 roadmap baseline. It inventories all existing contract tests and E2E tests, maps them against the R3 requirements defined in the roadmap, classifies gaps by severity, and provides a traceable foundation for subsequent R3 implementation fronts.

## Part 1: R3 Contract Definition

### 1.1 R3 Scope (from Roadmap)

R3 targets inherited from the GLM 5.2 baseline audit:

- 12+ relevant E2E tests
- 20+ relevant contract tests
- Unit tests of core modules
- Windows/Ubuntu CI coverage
- PS5.1/PS7 where applicable

### 1.2 Required Contract Surfaces

The roadmap specifies contracts for the following surfaces:

| # | Contract Surface | Description |
|---|-----------------|-------------|
| C1 | Runtime contract | Agent V2 runtime lifecycle, mission/run/room identity, checkpoint/resume |
| C2 | Intent contract | Intent routing: direct LLM, brain evidence, mixed reasoning, learning external, code task, financial research |
| C3 | Planner contract | Planner input/output schema, tool selection, context assembly |
| C4 | Evaluator contract | Evaluator criteria, evidence scoring, final answer synthesis |
| C5 | Finalizer contract | Finalizer output normalization, trace binding, response shape |
| C6 | Tool gateway contract | Tool registration, permission gating, timeout/fallback, result normalization |
| C7 | Memory service contract | Single-writer boundary, retrieve/stage/promote/rollback/integrity/rebuild/snapshot |
| C8 | Provider gateway contract | Provider selection, health, circuit breaker, timeout/retry, cost accounting |
| C9 | Execution gate contract | P3 denial, scope validation, signed approval enforcement |
| C10 | Strategy engine contract | Strategy evaluation, ranking, signal generation, edge validation |
| C11 | Financial autonomy contract | Paper-only wiring, feature flag, dry-run, audit events |
| C12 | Observability contract | Trace schema, event unification, correlation IDs, metrics, SSE/WebSocket |
| C13 | Dashboard contract | Chat UI, trace console, operator console, audit download |
| C14 | Agent Loop contract | Roadmap-aware worker, state machine, spec processing, prompt delivery |

### 1.3 Required E2E Flows

The roadmap specifies the following E2E scenarios:

| # | E2E Flow | Description |
|---|---------|-------------|
| E1 | chat -> intent -> plan -> tool -> evaluate | Full cognitive pipeline from user message to final answer |
| E2 | brain evidence retrieval | Query -> semantic search -> evidence assembly -> response |
| E3 | mixed reasoning | Multi-step reasoning combining LLM, evidence, and tool results |
| E4 | promote -> retrieve -> use | Memory promotion pipeline: stage -> approve -> promote -> retrieve -> use in answer |
| E5 | rollback | Memory rollback: promote -> snapshot -> rollback -> verify integrity |
| E6 | FAISS rebuild | Index corruption -> rebuild -> verify consistency |
| E7 | provider fallback | Primary provider failure -> fallback -> circuit breaker -> recovery |
| E8 | crash resume | Mid-mission crash -> restart -> checkpoint resume -> complete |
| E9 | Issue -> commit -> PR -> CI -> audit | Agent Loop full development lifecycle |
| E10 | auth denial | Unauthorized access -> gate denial -> audit log |
| E11 | paper order | Paper trading order lifecycle: create -> validate -> fill -> reconcile |
| E12 | kill switch | Active operation -> kill switch activation -> graceful shutdown -> state preservation |
| E13 | state corruption recovery | Corrupted state -> detection -> rollback -> integrity verification |
| E14 | cross-room isolation | Room A operation -> cannot access Room B state |
| E15 | self-improvement canary | Observe -> propose -> evaluate -> canary -> promote/reject -> memory |

## Part 2: Contract Test Inventory

### 2.1 Existing Contract Tests

| # | Test File | Surface | Classification | Notes |
|---|----------|---------|---------------|-------|
| CT01 | test_agent_v2_boundary_contracts_02.py | C5 Finalizer | PRESENT | Validates response normalizer top-level fields |
| CT02 | test_agent_loop_worker_v157_state_event_contract.py | C14 Agent Loop | PRESENT | State machine, event handling, spec processing (3403 LOC) |
| CT03 | test_agent_loop_worker_v157_codex_supervisor_contract.py | C14 Agent Loop | PRESENT | Supervisor prompt, review schema, workflow YAML |
| CT04 | test_main_router_topology_contract_12b.py | C1 Runtime | PRESENT | Static router/entrypoint inventory lock |
| CT05 | test_main_router_auth_permission_contract_12e.py | C9 Execution Gate | PRESENT | Auth/permission surface mapping |
| CT06 | test_main_router_surface_matrix_12d.py | C1 Runtime | PRESENT | Endpoint surface classification |
| CT07 | test_main_router_side_effect_boundary_12f.py | C1 Runtime | PRESENT | Mutating vs non-mutating handler tokens |
| CT08 | test_main_router_dev_surface_guard_12c.py | C9 Execution Gate | PRESENT | Dev/debug surface guard |
| CT09 | test_brain_101_r2_4_unified_governance_gate.py | C9 Execution Gate | PRESENT | Fail-closed decisions, stale/malformed rejection |
| CT10 | test_brain_101_r2_5_five_role_rbac_matrix.py | C9 Execution Gate | PRESENT | Five-role RBAC allow/deny matrix |
| CT11 | test_agent_loop_worker_r1_1_roadmap_manifest.py | C14 Agent Loop | PRESENT | Git blob hashing, manifest integrity |
| CT12 | test_agent_loop_worker_r1_2_profiles.py | C14 Agent Loop | PRESENT | Profile configuration, command generation |
| CT13 | test_agent_loop_worker_v153_base_advance.py | C14 Agent Loop | PRESENT | Git base SHA advancement |
| CT14 | test_agent_loop_worker_v153_regression.py | C14 Agent Loop | PRESENT | Process output decoding, error handling |
| CT15 | test_agent_loop_worker_v154_repair.py | C14 Agent Loop | PRESENT | WORKER_VERSION, pilot marker |
| CT16 | test_agent_loop_worker_v154_transaction_notifications.py | C14 Agent Loop | PRESENT | Spec construction, notification payloads |
| CT17 | test_agent_loop_worker_v155_quiescence_recovery.py | C14 Agent Loop | PRESENT | Recovery from dirty/ahead/non-git states |
| CT18 | test_agent_loop_worker_v156_post_merge_recovery.py | C14 Agent Loop | PRESENT | POST_MERGE_RECOVERED, token exhaustion |
| CT19 | test_agent_loop_worker_v157_lossless_transport.py | C14 Agent Loop | PRESENT | Full multiline prompt delivery |
| CT20 | test_agent_loop_worker_v157_prompt_delivery.py | C14 Agent Loop | PRESENT | Prompt construction, marker file handling |
| CT21 | test_agent_loop_worker_v157_real_cmd_quoting.py | C14 Agent Loop | PRESENT | Windows .CMD shim argument quoting |
| CT22 | test_agent_loop_worker_v157_runtime_resolution.py | C14 Agent Loop | PRESENT | Runtime path resolution |
| CT23 | test_agent_loop_worker_hardening_02.py | C14 Agent Loop | PRESENT | Error handling, input validation |
| CT24 | operator_proxy/builder_contract.test.ts | C14 Agent Loop | PRESENT | GovernedBuilder spec validation, Draft PR recovery |
| CT25 | test_main_chat_runtime_decomposition_15c.py | C13 Dashboard | PRESENT | Legacy chat route decomposition |
| CT26 | test_main_chat_service_boundary_15e.py | C13 Dashboard | PRESENT | Chat route location, service boundary |
| CT27 | test_main_routes_chat_entrypoint_split_15b.py | C13 Dashboard | PRESENT | Chat entrypoint route split |
| CT28 | test_main_routes_chat_final_move_15d.py | C13 Dashboard | PRESENT | Chat route move validation |
| CT29 | test_main_routes_chat_final_route_move_15f.py | C13 Dashboard | PRESENT | Chat route final location |
| CT30 | test_main_routes_chat_session_lifecycle_split_15a.py | C13 Dashboard | PRESENT | Session lifecycle route split |
| CT31 | test_main_routes_curated_knowledge_split_14a.py | C7 Memory | PRESENT | Curated knowledge route split |
| CT32 | test_main_routes_dashboard_shell_split_14c.py | C13 Dashboard | PRESENT | Dashboard shell route split |
| CT33 | test_main_routes_dev_debug_split_14e.py | C9 Execution Gate | PRESENT | Dev/debug diagnostic route split |
| CT34 | test_main_routes_gate_tool_split_14b.py | C6 Tool Gateway | PRESENT | Gate and Tool01 permission route split |
| CT35 | test_main_routes_governance_control_split_14c.py | C9 Execution Gate | PRESENT | Governance/control route split |
| CT36 | test_main_routes_health_status_split_13a.py | C1 Runtime | PRESENT | Health-status endpoint inventory |
| CT37 | test_main_routes_health_status_deferred_split_13c.py | C1 Runtime | PRESENT | Deferred health endpoints |
| CT38 | test_main_routes_memory_semantic_split_14b.py | C7 Memory | PRESENT | Semantic memory route split |
| CT39 | test_main_routes_provider_readonly_split_14e.py | C8 Provider | PRESENT | Provider-backed read-only route split |
| CT40 | test_main_routes_readonly_diagnostics_split_13e.py | C1 Runtime | PRESENT | Read-only diagnostics route split |
| CT41 | test_main_routes_readonly_extra_split_13f.py | C1 Runtime | PRESENT | Extra read-only route split |
| CT42 | test_main_routes_remaining_control_split_14h.py | C1 Runtime | PRESENT | Controlled diagnostics/ops route split |
| CT43 | test_main_routes_startup_state_adapter_13b.py | C1 Runtime | PRESENT | Startup state adapter |
| CT44 | test_main_routes_strategy_readonly_split_14f.py | C10 Strategy | PRESENT | Strategy engine route split |
| CT45 | test_main_routes_trace_streaming_split_14d.py | C12 Observability | PRESENT | Agent trace/streaming route split |
| CT46 | test_main_routes_validators_observability_split_13d.py | C12 Observability | PRESENT | Validator observability endpoints |
| CT47 | test_main_router_low_risk_shell_move_16b.py | C1 Runtime | PRESENT | Low-risk shell route move |
| CT48 | test_main_router_residual_surface_audit_16a.py | C1 Runtime | PRESENT | Residual surface audit |

### 2.2 Contract Test Gap Analysis

| Contract Surface | Required | Existing | Gap | Severity |
|-----------------|----------|----------|-----|----------|
| C1 Runtime | Yes | CT04, CT06, CT07, CT36, CT37, CT40, CT41, CT42, CT43, CT47, CT48 | Partial: static topology contracts exist; no runtime lifecycle, checkpoint/resume, or mission identity contract | MEDIUM |
| C2 Intent | Yes | None | Missing: no intent router contract exists | HIGH |
| C3 Planner | Yes | None | Missing: no planner input/output schema contract exists | HIGH |
| C4 Evaluator | Yes | None | Missing: no evaluator criteria or evidence scoring contract exists | HIGH |
| C5 Finalizer | Yes | CT01 | Partial: response normalizer contract exists; no trace binding or full response shape contract | MEDIUM |
| C6 Tool Gateway | Yes | CT34 | Partial: route split contract exists; no tool registration, permission gating, timeout/fallback, or result normalization contract | HIGH |
| C7 Memory Service | Yes | CT31, CT38 | Partial: route split contracts exist; no single-writer boundary, promote/rollback/integrity/rebuild/snapshot contract | CRITICAL |
| C8 Provider Gateway | Yes | CT39 | Partial: route split contract exists; no provider selection, health, circuit breaker, or cost accounting contract | HIGH |
| C9 Execution Gate | Yes | CT05, CT08, CT09, CT10, CT33, CT35 | Partial: auth surface, dev guard, unified gate, and RBAC contracts exist; no P3 denial, scope validation, or signed approval enforcement contract | MEDIUM |
| C10 Strategy Engine | Yes | CT44 | Partial: route split contract exists; no strategy evaluation, ranking, or signal generation contract | HIGH |
| C11 Financial Autonomy | Yes | None | Missing: no paper-only wiring, feature flag, or audit events contract exists | HIGH |
| C12 Observability | Yes | CT45, CT46 | Partial: trace/streaming route split and validator observability contracts exist; no trace schema versioning, event unification, correlation IDs, or metrics contract | MEDIUM |
| C13 Dashboard | Yes | CT25, CT26, CT27, CT28, CT29, CT30, CT32 | Partial: chat and dashboard route split contracts exist; no operator console, audit download, or full UI contract | MEDIUM |
| C14 Agent Loop | Yes | CT02, CT03, CT11-CT24 | Present: comprehensive agent loop worker contracts (v1.5.3-v1.5.7) and operator proxy contract exist | LOW |

### 2.3 Contract Test Summary

| Metric | Count |
|--------|-------|
| Total existing contract tests | 48 |
| Roadmap minimum target | 20+ |
| Surfaces with full coverage | 1 (C14 Agent Loop) |
| Surfaces with partial coverage | 10 |
| Surfaces with no coverage | 4 (C2 Intent, C3 Planner, C4 Evaluator, C11 Financial Autonomy) |
| Critical gaps | 1 (C7 Memory Service) |
| High-severity gaps | 6 (C2, C3, C4, C6, C8, C10, C11) |
| Medium-severity gaps | 5 (C1, C5, C9, C12, C13) |
| Low-severity gaps | 1 (C14) |

## Part 3: E2E Test Inventory

### 3.1 Existing E2E Tests

| # | Test File | E2E Flow | Classification | Notes |
|---|----------|---------|---------------|-------|
| ET01 | smoke_front_test_01_minimal_e2e_pipeline.py | E9 | PRESENT | Minimal E2E pipeline: controlled input, governance check, dry-run, evidence |
| ET02 | smoke_front_real_plan_01_controlled_e2e_write_plan.py | E9 | PRESENT | Controlled real E2E write plan validation |
| ET03 | smoke_front_chat_ui_e2e_failure_diagnostic_01.py | E1 | PRESENT | Chat UI E2E failure diagnostic, canonical safety baseline |
| ET04 | test_e2e_self_learning_loop_nontrading_01.py | E15 | PRESENT | Non-trading self-learning loop: source input, staging, validation, retrieval, finalizer, governance, rollback |
| ET05 | test_ingestion_controlled_e2e_09a.py | E4 | PRESENT | Ingestion controlled E2E: 3 curated candidates promoted with approval token |
| ET06 | test_agent_trace_sse_e2e.py | E12 | PRESENT | SSE trace redaction: emit, sanitize, persist, broadcast |
| ET07 | test_autonomy_e2e_memory_tool_fallback_11c.py | E7 | PRESENT | Autonomy E2E memory tool fallback with SCVL gates |

### 3.2 E2E Gap Analysis

| E2E Flow | Required | Existing | Gap | Severity |
|----------|----------|----------|-----|----------|
| E1 chat->intent->plan->tool->evaluate | Yes | ET03 | Partial: chat UI failure diagnostic exists; no full cognitive pipeline E2E with intent routing, planner, tool execution, and evaluator | CRITICAL |
| E2 brain evidence retrieval | Yes | None | Missing: no E2E for query -> semantic search -> evidence assembly -> response | HIGH |
| E3 mixed reasoning | Yes | None | Missing: no E2E for multi-step reasoning combining LLM, evidence, and tool results | HIGH |
| E4 promote->retrieve->use | Yes | ET05 | Partial: ingestion controlled E2E exists; no full promote->retrieve->use-in-answer E2E | HIGH |
| E5 rollback | Yes | None | Missing: no E2E for promote -> snapshot -> rollback -> verify integrity | CRITICAL |
| E6 FAISS rebuild | Yes | None | Missing: no E2E for index corruption -> rebuild -> verify consistency | HIGH |
| E7 provider fallback | Yes | ET07 | Partial: autonomy memory tool fallback exists; no primary provider failure -> fallback -> circuit breaker -> recovery E2E | HIGH |
| E8 crash resume | Yes | None | Missing: no E2E for mid-mission crash -> restart -> checkpoint resume -> complete | CRITICAL |
| E9 Issue->commit->PR->CI->audit | Yes | ET01, ET02 | Partial: minimal pipeline and write plan E2E exist; no full Agent Loop development lifecycle E2E | MEDIUM |
| E10 auth denial | Yes | None | Missing: no E2E for unauthorized access -> gate denial -> audit log | HIGH |
| E11 paper order | Yes | None | Missing: no E2E for paper trading order lifecycle | HIGH |
| E12 kill switch | Yes | ET06 | Partial: SSE trace E2E exists; no active operation -> kill switch -> graceful shutdown -> state preservation E2E | HIGH |
| E13 state corruption recovery | Yes | None | Missing: no E2E for corrupted state -> detection -> rollback -> integrity verification | CRITICAL |
| E14 cross-room isolation | Yes | None | Missing: no E2E for Room A operation -> cannot access Room B state | HIGH |
| E15 self-improvement canary | Yes | ET04 | Partial: self-learning loop E2E exists; no full observe->propose->evaluate->canary->promote/reject->memory E2E | MEDIUM |

### 3.3 E2E Test Summary

| Metric | Count |
|--------|-------|
| Total existing E2E tests | 7 |
| Roadmap minimum target | 12+ |
| Flows with full coverage | 0 |
| Flows with partial coverage | 6 (E1, E4, E7, E9, E12, E15) |
| Flows with no coverage | 9 (E2, E3, E5, E6, E8, E10, E11, E13, E14) |
| Critical gaps | 4 (E1, E5, E8, E13) |
| High-severity gaps | 9 (E2, E3, E4, E6, E7, E10, E11, E12, E14) |
| Medium-severity gaps | 2 (E9, E15) |

## Part 4: CI and Infrastructure Gap Analysis

### 4.1 Existing CI Workflows

| Workflow | Platform | Status | Notes |
|----------|----------|--------|-------|
| phase1-ci | Windows | PRESENT | Core CI: lint, typecheck, unit tests |
| nontrading-smoke-regression | Ubuntu | PRESENT | Non-trading smoke and regression tests |
| agent-loop-worker-contract | Windows | PRESENT | Agent loop worker contract tests |
| operator-proxy-contract | Ubuntu | PRESENT | Operator proxy contract tests |

### 4.2 CI Gap Analysis

| Gap | Severity | Description |
|-----|----------|-------------|
| No dedicated E2E CI workflow | HIGH | E2E tests are not run in a dedicated CI pipeline; they are scattered across smoke workflows |
| No cross-platform E2E coverage | MEDIUM | E2E tests lack explicit Windows/Ubuntu parity validation |
| No recovery/rollback CI | HIGH | No CI workflow validates crash recovery, state rollback, or FAISS rebuild scenarios |
| No performance/soak CI | MEDIUM | No CI workflow for performance regression or soak testing |
| No security adversarial CI | HIGH | No CI workflow for adversarial security tests (prompt injection, path traversal, replay) |

## Part 5: Unit Test Coverage Gap Analysis

### 5.1 Core Module Coverage

| Module | Unit Tests | Gap | Severity |
|--------|-----------|-----|----------|
| session.py (3052 LOC) | ~12 test files | Partial: session routing, command handler, curated render, fastpaths, formatters, memory state, observability, query predicates, response hygiene, tool01 gateway covered; session_chat, session_governance, session_tools not covered | HIGH |
| main.py (2164 LOC) | Route split contracts only | Partial: static topology contracts exist; no runtime behavior unit tests | HIGH |
| agent/tools.py (3519 LOC) | None | Missing: legacy tools module has no dedicated unit tests | CRITICAL |
| agent/loop.py (2912 LOC) | None | Missing: legacy loop module has no dedicated unit tests | CRITICAL |
| Agent V2 kernel | ~40 smoke tests | Partial: LangGraph parity, dashboard, chat, trace covered; planner, evaluator, finalizer unit tests missing | HIGH |
| Memory/semantic | ~20 unit tests | Partial: adapter, FAISS, decision gate, evidence, rollback simulation covered; MemoryService boundary tests missing | HIGH |
| Financial autonomy | Compile contract only | Missing: no runtime unit tests (intentionally blocked) | MEDIUM |
| Trading modules | Scattered | Partial: backtest gate, risk contract covered; PortfolioManager, Compliance absent | HIGH |

## Part 6: Consolidated Gap Matrix

### 6.1 Critical Gaps (Block R3 Closure)

| ID | Gap | Category | Required By | Description |
|----|-----|----------|-------------|-------------|
| G-C1 | Memory Service contract (C7) | Contract | R6 | No single-writer boundary, promote/rollback/integrity/rebuild/snapshot contract exists |
| G-C2 | Full cognitive pipeline E2E (E1) | E2E | R5 | No E2E for chat->intent->plan->tool->evaluate |
| G-C3 | Rollback E2E (E5) | E2E | R6 | No E2E for promote->snapshot->rollback->verify integrity |
| G-C4 | Crash resume E2E (E8) | E2E | R5 | No E2E for mid-mission crash->restart->checkpoint resume->complete |
| G-C5 | State corruption recovery E2E (E13) | E2E | R3 | No E2E for corrupted state->detection->rollback->integrity verification |
| G-C6 | Legacy tools.py unit tests | Unit | R4 | 3519 LOC legacy module with zero dedicated unit tests |
| G-C7 | Legacy loop.py unit tests | Unit | R4 | 2912 LOC legacy module with zero dedicated unit tests |

### 6.2 High-Severity Gaps

| ID | Gap | Category | Required By | Description |
|----|-----|----------|-------------|-------------|
| G-H1 | Intent router contract (C2) | Contract | R5 | No intent router contract exists |
| G-H2 | Planner contract (C3) | Contract | R5 | No planner input/output schema contract exists |
| G-H3 | Evaluator contract (C4) | Contract | R5 | No evaluator criteria or evidence scoring contract exists |
| G-H4 | Tool gateway contract (C6) | Contract | R5 | No tool registration, permission gating, timeout/fallback contract |
| G-H5 | Provider gateway contract (C8) | Contract | R8 | No provider selection, health, circuit breaker, cost accounting contract |
| G-H6 | Strategy engine contract (C10) | Contract | R12 | No strategy evaluation, ranking, signal generation contract |
| G-H7 | Financial autonomy contract (C11) | Contract | R11 | No paper-only wiring, feature flag, audit events contract |
| G-H8 | Brain evidence retrieval E2E (E2) | E2E | R6 | No E2E for query->semantic search->evidence assembly->response |
| G-H9 | Mixed reasoning E2E (E3) | E2E | R5 | No E2E for multi-step reasoning combining LLM, evidence, and tools |
| G-H10 | Promote->retrieve->use E2E (E4) | E2E | R6 | No full promote->retrieve->use-in-answer E2E |
| G-H11 | FAISS rebuild E2E (E6) | E2E | R6 | No E2E for index corruption->rebuild->verify consistency |
| G-H12 | Provider fallback E2E (E7) | E2E | R8 | No primary provider failure->fallback->circuit breaker->recovery E2E |
| G-H13 | Auth denial E2E (E10) | E2E | R2 | No E2E for unauthorized access->gate denial->audit log |
| G-H14 | Paper order E2E (E11) | E2E | R15 | No E2E for paper trading order lifecycle |
| G-H15 | Kill switch E2E (E12) | E2E | R16 | No active operation->kill switch->graceful shutdown E2E |
| G-H16 | Cross-room isolation E2E (E14) | E2E | R2 | No E2E for Room A operation->cannot access Room B state |
| G-H17 | Dedicated E2E CI workflow | CI | R3 | E2E tests not run in dedicated CI pipeline |
| G-H18 | Recovery/rollback CI | CI | R3 | No CI workflow for crash recovery, state rollback, FAISS rebuild |
| G-H19 | Security adversarial CI | CI | R2 | No CI workflow for adversarial security tests |
| G-H20 | session.py runtime unit tests | Unit | R4 | No runtime behavior unit tests for main.py and session.py core logic |
| G-H21 | Agent V2 planner/evaluator unit tests | Unit | R5 | Planner, evaluator, finalizer unit tests missing |
| G-H22 | MemoryService boundary unit tests | Unit | R6 | MemoryService boundary tests missing |
| G-H23 | Trading module unit tests | Unit | R12 | PortfolioManager, Compliance unit tests absent |

### 6.3 Medium-Severity Gaps

| ID | Gap | Category | Required By | Description |
|----|-----|----------|-------------|-------------|
| G-M1 | Runtime lifecycle contract (C1) | Contract | R5 | No runtime lifecycle, checkpoint/resume, or mission identity contract |
| G-M2 | Finalizer trace binding contract (C5) | Contract | R5 | No trace binding or full response shape contract |
| G-M3 | Execution gate P3/scope contract (C9) | Contract | R2 | No P3 denial, scope validation, or signed approval enforcement contract |
| G-M4 | Observability unification contract (C12) | Contract | R7 | No trace schema versioning, event unification, correlation IDs, metrics contract |
| G-M5 | Dashboard full UI contract (C13) | Contract | R18 | No operator console, audit download, or full UI contract |
| G-M6 | Agent Loop full lifecycle E2E (E9) | E2E | R1 | No full Issue->commit->PR->CI->audit E2E |
| G-M7 | Self-improvement canary E2E (E15) | E2E | R10 | No full observe->propose->evaluate->canary->promote/reject->memory E2E |
| G-M8 | Cross-platform E2E parity | CI | R3 | E2E tests lack explicit Windows/Ubuntu parity validation |
| G-M9 | Performance/soak CI | CI | R3 | No CI workflow for performance regression or soak testing |
| G-M10 | Financial autonomy unit tests | Unit | R11 | No runtime unit tests (intentionally blocked, deferred to R11) |

## Part 7: Gap Resolution Roadmap

### 7.1 Recommended R3 Sub-Fronts

Based on the gap analysis, the following sub-fronts are recommended for R3 closure:

| Sub-Front | Priority | Gaps Addressed | Dependencies | Estimated Effort |
|-----------|----------|---------------|-------------|-----------------|
| R3.2 Agent V2 cognitive pipeline contracts | HIGH | G-H1, G-H2, G-H3, G-H4, G-M1, G-M2 | R2.5 | Contract tests for intent, planner, evaluator, tool gateway |
| R3.3 Memory and recovery E2E | CRITICAL | G-C1, G-C3, G-C5, G-H8, G-H10, G-H11 | R6 (partial) | Memory service contract + rollback/rebuild/recovery E2E |
| R3.4 Full cognitive pipeline E2E | CRITICAL | G-C2, G-H9 | R3.2 | chat->intent->plan->tool->evaluate E2E |
| R3.5 Crash resilience E2E | CRITICAL | G-C4, G-H15 | R3.3 | Crash resume + kill switch E2E |
| R3.6 Provider and auth E2E | HIGH | G-H12, G-H13, G-H16 | R2.5, R8 | Provider fallback + auth denial + cross-room isolation E2E |
| R3.7 Legacy module unit tests | CRITICAL | G-C6, G-C7 | R4 | Unit tests for tools.py and loop.py |
| R3.8 Core runtime unit tests | HIGH | G-H20, G-H21, G-H22 | R4, R5 | Unit tests for session.py, Agent V2 planner/evaluator, MemoryService |
| R3.9 CI hardening | HIGH | G-H17, G-H18, G-H19, G-M8, G-M9 | R3.3-R3.6 | Dedicated E2E CI, recovery CI, security CI, cross-platform parity |
| R3.10 Financial and trading contracts | HIGH | G-H7, G-H14, G-H23 | R11, R12, R15 | Financial autonomy + paper order + trading unit tests |
| R3.11 Strategy and observability contracts | MEDIUM | G-H6, G-M4, G-M5 | R7, R12 | Strategy engine + observability + dashboard contracts |
| R3.12 Self-improvement and Agent Loop E2E | MEDIUM | G-M6, G-M7 | R10 | Agent Loop full lifecycle + self-improvement canary E2E |

### 7.2 Dependency Order

```text
R3.1 (this document: gap matrix)
  |
  +-- R3.2 (Agent V2 cognitive pipeline contracts)
  |     |
  |     +-- R3.4 (full cognitive pipeline E2E)
  |
  +-- R3.3 (memory and recovery E2E)
  |     |
  |     +-- R3.5 (crash resilience E2E)
  |
  +-- R3.6 (provider and auth E2E)
  +-- R3.7 (legacy module unit tests)
  +-- R3.8 (core runtime unit tests)
  |
  +-- R3.9 (CI hardening) [depends on R3.3-R3.6]
  +-- R3.10 (financial and trading contracts)
  +-- R3.11 (strategy and observability contracts)
  +-- R3.12 (self-improvement and Agent Loop E2E)
```

## Part 8: Preserved Invariants

This document preserves all constitutional invariants:

- Human final authority: true
- Live trading enabled: false
- Real money enabled: false
- Canonical local sync: false
- Auto-merge: false
- Deployment mode: NO_DEPLOY
- P3 denial: preserved
- Forbidden target denial: preserved

No runtime code, tests, governance logic, memory, FAISS, trading, financial autonomy, CI, environment files, or canonical local state were modified in the creation of this document.

## Part 9: Acceptance Criteria

1. A complete contract gap matrix is produced covering all 14 contract surfaces defined in the R3 roadmap.
2. A complete E2E gap matrix is produced covering all 15 E2E flows defined in the R3 roadmap.
3. CI and unit test coverage gaps are identified and classified by severity.
4. A prioritized resolution roadmap with dependency ordering is provided.
5. All constitutional invariants are preserved.
6. This evidence document is the sole modified artifact in the allowlisted path.

## Traceability

- Roadmap source: `docs/roadmap/BRAIN_101_ROADMAP.md` (R3 section)
- Manifest source: `docs/roadmap/BRAIN_101_MANIFEST.json` (R3.1 automation block)
- Scorecard source: `docs/roadmap/BRAIN_101_SCORECARD.json` (testing_ci_recovery domain)
- Evidence type: Documentation-only contract and E2E gap matrix
- Validated against: Current HEAD baseline

## Change Record

| Cycle | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-08-11 | Initial contract and E2E gap matrix created against current roadmap baseline. | OpenCode codex_control_plane executor |

---
*End of evidence document.*
