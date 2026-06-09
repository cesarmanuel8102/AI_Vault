# Real Execution Policy

## What Counts as "Real Execution"

Real execution means the system processes a concrete source and generates a
traceable execution packet. It is NOT synthetic/dry-run. It touches actual data.

For this repository, the first permitted real execution is:
- **Local whitelisted file read** only
- **No network**
- **No connector**
- **No memory write**
- **No FAISS promotion**
- **No trading**
- **No B8**

## What is NOT Allowed Yet

- Semantic memory write (`memory/semantic/semantic_memory.jsonl`)
- FAISS index write (`memory/semantic/semantic_memory_faiss.*`)
- External API/network fetch
- Connector activation
- Trading order execution
- B8 module activation
- Patch application
- Docker destructive commands
- `.env` modification

## Minimum Conditions for Real Execution

Before `real_execution_allowed` becomes true, ALL must be satisfied:

| Condition | Required Value |
|-----------|---------------|
| dashboard_ok | true |
| brain_server_ok | true |
| ollama_ok | true (if LLM used) |
| operator_approval_visible | true |
| git_tracked_clean | true |
| roadmap_valid | true |
| semantic_memory_write_allowed | false (this front) |
| faiss_write_allowed | false (this front) |

## Real Execution Gate

The gate is implemented in `brain/real_execution_gate.py`.

Default: `real_execution_allowed = false`

No code path in the repository should bypass this gate for the first real
execution.

## Rollback / No-Op Policy

If real execution fails or is denied:
1. Log failure to evidence path
2. Do NOT write to semantic memory
3. Do NOT promote to FAISS
4. Do NOT modify tracked files
5. Report status to operator

## Operator Approval Requirement

Every real execution requires explicit operator approval.
The approval must be:
- Visible in dashboard/chat
- Logged with timestamp
- Reversible (no destructive action)

## Recommended Next Front

FRONT-FIRST-REAL-LOCAL-INGESTION-DRY-RUN-01
