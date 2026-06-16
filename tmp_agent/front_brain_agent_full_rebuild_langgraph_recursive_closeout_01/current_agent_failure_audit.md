# Current Agent Failure Audit

```json
{
  "agent_v2_fix": [
    "run.json per run",
    "trace.jsonl operational events",
    "checkpoint.json after state transitions",
    "permissioned tool gateway",
    "read-only memory gateway",
    "/v2/agent canonical endpoints"
  ],
  "frontend_fragmentation": "8091 UI/dashboard and 8092 dashboard preserved; 8092 gets /brain-dashboard/agent-v2/status",
  "missing_state": "legacy agent lacks durable per-run checkpoint and trace",
  "provider_ambiguity": "recent eval showed Kimi confirmation inconsistent under load; Agent V2 finalizer labels structured provider explicitly",
  "weak_routing": [
    "legacy /v1/agent status is health-only, not canonical execution",
    "/agent route is legacy compatibility and points users to /chat",
    "chat route may timeout/fallback under load"
  ]
}
```
