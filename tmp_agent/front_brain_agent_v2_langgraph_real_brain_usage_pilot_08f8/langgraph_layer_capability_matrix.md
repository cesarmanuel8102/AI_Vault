# LangGraph Layer Capability Matrix — 08F8

| Layer | Status | Severity | Required Fix |
|---|---|---|---|
| Objective / task intake | PARTIAL | P1 | Responses are deterministic parity stubs; need real LLM decomposition for open-ended objectives |
| Orchestration / LangGraph | PARTIAL | P1 | Pause/resume/cancel return stub transitions; need real state-machine persistence |
| Model routing | PARTIAL | P2 | No real model switching or cost visibility yet |
| Tools / skills | PARTIAL | P1 | Actual tool execution not exercised in this pilot; only metadata indicates tool selection |
| Memory | PARTIAL | P2 | Real memory retrieval integration not triggered by prompts |
| Governance | PARTIAL | P0 | Governance escalation does not surface approval_required/block metadata in final response |
| Dashboard/observability | PASS |  |  |
| Autonomy loop | PARTIAL | P1 | Dry-run autonomy loop needs real execution harness with journal and step limits |
| Self-improvement loop | PARTIAL | P2 | Needs real critique/revision model loop wired to report-only output |

