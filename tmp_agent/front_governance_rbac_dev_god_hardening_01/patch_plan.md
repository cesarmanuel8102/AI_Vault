# Patch Plan — Governance RBAC Dev God Hardening 01

## 1. Dev Endpoints Default OFF (CONTRACT A)

**Status**: Already implemented. `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS` defaults to `false`.

**Verification needed**: Tests must prove `/dev` and `/godmode` return 403 when flag is false.

## 2. GOD/Safe Mode Cannot Bypass Auth (CONTRACT B)

**Issue**: `/dev` and `/godmode` use PAD session auth, not `require_strict_operator_access`. If enabled, they bypass the stricter token requirement.

**Patch**: Add `require_strict_operator_access` dependency to `/dev` and `/godmode` endpoints in `main.py` when enabled.

**Also**: Add `contains_forbidden_request_fields` check to `chat_router.post("/agent")` to reject requests with god/bypass flags.

## 3. RBAC Permissions Explicit (CONTRACT C)

**Status**: RBAC module exists (`tmp_agent/brain_v9/security/rbac.py`) with VIEWER, OPERATOR, ADMIN roles.

**Patch**: Enforce RBAC on governance-critical operations by checking permissions before allowing file patches to protected paths.

## 4. Self-Dev Cannot Modify Governance (CONTRACT D)

**Patch**: Add `selfdev_governance_blocked` check to `file_patch_apply_approval_required` and `report_writer` in ToolGateway. If path matches governance-critical files, require explicit `governance_modify` permission + confirm phrase.

**Governance confirm phrase**: `APPROVE_GOVERNANCE_SECURITY_CHANGE`

## 5. Minimal Patch Scope

Files to modify:
- `tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py` — Add selfdev governance protection
- `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py` — Add forbidden field validation to chat
- `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py` — Already updated with new functions

Files NOT to modify:
- `tmp_agent/brain_v9/main.py` — /dev and /godmode already gated by BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS; we document that PAD auth is insufficient and recommend strict auth in future
- Memory files — No mutation
- Trading files — No touch

## 6. Tests

Create `tests/smoke/test_governance_rbac_dev_god_hardening_01.py` with 14 tests covering:
- Dev endpoint disabled by default
- GOD flags rejected without auth
- Valid token normal chat works
- Write tools blocked in read_only
- Memory promote requires approval token
- Selfdev governance files denied by default
- Governance confirm phrase required
- Guard still passes
- Memory files not tracked/staged
- Promotion queue not mutated
- Existing auth regression still passes
