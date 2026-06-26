# Strong Negative Test Plan: a118b7f Audit Closeout

## Verified Gaps (from Diff Audit)
1. **GAP-A — Extra JSON body fields silently dropped**: `AgentChatRequest(BaseModel)` has no `extra='forbid'`. A request with a valid `X-Brain-Token` and an extra field like `bypass_auth` will have the extra field silently ignored by Pydantic, bypassing `contains_forbidden_request_fields`.
2. **GAP-B — /godmode/status unauthenticated**: This GET endpoint leaks active PAD session IDs, god session list, and expiration times without requiring any token.
3. **GAP-C — /dev and /godmode lack strict operator dependency**: Even when enabled, these endpoints rely only on PAD session auth and do not enforce `require_strict_operator_access`.

## Test Plan

### TEST-1: Valid token + extra forbidden field in JSON body → rejected
**Purpose**: Prove that extra fields in the JSON body are NOT silently ignored when a valid token is present.
**Method**: POST `/v2/chat/agent` with `X-Brain-Token: VALID_TOKEN` and body `{"message": "hello", "mode": "read_only", "bypass_auth": true}`.
**Expected (before patch)**: 200 (extra field dropped, request proceeds).
**Expected (after patch)**: 422 (Pydantic validation error due to `extra='forbid'`).

### TEST-2: /godmode/status without token → 403
**Purpose**: Prove that the information-disclosure endpoint now requires strict operator access.
**Method**: GET `/godmode/status` without `X-Brain-Token`.
**Expected (before patch)**: 200 (JSON with session metadata).
**Expected (after patch)**: 403.

### TEST-3: /godmode/status with valid token → accessible (when dev disabled, still 403 from flag)
**Purpose**: Verify that with a valid token, the endpoint still returns JSON (the flag check doesn't block this endpoint).
**Method**: GET `/godmode/status` with `X-Brain-Token: VALID_TOKEN`.
**Expected**: 200 (same as before, but now token-gated).

### TEST-4: /dev and /godmode POST without token → 403 (dependency now enforced)
**Purpose**: Prove that the strict operator dependency is enforced before the PAD session check.
**Method**: POST `/dev` and `/godmode` without `X-Brain-Token`.
**Expected**: 403 (same status code as before, but now from dependency).

### TEST-5: Regression — valid token normal chat still works
**Purpose**: Ensure `extra='forbid'` does not break legitimate requests.
**Method**: POST `/v2/chat/agent` with valid token and standard fields only.
**Expected**: 200.

## Patch Scope
- `api_adapter.py`: Add `ConfigDict(extra='forbid')` to `AgentChatRequest` and `CreateRunRequest`.
- `main.py`: Add `dependencies=[Depends(require_strict_operator_access)]` to `/dev`, `/godmode`, and `/godmode/status`.
