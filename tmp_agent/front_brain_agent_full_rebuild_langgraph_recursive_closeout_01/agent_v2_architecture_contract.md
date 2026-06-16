# Agent V2 Architecture Contract

```json
{
  "statuses": [
    "created",
    "planned",
    "running",
    "waiting_approval",
    "paused",
    "failed",
    "completed",
    "cancelled"
  ],
  "modes": [
    "read_only",
    "dry_run",
    "approval_required",
    "write_allowed"
  ],
  "default_mode": "read_only",
  "schemas": [
    "AgentRun",
    "AgentStep",
    "AgentTraceEvent",
    "ToolCallRequest",
    "ToolCallResult",
    "AgentApprovalRequest",
    "AgentFinalResult",
    "AgentCapability",
    "AgentError",
    "AgentCheckpoint"
  ],
  "guarantees": [
    "no raw chain-of-thought",
    "operational trace only",
    "tools permissioned",
    "memory retrieval read-only",
    "no memory promotion inside Agent V2",
    "write tools require approval",
    "checkpoint after each step",
    "resumable runs",
    "deterministic JSON artifacts",
    "frontend can consume run/trace state"
  ]
}
```
