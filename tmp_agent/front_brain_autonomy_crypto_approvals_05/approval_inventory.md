# FRONT-BRAIN-AUTONOMY-CRYPTO-APPROVALS-05

## Phase 1: Approval Inventory

**Starting HEAD**: 0b790a7  
**Date**: 2026-06-27

---

## Summary

| Category | Count |
|----------|-------|
| Total approval mechanisms | 4 |
| Weak approvals identified | 6 |
| High-risk approval paths | 5 |
| Files to modify | 2 (1 new, 1 existing) |
| Files NOT to touch | 8 |

---

## Existing Approval Mechanisms

### 1. ExecutionGate pending_approval
**File**: `tmp_agent/brain_v9/governance/execution_gate.py`  
**Type**: pending_id + plain text confirmation  
**Weakness**: No cryptographic validation, plain text 'si' or /approve <pending_id> accepted, no expiration, no nonce, no replay protection  
**Key locations**:
- `approve()` method (line 726)
- `approve_latest()` method (line 738)
- `reject()` method (line 749)

### 2. HTTP /gate/approve endpoint
**File**: `tmp_agent/brain_v9/main.py`  
**Type**: pending_id + operator access  
**Weakness**: Only checks operator access via `require_operator_access`, passes `_bypass_gate=True`, no signed token validation  
**Locations**:
- `/gate/approve/{pending_id}` (line 1930)
- `/gate/reject/{pending_id}` (line 1957)

### 3. R27 self-dev auto-approve
**File**: `tmp_agent/brain_v9/governance/execution_gate.py`  
**Type**: settings-based bypass  
**Weakness**: Auto-approves P2 tools if `self_dev_enabled=true`, `require_approval=false`, `max_risk>=0.4`, no token, no audit trail beyond log  
**Locations**: lines 669-697

### 4. AGENTV2_APPROVED_ prefix check
**File**: `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py`  
**Type**: prefix string check  
**Weakness**: Only checks if `approval_token` starts with `AGENTV2_APPROVED_`, no signature validation, no expiration, no scope/action/target binding  
**Locations**: `write_allowed()` function (line 128-130)

---

## Weak Approvals Identified

| ID | Description | Severity |
|----|-------------|----------|
| WEAK-01 | Plain text 'si' or /approve <pending_id> accepted without cryptographic validation | HIGH |
| WEAK-02 | pending_id is just timestamp + tool name, predictable, no nonce | HIGH |
| WEAK-03 | No expiration on pending approvals (except TTL cleanup at 24h) | MEDIUM |
| WEAK-04 | No replay protection - same pending_id can be approved multiple times | HIGH |
| WEAK-05 | AGENTV2_APPROVED_ prefix check has no signature validation | HIGH |
| WEAK-06 | R27 self-dev auto-approve bypasses approval entirely for P2 tools | HIGH |

---

## High-Risk Approval Paths

| Path | Current Protection | Risk if Bypassed |
|------|-------------------|------------------|
| edit_file/write_file/backup_file on governance/security files | ExecutionGate.check() → SelfDevSandbox (denied) | If gate bypassed, plain /approve would allow mutation |
| mutation |
| promote_staged_change/rollback_staged_change | ExecutionGate.check() → SelfDevSandbox (denied) | Same as above |
| semantic_memory_ingest | evaluate_selfdev_action() direct (denied) | If gate bypassed, plain approval would allow |
| GOD mode P3 actions | Blocked, requires /approve <pending_id> | Plain /approve would bypass |
| R27 self-dev auto-approve | Auto-approves P2 if settings allow | No token, no audit, no scope binding |

---

## Files to Modify

| File | Change Type |
|------|-------------|
| `tmp_agent/brain_v9/governance/signed_approvals.py` | **NEW** - Signed approval module |
| `tmp_agent/brain_v9/governance/execution_gate.py` | Minimal integration - validate signed tokens |
| `tmp_agent/brain_v9/main.py` | Minimal integration for /gate/approve |

## Files NOT to Touch

| File | Reason |
|------|--------|
| `memory/*` | Forbidden |
| `trading/*` | Forbidden |
| `broker/*` | Forbidden |
| `.env` | Forbidden |
| `tmp_agent/brain_v9/core/agent_kernel_v2/governance.py` | write_allowed() - out of scope for this front |
| `tmp_agent/brain_v9/brain/self_improvement.py` | Out of scope |
| `tmp_agent/brain_v9/agent/loop.py` | Out of scope |

---

## Signed Approval Design

### Token Format (HMAC-SHA256)
```
{
  "actor": "operator",
  "scope": "governance",
  "action": "edit_file",
  "target": "tmp_agent/brain_v9/governance/execution_gate.py",
  "issued_at": 1719400000,
  "expires_at": 1719403600,
  "nonce": "a1b2c3d4...",
  "signature": "hmac_sha256(...)"
}
```

### Validation Rules
1. **Valid signature** - HMAC-SHA256 verified with secret
2. **Not expired** - `expires_at > now`
3. **Correct scope** - Matches expected scope
4. **Correct action** - Matches expected action
5. **Correct target** - Matches expected target
6. **Not replayed** - Nonce not in used_nonces set
7. **No secret printed** - Never log full token or secret