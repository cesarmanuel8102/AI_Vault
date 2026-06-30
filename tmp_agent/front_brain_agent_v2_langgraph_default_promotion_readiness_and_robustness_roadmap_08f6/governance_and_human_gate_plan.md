# Governance and Human Gate Plan — 08F6

## Approval gates

| Action | Rule | Irreversible | Approval required |
|---|---|---|---|
| File writes | Read-only or dry-run by default; write requires `mode=approval_required` or explicit tool | No | YES |
| Source patches | Only in dedicated promotion fronts; report-only fronts never patch source | YES | YES |
| Test patches | Only in dedicated test-fix fronts; must pass CI before baseline update | YES | YES |
| Git commits | Require human review; no auto-commit by agent without explicit front | YES | YES |
| Pushes | Normal push only; no force push, force-with-lease, or amend | YES | YES |
| Memory promotion | Candidate → validated → human approved → promoted → retrieval tested | YES | YES |
| FAISS rebuild | Separate front required; no runtime-triggered rebuild | YES | YES |
| Tool registry changes | New write/broker/trading tools require separate risk-governance front | YES | YES |
| Model routing changes | Must be documented and reviewed; no hidden fallback to expensive model | No | YES |
| Cost budget changes | Explicit approval; logged in decision journal | No | YES |
| Trading/broker integration | Explicitly forbidden without separate risk-governance front | YES | YES |
| External API calls | Read-only/dry-run allowed; write/stateful calls require approval | No | YES |
| Cloud tracing | Opt-in only; operator must approve and configure endpoint | No | YES |
| Default backend promotion | Only after all gates pass and a separate front is accepted | YES | YES |

## Operational limits

| Limit | Value |
|---|---|
| Max steps per task | 50 |
| Max token/cost budget per run | USD 2.00 |
| Max wall-clock duration | 300 seconds |
| Max retry count | 3 |
| Emergency stop | Operator can stop any run by unsetting `AGENT_V2_BACKEND` or restarting the server; fallback to Native is automatic. |

## Audit log required fields

- run_id
- backend_selected
- backend_fallback_used
- backend_fallback_reason
- mode_requested
- mode_effective
- tools_considered
- tools_blocked
- tools_executed
- node_path
- trace_events_count
- provider_used
- model_used
- updated_utc

## Failure loudness rule

No silent fallback unless explicitly recorded in `backend_fallback_used` and `backend_fallback_reason`. All failures must emit a trace event and set run status to `failed` with a reason.

## Phase result

PHASE 6 — Governance and human gate plan: **COMPLETED**

## Recorded

`2026-06-30T18:40:00+00:00`
