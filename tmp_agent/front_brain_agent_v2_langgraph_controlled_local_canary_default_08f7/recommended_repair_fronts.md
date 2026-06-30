# Phase 10 — Recommended Repair Fronts

## Priority 1 — `FRONT-BRAIN-AGENT-V2-LANGGRAPH-PRODUCTION-METHOD-PARITY-08F7-R1`
- **Mission:** Close **GATE-01** by making `LangGraphParityRuntimeV2` production-method-parity with `NativeAgentRuntimeV2`.
- **Scope:** Source-code changes limited to `langgraph_parity_runtime.py` and new parity tests.
- **Must not:**
  - Change the default backend in `runtime.py`.
  - Promote LangGraph to global default.
  - Modify `.env` or secrets.
  - Touch memory/FAISS, trading, journal, or promotion queues.
- **Deliverables:**
  1. Implement real `plan_run` using `build_plan` and `ToolGatewayV2` semantic binding.
  2. Implement `pause_run` that stops/resumes graph thread and checkpoints state.
  3. Implement `resume_run` that restores graph thread from checkpoint and continues.
  4. Implement `cancel_run` that cleanly terminates graph execution.
  5. Add parity tests comparing both runtimes for create, plan, execute, pause, resume, cancel, trace, list.
  6. Run parity tests under `AGENT_V2_BACKEND=langgraph` and under default native backend.
- **Success criteria:** GATE-01 moves from OPEN to PASS; 08F7 smoke tests still pass; native default unchanged.

## Priority 2 — `FRONT-BRAIN-AGENT-V2-LANGGRAPH-DASHBOARD-FALLBACK-OBSERVABILITY-08F7-R2`
- **Mission:** Close **GATE-04** by exposing backend fallback metadata in dashboard status.
- **Scope:** Source-code change limited to `dashboard_routes.py` and dashboard smoke tests.
- **Deliverables:**
  1. Extend `_agent_v2_snapshot()` to return `backend_fallback_used` and `backend_fallback_reason`.
  2. Add dashboard smoke test asserting fallback reason is visible when fallback occurs.
  3. Ensure no token leakage and route remains read-only.
- **Success criteria:** `/brain-dashboard/status` exposes fallback fields; smoke tests pass.

## Priority 3 — `FRONT-BRAIN-AGENT-V2-RUNTIME-BUDGET-AND-MODEL-ROUTING-GOVERNANCE-08F7-R3`
- **Mission:** Close **GATE-08** by documenting and enforcing explicit cost/step/model-routing policy.
- **Scope:** Source-code and documentation changes in governance/runtime config.
- **Deliverables:**
  1. Document per-step budget and max-step policy.
  2. Add model-routing policy (`PRIMARY_KIMI_MODEL`, fallback ordering, provider degradation rules).
  3. Add smoke tests asserting budget/step limits for both backends.
- **Success criteria:** GATE-08 moves from PARTIAL to PASS; policy visible in code/docs and enforced by tests.

## Ordering rationale
- R1 is mandatory before any default-promotion PR because GATE-01 is the only hard blocker.
- R2 and R3 can be worked in parallel once R1 is scoped, but both are required before global default promotion.

## Next
Proceed to Phase 11 — Final Report.
