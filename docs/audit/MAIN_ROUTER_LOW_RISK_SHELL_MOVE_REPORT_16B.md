# MAIN ROUTER LOW-RISK SHELL MOVE REPORT 16B

**Status:** LOW_RISK_SHELL_MOVE_COMPLETED

**Front:** FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B

**Scope:** Move read-only / dry-run / thin refresh shell endpoints from `tmp_agent/brain_v9/main.py` into focused routers, leaving all strong mutations, trading/QC/IBKR, memory/FAISS, and runtime-state surfaces in `main.py` for later fronts.

---

## Base

- Repository: `C:\AI_VAULT_CANONICAL`
- Branch: `codex/own-capital-sustainable-return`
- HEAD initial: `759edfb`
- `main.py` endpoints before: 50
- `main.py` endpoints after: 30
- `main.py` lines before: 2441
- `main.py` lines after: 2164

---

## Routers Created

| Router | File |
|--------|------|
| Code Mutation Read-Only | `tmp_agent/brain_v9/routes/code_mutation_readonly_routes.py` |
| Chat Excellence Read-Only | `tmp_agent/brain_v9/routes/chat_excellence_readonly_routes.py` |
| Autonomy Read-Only Shell | `tmp_agent/brain_v9/routes/autonomy_readonly_shell_routes.py` |
| Dev / Pipeline Audit | `tmp_agent/brain_v9/routes/dev_pipeline_audit_routes.py` |
| Governance Refresh Shell | `tmp_agent/brain_v9/routes/governance_refresh_shell_routes.py` |

---

## Routes Moved

**Total routes moved: 18**

### Batch A — Code Mutation Read-Only (2)

- `GET /brain/mutations`
- `GET /brain/mutations/{mutation_id}`

### Batch B — Chat Excellence Read-Only / Dry-Run (7)

- `GET /brain/chat_excellence/status`
- `GET /brain/chat_excellence/proposals`
- `GET /brain/learning/proposals`
- `GET /brain/chat_excellence/proposals/{proposal_id}`
- `POST /brain/chat_excellence/proposals/{proposal_id}/dry_run`
- `GET /brain/chat_excellence/proposals/{proposal_id}/health_gate_log`
- `GET /brain/chat_excellence/proposals/{proposal_id}/evaluation_status`

### Batch C — Autonomy / Pipeline / Audit Shell (3)

- `GET /brain/autonomy/next-actions`
- `GET /brain/pipeline-health`
- `POST /brain/metacognition/audit`

### Batch D — Governance Refresh Shell (6)

- `POST /brain/post-bl-roadmap/refresh`
- `POST /brain/meta-improvement/refresh`
- `POST /brain/chat-product/refresh`
- `POST /brain/autonomous-governance-eval/refresh`
- `POST /brain/utility-governance/refresh`
- `POST /brain/roadmap/governance/refresh`

---

## Deferred Routes (intentionally left in main.py)

| Route | Reason |
|-------|--------|
| `POST /brain/maintenance/action` | Needs helper extraction from `_brain_maintenance_action_result`. |
| `POST /brain/learned/patterns/{pattern_id}/disable` | State mutation. |
| `DELETE /brain/learned/patterns/{pattern_id}` | State mutation. |
| `POST /brain/learned/test_simulate` | Full meta-loop with session + LLM + sandbox + persistence. |
| `POST /brain/mutations/{mutation_id}/rollback` | File-system rollback. |
| `POST /brain/mutations/test_apply` | Direct code mutation. |
| `POST /brain/scheduler/alerts/ack` | Mutates scheduler alert state. |
| `POST /brain/proactive/run/{task_id}` | Mutates scheduler queue. |
| `POST /brain/llm/circuit_breaker/reset` | Mutates LLM manager circuit state. |
| `POST /brain/chat_excellence/proposals/{proposal_id}/reject` | Proposal status mutation. |
| `POST /brain/chat_excellence/proposals/{proposal_id}/apply` | Patch apply with optional restart. |
| `POST /brain/chat_excellence/proposals/{proposal_id}/rollback` | File restore. |
| `POST /brain/chat_excellence/proposals/apply_batch` | **Bulk patch apply / CONTROL_MUTATION — NOT low-risk; defer to 16D.** |
| `POST /brain/chat_excellence/proposals/evaluate` | May auto-rollback. |
| `POST /brain/utility/refresh` | Multi-helper orchestration still coupled to main.py. |
| `GET /brain/autonomy/sample-accumulator` | Multi-platform aggregator logic needs service boundary. |
| `POST /brain/autonomy/execute-top-action` | Executes autonomy action. |
| `GET /brain/autonomy/ibkr-ingester` | IBKR adjacent. |
| `POST /brain/autonomy/ibkr-snapshot` | IBKR adjacent / triggers snapshot. |
| `GET /brain/operations` | Cross-domain aggregator (trading + governance + research). |
| `GET /brain/session-memory` | Session memory / FAISS adjacent; move only under 16F no-write contract. |
| `POST /brain/learning/refresh` | Learning refresh mutation. |
| `POST /brain/learning/proposals/{proposal_id}/transition` | State mutation. |
| `POST /brain/learning/proposals/{proposal_id}/sandbox-run` | Sandbox execution. |
| `POST /brain/learning/proposals/{proposal_id}/evaluate` | Evaluation mutation. |
| All `/brain/strategy-engine/*` | Trading/QC/IBKR adjacent; defer to 16G. |

---

## No-Touch Confirmation

Endpoint delta explanation:
- 18 routes moved to focused routers.
- 2 additional `@app.*` decorators disappeared because they were stale duplicates/left-overs from prior refactoring:
  - `POST /brain/metacognition/audit` had a duplicate implementation near the bottom of `main.py` that was removed.
  - `GET /brain/chat_excellence/proposals/{proposal_id}/evaluation_status` had an extra blank-line-separated decorator that was consolidated.
- Therefore `50 - 18 - 2 = 30` endpoints remain in `main.py`.
- Modify SCVL internals.
- Modify runtime data under `tmp_agent/state`.
- Change behavior or response shape of moved endpoints.
- Start a server or call external APIs.

---

## Tests Executed

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m py_compile tmp_agent/brain_v9/routes/code_mutation_readonly_routes.py`
- `python -m py_compile tmp_agent/brain_v9/routes/chat_excellence_readonly_routes.py`
- `python -m py_compile tmp_agent/brain_v9/routes/autonomy_readonly_shell_routes.py`
- `python -m py_compile tmp_agent/brain_v9/routes/dev_pipeline_audit_routes.py`
- `python -m py_compile tmp_agent/brain_v9/routes/governance_refresh_shell_routes.py`
- `python tests/contract/test_main_router_low_risk_shell_move_16b.py`
- `python -m pytest tests/contract/test_main_router_low_risk_shell_move_16b.py -q`
- Regressions: 16A, 15F, 15E, 12B–12F, P0 security smoke.

---

## Next Recommended Front

**FRONT-BRAIN-MAIN-ROUTER-PROVIDER-BOUNDARY-BATCH-16C**

Move `PROVIDER_BOUNDARY_READY` endpoints after extracting small, focused providers (e.g. scheduler alerts ack, proactive task run, LLM circuit breaker reset, utility refresh, learning refresh, proposal reject).
