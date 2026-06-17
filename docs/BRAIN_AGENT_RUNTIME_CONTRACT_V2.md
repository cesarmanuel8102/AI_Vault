# Brain Agent Runtime Contract V2

## Mandatory Multi-Tool Compliance

### Deterministic Parser
- File: `tmp_agent/brain_v9/core/agent_kernel_v2/mandatory_tools.py`
- Detects: "mandatory tool test", "must perform", "not just repo status", numbered lists
- Maps: probe URL → route_probe, repo status → repo_status_read, search code → grep_search, retrieve memory → semantic_retrieve

### Planner Override
- When `mandatory_detected=true`, classification = `mandatory_multitool`
- Plan includes one step per requested check
- Final answer obligations (e.g. "In final answer, list...") are extracted as requested checks but are NOT scheduled as tool calls
- Order preserved
- Deduplication of exact duplicates only
- Each tool step includes `requested_by_user: true`, `expected: "ok"`

### Finalizer Evidence Contract
- Prompt includes `tool_distinction` field
- Distinguishes: requested vs scheduled vs executed
- Rules:
  - Requested but not scheduled → "planner did not schedule requested tool"
  - Scheduled but failed → "tool scheduled but failed"
  - Executed and blocked → "executed and correctly blocked"
  - Executed and passed → "executed and passed"
  - Do NOT say "unavailable" unless ToolGateway lacks the capability

## Tool Gateway Safety
- route_probe: only localhost (127.0.0.1, localhost)
- file_read: path blocked for .env, secrets, trading, B8, strategies
- semantic_retrieve: read-only, never writes
- file_patch_apply_approval_required: requires approval_token or write_allowed mode
- git_commit_approval_required: requires approval_token or write_allowed mode

## 8092 Zombie Blocker
- Separate issue documented in FRONT-BRAIN-AGENT-V2-8092-DASHBOARD-DOGFOOD-CLOSEOUT-01
- 8091 is canonical for Agent V2 until zombie resolved

## Runtime Operations
The runtime supports create, plan, execute, pause, resume, cancel, list, get, and trace operations. Responses include canonical flags, provider metadata, trace availability, and governed tool outcomes. No raw chain-of-thought is exposed.
