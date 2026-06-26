# Governance Surface Inventory

## Route Inventory

### Critical Protected Routes (strict auth present)
- `/v2/chat/agent` (chat_router) - POST, requires strict auth
- `/v2/agent/runs` (router) - POST, requires strict auth
- `/v2/agent/runs/{run_id}/plan` - POST, requires strict auth
- `/v2/agent/runs/{run_id}/execute` - POST, requires strict auth
- `/v2/agent/runs/{run_id}/pause` - POST, requires strict auth
- `/v2/agent/runs/{run_id}/resume` - POST, requires strict auth
- `/v2/agent/runs/{run_id}/cancel` - POST, requires strict auth
- `/v1/chat/completions` - POST, requires strict auth (openai_compat router)

### Dev/Debug/Admin Routes (potentially risky)
- `/dev` - POST, no strict auth dependency visible
- `/godmode` - POST, no strict auth dependency visible
- `/godmode/status` - GET, no strict auth dependency visible
- `/chat/introspectivo/debug` - GET, no strict auth dependency visible
- `/brain/maintenance/action` - POST, no strict auth visible
- `/brain/mutations/test_apply` - POST, no strict auth visible
- `/brain/semantic-memory/ingest` - POST, no strict auth visible
- `/brain/semantic-memory/ingest-session` - POST, no strict auth visible
- `/brain/self-improvement/change` - POST, no strict auth visible
- `/brain/self-improvement/change/{id}/promote` - POST, no strict auth visible
- `/brain/self-improvement/change/{id}/rollback` - POST, no strict auth visible
- `/brain/validate` - POST, no strict auth visible
- `/brain/proactive/run/{task_id}` - POST, no strict auth visible
- `/brain/ops/log-cleanup` - POST, no strict auth visible
- `/brain/strategy-engine/execute-top-candidate` - POST, no strict auth visible
- `/brain/strategy-engine/execute-candidate/{strategy_id}` - POST, no strict auth visible
- `/brain/strategy-engine/execute-batch/{strategy_id}` - POST, no strict auth visible
- `/brain/strategy-engine/execute-comparison-cycle` - POST, no strict auth visible
- `/brain/control-layer/freeze` - POST, no strict auth visible
- `/brain/control-layer/unfreeze` - POST, no strict auth visible

### Read-Only Status Routes (lower risk)
- `/health`, `/status`, `/healthz` - GET, public
- `/brain/*` status endpoints - GET, mostly read-only

## ToolGateway Inventory

### Write Tools (high risk)
- `promotion_candidate_promote` - requires build mode + approval token
- `file_patch_apply_approval_required` - requires build mode + approval token
- `git_commit_approval_required` - requires build mode + approval token
- `report_writer` - dry_run by default

### Read Tools (low risk)
- `repo_status_read`, `repo_history_read`, `file_read`, `grep_search`, `route_probe`, `semantic_retrieve`, `smoke_test_readonly`, `promotion_candidate_validate`

## Risk Assessment

| Risk | Status | Mitigation |
|------|--------|------------|
| /dev endpoint | HIGH | Must be gated by BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS |
| /godmode endpoint | HIGH | Must require strict auth, no bypass |
| god/safe_mode flags | MEDIUM | Must not bypass auth |
| self-dev change endpoints | HIGH | Must not modify auth/governance files |
| semantic-memory/ingest | HIGH | Must require strict auth |
| strategy-engine execute | HIGH | Must require strict auth |
| proactive/run | MEDIUM | Must require strict auth |
| maintenance/action | MEDIUM | Must require strict auth |
| mutations/test_apply | MEDIUM | Must require strict auth |

## Findings

1. BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS defaults to false - good
2. require_strict_operator_access is used on critical routes - good
3. /dev and /godmode routes need verification of gating
4. No explicit GOD/safe_mode bypass fields found in request schemas
5. RBAC exists but not enforced on all routes
6. Self-dev endpoints exist but may not check for governance file protection
