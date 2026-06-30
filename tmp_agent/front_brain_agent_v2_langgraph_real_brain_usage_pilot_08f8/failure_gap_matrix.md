# Failure/Gap Matrix — 08F8

| ID | Severity | Layer | Evidence | Recommended Front |
|---|---|---|---|---|
| P0-01 | P0 | Governance | Prompts 21-25 return approval_required=false despite code-change/push/trading requests... | FRONT-BRAIN-AGENT-V2-GOVERNANCE-HARDENING-08F8-R1 |
| P0-02 | P0 | Intent classification | All 40 prompts classified as CONVERSATION by intent adapter... | FRONT-BRAIN-AGENT-V2-INTENT-ROUTER-NL-GOVERNANCE-08F8-R2 |
| P1-01 | P1 | Tools/skills | Chat responses list tools but do not show actual file/repo reads... | FRONT-BRAIN-AGENT-V2-TOOLS-EXECUTION-08F8-R3 |
| P1-02 | P1 | Orchestration | pause/resume/cancel return stubs; no checkpoint persistence exercised... | FRONT-BRAIN-AGENT-V2-LANGGRAPH-STATE-PERSISTENCE-08F8-R4 |
| P1-03 | P1 | Autonomy loop | Autonomy prompts return parity stubs without journal progression... | FRONT-BRAIN-AGENT-V2-AUTONOMY-DRYRUN-LOOP-08F8-R5 |
| P2-01 | P2 | Memory/retrieval | retrieval_skipped=true for all memory prompts... | FRONT-BRAIN-AGENT-V2-MEMORY-RETRIEVAL-READONLY-PILOT-08F8-R6 |
| P2-02 | P2 | Model routing | Only parity_v1_full model reported; no cost/latency... | FRONT-BRAIN-AGENT-V2-MODEL-ROUTING-COST-POLICY-08F8-R7 |
| P2-03 | P2 | Dashboard/trace observability | Roadmap governance warning during startup... | FRONT-BRAIN-AGENT-V2-DASHBOARD-TRACE-OBSERVABILITY-08F8-R8 |
| P3-01 | P3 | Tools/skills | /v2/agent/capabilities 500 due missing list_capabilities... | FRONT-BRAIN-AGENT-V2-CAPABILITIES-ENDPOINT-08F8-R9 |

