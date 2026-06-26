# Diff Audit: a118b7f — Governance RBAC Dev God Hardening

## Commit
`a118b7f26899849152b5001b445247234e7d8d07`

## Files Changed
1. `tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py`
2. `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py`
3. `tmp_agent/brain_v9/core/agent_kernel_v2/tool_gateway.py`
4. `tests/smoke/test_governance_rbac_dev_god_hardening_01.py`

## Claim-by-Claim Verification

### CLAIM 1: CONTRACT B — Reject forbidden bypass/override fields in message
- **File**: `api_adapter.py:139-142`
- **Classification**: PARTIAL
- **Analysis**: `contains_forbidden_request_fields` is called with `{"message": req.message}`. It checks if the **keys** of this dict match forbidden names. However, `AgentChatRequest(BaseModel)` has no `ConfigDict(extra='forbid')`. In Pydantic v2, default behavior is `extra='ignore'`, meaning extra JSON fields (e.g., `{"message": "hello", "bypass_auth": true}`) are silently dropped and never reach `contains_forbidden_request_fields`. The defense only catches forbidden strings **inside** the message text, not extra fields in the JSON body.
- **Gap**: Strong negative test needed with valid token + extra forbidden fields to prove rejection.

### CLAIM 2: validate_mode rejects dangerous modes
- **File**: `governance.py:95-103`
- **Classification**: TRUE
- **Analysis**: Explicitly maps god/god_mode/execute/unsafe/superuser → read_only.

### CLAIM 3: GOVERNANCE_PROTECTED_PATHS blocks self-dev modification
- **File**: `governance.py:32-42`
- **Classification**: TRUE
- **Analysis**: Correctly lists security-critical files.

### CLAIM 4: CONTRACT D — Self-dev governance file protection in tool_gateway
- **File**: `tool_gateway.py:91-98`
- **Classification**: TRUE
- **Analysis**: Checks `selfdev_governance_blocked()` and requires exact token+confirm phrase before allowing `file_patch_apply_approval_required`, `file_patch_dry_run`, or `report_writer` on protected paths.

### CLAIM 5: Dev endpoints disabled by default
- **File**: `main.py:4273-4284, 4355-4366`
- **Classification**: TRUE
- **Analysis**: Both `/dev` and `/godmode` POST endpoints raise `HTTPException(403)` when `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS` is false.

### CLAIM 6: /godmode/status safety
- **File**: `main.py:4333-4353`
- **Classification**: NOT_PROVEN
- **Analysis**: This GET endpoint has **no authentication dependency** (`require_strict_operator_access` is not applied). It returns:
  - Whether unsafe endpoints are enabled
  - Safe mode status
  - **Active PAD session IDs** (information disclosure)
  - **God session IDs from execution_gate** (information disclosure)
  - Session expiration times
- **Gap**: Even though it doesn't execute tasks, it leaks session metadata. Should require strict operator access.

### CLAIM 7: test_god_flags_do_not_bypass_auth proves extra fields rejected
- **File**: `test_governance_rbac_dev_god_hardening_01.py:54-66`
- **Classification**: FALSE (overclaim)
- **Analysis**: The test sends payloads **without** `X-Brain-Token`. All requests are rejected by `require_strict_operator_access` (401/403). It does **not** prove that a request with a **valid token** + extra forbidden fields would be rejected. This is a classic "missing auth" vs "auth+bad payload" distinction.

### CLAIM 8: FORBIDDEN_REQUEST_FIELDS includes 'mode' as defense-in-depth
- **File**: `governance.py:44-47`
- **Classification**: TRUE
- **Analysis**: Redundant with validate_mode, but valid defense-in-depth.

### CLAIM 9: write_allowed dual-check
- **File**: `governance.py:128-130`
- **Classification**: TRUE
- **Analysis**: Requires both mode==build AND approval_token prefix match.

## Summary
- **TRUE**: 6 claims
- **PARTIAL**: 1 claim (CLAIM 1 — body-level extra fields not inspected)
- **NOT_PROVEN**: 1 claim (CLAIM 6 — /godmode/status auth)
- **FALSE**: 1 claim (CLAIM 7 — test does not prove what it claims)
