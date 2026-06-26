# External Component Inventory — Build-vs-Adapt Recon

## 1. Agent Orchestration

### Current Internal: NativeAgentRuntimeV2
- Real runtime with plan, execute, tool calls, memory retrieval, finalization
- Status: Working, proven in tests
- Complexity: Low (single Python class, ~500 lines)
- Dependency weight: None (stdlib + local modules)
- Data privacy: 100% local
- Maintenance risk: Low (we own the code)

### External Option: LangGraph
- Repo: https://github.com/langchain-ai/langgraph
- Stars: 35.8k | Forks: 6k | Latest: 1.2.6 (Jun 2026)
- License: MIT
- Features: Stateful agents, durable execution, human-in-the-loop, memory, debugging
- Current use in project: Facade only (LangGraphAgentRuntimeV2 extends NativeAgentRuntimeV2 but never invokes the graph in canonical path)
- Local/offline feasibility: Yes (pip installable)
- Windows feasibility: Yes
- Python/FastAPI compatibility: Yes
- Dependency weight: Medium (langgraph + langchain + pydantic + many transitive deps)
- Security risk: Low-Medium (widely used, but adds attack surface)
- Data privacy risk: Low if self-hosted, Medium if using LangSmith cloud
- Integration complexity: High (requires rewriting plan/execute/tool/final nodes as real graph nodes)
- Quality advantage: Human-in-the-loop, durable execution, visual debugging via LangSmith
- Time saved: Negative (would require major refactor, not savings)
- **Decision: REJECT for now**
- **Reason**: Native runtime is working. LangGraph is currently a facade that falsely claims to be the backend. Integrating it for real would require a major refactor with no immediate benefit. Can be revisited if human-in-the-loop or durable execution become requirements.

## 2. RBAC / Policy

### Current Internal: api_security.py
- Simple role-based access (VIEWER, OPERATOR, ADMIN)
- Token-based auth with `require_strict_operator_access`
- Status: Working, tested, minimal
- Complexity: Very low (~150 lines)
- Dependency weight: None
- Data privacy: 100% local

### External Option: PyCasbin
- Repo: https://github.com/apache/casbin-pycasbin
- Stars: 1.7k | Forks: 215 | Latest: v2.8.0 (Feb 2026)
- License: Apache-2.0
- Features: ACL, RBAC, ABAC, RESTful, Deny-override, Priority models
- Local/offline feasibility: Yes
- Windows feasibility: Yes
- Python/FastAPI compatibility: Yes
- Dependency weight: Low (single package, few deps)
- Security risk: Low (Apache project, mature)
- Data privacy risk: Low
- Integration complexity: Medium (need to adapt current routes to Casbin enforcer)
- Quality advantage: More flexible policy models, policy persistence adapters
- Time saved: Low (current RBAC is sufficient for now)
- **Decision: DEFER**
- **Reason**: Current RBAC is minimal but sufficient. PyCasbin would add flexibility but also complexity. Revisit if we need ABAC or complex policy rules.

### External Option: OPA (Open Policy Agent)
- Not evaluated in detail (would require Go binary or sidecar)
- **Decision: REJECT**
- **Reason**: Overkill for current needs. Adds Go dependency and sidecar complexity.

## 3. Observability / Tracing

### Current Internal: TraceStore (trace.py)
- JSONL-based trace events per run
- Events: run_created, plan_created, tool_call_started, tool_call_completed, memory_retrieval, final_answer_created, run_completed
- Sanitizes raw CoT markers
- Status: Working, local files only
- Complexity: Very low (~30 lines)
- Dependency weight: None
- Data privacy: 100% local

### External Option: OpenTelemetry Python
- Repo: https://github.com/open-telemetry/opentelemetry-python
- Stars: 2.5k | Forks: 919 | Latest: 1.43.0/0.64b0 (Jun 2026)
- License: Apache-2.0
- Features: Traces (stable), Metrics (stable), Logs (dev), standard OTLP export
- Local/offline feasibility: Yes (can export to local collector or file)
- Windows feasibility: Yes
- Python/FastAPI compatibility: Yes (has FastAPI instrumentation)
- Dependency weight: Medium-High (multiple packages: api, sdk, exporter, semantic conventions)
- Security risk: Low
- Data privacy risk: Low if local collector, Medium if sending to SaaS backend
- Integration complexity: Medium (need to instrument all routes and runtime methods)
- Quality advantage: Standard format, interoperable with many backends, spans/metrics/logs unified
- Time saved: Low for now (we already have traces)
- **Decision: DEFER**
- **Reason**: Our JSONL trace model is sufficient for V1. OpenTelemetry would be valuable if we need distributed tracing or integrate with external observability platforms. Good candidate for future front.

### External Option: Langfuse
- Repo: https://github.com/langfuse/langfuse
- Stars: 29.8k | Forks: 3.1k
- License: MIT (core), with ee folder for enterprise features
- Features: LLM observability, prompt management, evaluations, datasets, playground
- Local/offline feasibility: Yes (self-host via Docker Compose)
- Windows feasibility: Yes (Docker)
- Python/FastAPI compatibility: Yes (Python SDK available)
- Dependency weight: High (requires Postgres, ClickHouse, Redis, Redis worker, web app)
- Security risk: Low-Medium (self-hosted = low, but complex stack)
- Data privacy risk: Low if self-hosted, Medium if using Langfuse Cloud
- Integration complexity: High (requires running separate services)
- Quality advantage: Purpose-built for LLM apps, trace visualization, evals, prompt management
- Time saved: Negative for now (would require significant setup and integration)
- **Decision: REJECT for now**
- **Reason**: Too heavy for V1. Our simple JSONL traces + custom dashboard are lighter. Revisit when we need advanced LLM-specific observability, evals, or prompt management.

## 4. Visual Trace Console

### Current Internal: /v2/agent/runs/{run_id}/trace endpoint + dashboard trace proxy
- Returns JSON trace events
- Dashboard renders trace (if implemented)
- Status: Endpoint exists, UI connection needs verification in Phase 3
- Complexity: Low
- Dependency weight: None

### External Option: LangSmith (LangChain)
- Part of LangGraph/LangChain ecosystem
- **Decision: REJECT**
- **Reason**: Requires LangGraph integration. Since we rejected LangGraph, LangSmith is not applicable.

### External Option: Custom FastAPI/HTML/JS
- **Decision: BUILD_INTERNAL**
- **Reason**: We already have the trace endpoint. A simple HTML/JS dashboard can consume it. No external dependencies needed.

## 5. LLM Eval / Test Harness

### Current Internal: Smoke tests + deterministic assertions
- `tests/smoke/test_agent_v2_*.py` — functional tests
- Status: Working, covers auth, governance, tool gates, memory hygiene
- Complexity: Low
- Dependency weight: None

### External Option: promptfoo
- Open source LLM testing platform
- **Decision: DEFER**
- **Reason**: Our smoke tests are sufficient for V1. External eval frameworks add value for model benchmarking but not for functional correctness.

## 6. Dashboards / UI

### Current Internal: brain-dashboard routes (8090/8091/8092)
- FastAPI serving HTML/JS
- Status: Partial (exists but may need verification)

### External Option: Streamlit
- **Decision: REJECT**
- **Reason**: Would require separate process and adds dependency. Current FastAPI static files are simpler.

### External Option: Gradio
- **Decision: REJECT**
- **Reason**: Same as Streamlit — adds dependency and separate process.

## Summary Table

| Component | Current | External Option | Decision | Reason |
|-----------|---------|----------------|----------|--------|
| Agent Orchestration | NativeAgentRuntimeV2 | LangGraph | **REJECT** | Facade only; real integration requires major refactor |
| RBAC/Policy | api_security.py | PyCasbin | **DEFER** | Current RBAC sufficient |
| Observability/Tracing | TraceStore (JSONL) | OpenTelemetry | **DEFER** | JSONL sufficient; OTel good future candidate |
| LLM Observability | TraceStore | Langfuse | **REJECT** | Too heavy for V1 |
| Visual Trace Console | /v2/agent/runs/{run_id}/trace | Any external | **BUILD_INTERNAL** | Endpoint exists; add simple UI |
| LLM Eval | Smoke tests | promptfoo | **DEFER** | Smoke tests sufficient |
| Dashboards/UI | FastAPI static | Streamlit/Gradio | **BUILD_INTERNAL** | Current approach lighter |

## Decision Gates

| Gate | Default | Evidence-based Decision | Reason |
|------|---------|------------------------|--------|
| should_install_external_dependencies_now | false | **false** | No external component justified for V1 |
| should_keep_langgraph | true | **false** | Removed from critical path (Phase 1) |
| should_integrate_langgraph_deeper | false | **false** | Not worth the refactor now |
| should_demote_langgraph_to_wrapper | false | **true (done)** | Removed from critical path in Phase 1 |
| should_use_opentelemetry_schema | false | **false** | JSONL traces sufficient |
| should_use_langfuse_now | false | **false** | Too heavy for V1 |
| should_build_visual_trace_local_v1 | true | **true** | Endpoint exists; add minimal UI |
| should_adapt_external_visual_trace_component | false | **false** | No external component better than local build |
| should_start_09d_before_visualtrace_closeout | false | **false** | Visual trace should be closed first |
| should_mass_ingest_now | false | **false** | Explicitly forbidden |
| should_touch_trading_code_now | false | **false** | Explicitly forbidden |
