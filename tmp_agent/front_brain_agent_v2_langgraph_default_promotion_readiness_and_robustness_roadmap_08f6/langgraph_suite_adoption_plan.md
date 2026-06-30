# LangGraph Suite Adoption Plan — 08F6

## Layers

### Layer 1 — LangGraph OSS Runtime

- **Current status:** Integrated as opt-in backend (`LangGraphParityRuntimeV2`).
- **Value to Brain:** Durable execution, structured graph nodes, stateful workflows, future human-in-the-loop hooks.
- **Risk:** Graph complexity; package version drift; missing production methods.
- **Prerequisite:** All GATE-01 production methods implemented and tested.
- **Next front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-CONTROLLED-LOCAL-CANARY-DEFAULT-08F7` or `FRONT-BRAIN-AGENT-V2-LANGGRAPH-DEFAULT-PROMOTION-PATCH-08F7`.

### Layer 2 — LangSmith Observability / local equivalent

- **Current status:** Not integrated. Local `TraceStore` already provides per-run traces.
- **Value to Brain:** Trace export, run metrics, failure clustering, evaluation datasets.
- **Risk:** Cloud dependency; data leakage of source code or user prompts; cost.
- **Prerequisite:** Local runtime stable; explicit operator approval for any cloud tracing.
- **Next front:** Optional future front to evaluate local LangSmith self-hosting or trace export adapter.

### Layer 3 — LangGraph Platform / deployment concept

- **Current status:** Not evaluated; local Brain preferred.
- **Value to Brain:** Managed deployments, scaling, persisted checkpoints.
- **Risk:** External cloud by default violates self-hosted preference; cost; vendor lock-in.
- **Prerequisite:** Local runtime is default-stable and all gates pass.
- **Next front:** Separate evaluation front only after local default promotion succeeds.

### Layer 4 — Deep Agents / sub-agent harness concept

- **Current status:** Conceptual. Single-agent governance must be stable first.
- **Value to Brain:** Future roles: Research Agent, Memory Curator, Code Auditor, Governance Auditor, CEI/FDOT Knowledge Agent, Trading Research Agent, Strategy Risk Auditor.
- **Risk:** Swarms before single-agent governance is stable create uncontrolled action surface.
- **Prerequisite:** LangGraph is default backend; tool governance, memory boundaries, and human gates are proven.
- **Next front:** `FRONT-BRAIN-MULTI-AGENT-ROLES-ROADMAP-09A` (do not start now).

### Layer 5 — MCP / tools

- **Current status:** `ToolGatewayV2` exists; `SUPPORTED_READ_TOOLS` whitelist in LangGraph runtime.
- **Value to Brain:** Safe tool registry enables read-only, dry-run, approval-required, and forbidden tool classes.
- **Risk:** Broker/trading execution tools must never be added without separate risk-governance front.
- **Prerequisite:** Governance and human gate plan accepted.
- **Next front:** `FRONT-BRAIN-AGENT-V2-TOOL-REGISTRY-GOVERNANCE-08F6-R1` or later.

### Layer 6 — Evaluation

- **Current status:** Smoke tests exist; no formal LangGraph-vs-Native regression suite.
- **Value to Brain:** Scenario tests, golden prompts, regression journals, trace comparison, pass/fail rubric.
- **Risk:** Hidden regressions if default promotion happens without comparable evaluation.
- **Prerequisite:** LangGraph runtime completes Native parity.
- **Next front:** `FRONT-BRAIN-AGENT-V2-LANGGRAPH-EVALUATION-HARNESS-08F8` or part of 08F7 exit criteria.

## Tool classification

| Class | Tools |
|---|---|
| read-only | `repo_status_read`, `repo_history_read`, `grep_search`, `file_read`, `route_probe`, `semantic_retrieve`, `smoke_test_readonly` |
| dry-run | `promotion_candidate_validate` |
| approval-required write | `file_patch_apply_approval_required`, `git_commit_approval_required` |
| forbidden without separate risk front | `broker_order_execute`, `portfolio_rebalance_live`, `strategy_deploy_live` |

## Phase result

PHASE 4 — LangGraph suite adoption plan: **COMPLETED**

## Recorded

`2026-06-30T18:30:00+00:00`
