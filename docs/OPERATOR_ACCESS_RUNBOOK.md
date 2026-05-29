# Operator Access Runbook / Deployment Guide

## 1. Purpose
This runbook explains how operators configure and validate the operator access token (`BRAIN_ADMIN_TOKEN`) used by the Brain V9 runtime security gates.

## 2. Security Model
- `require_operator_access` — Allows localhost bypass for non-mutating GET endpoints.
- `require_strict_operator_access` — Requires token for ALL requests (no localhost bypass) for sensitive endpoints like POST /brain/agent-trace/event.
- Token is compared using `hmac.compare_digest()` to prevent timing attacks.
- The token value is never hardcoded, never logged, and never returned in HTTP responses.

## 3. Endpoint Access Matrix

| Endpoint | Method | Auth Type | Localhost Bypass | Token Required |
|----------|--------|-----------|------------------|----------------|
| /brain/agent-trace/latest | GET | `require_operator_access` | YES | Only for non-local |
| /brain/agent-trace/stream | GET | `require_operator_access` | YES | Only for non-local |
| /brain/agent-trace/event | POST | `require_strict_operator_access` | NO | Always |

## 4. Localhost Bypass Rules
- `127.0.0.1`, `::1`, `localhost`, `testclient` are treated as local and bypass token checks for `require_operator_access`.
- `require_strict_operator_access` **does NOT allow any bypass**.

## 5. StrictOperatorAccess Rules
- `BRAIN_ADMIN_TOKEN` environment variable **must** be set.
- Every request to a strict endpoint **must** include header `X-Brain-Token: <token>`.
- Mismatch or missing token returns **403**.

## 6. BRAIN_ADMIN_TOKEN Setup (PowerShell)

### Step 1: Generate a secure token
```powershell
# Generate 32-byte random hex token
$token = -join ((1..32) | ForEach-Object { '{0:X2}' -f (Get-Random -Maximum 256) })
Write-Host "Generated token (save securely): $token"
```

### Step 2: Set environment variable before launch
Session-only:
```powershell
$env:BRAIN_ADMIN_TOKEN = "YOUR_GENERATED_TOKEN_HERE"
```

System-wide (requires PowerShell restart):
```powershell
[Environment]::SetEnvironmentVariable("BRAIN_ADMIN_TOKEN", "YOUR_GENERATED_TOKEN_HERE", "User")
```

### Step 3: Verify token is set
```powershell
if ($env:BRAIN_ADMIN_TOKEN) { Write-Host "Token configured" } else { Write-Host "WARNING: Token NOT configured" }
```

## 7. X-Brain-Token Usage
Include in HTTP headers for strict endpoints:
```powershell
$headers = @{"X-Brain-Token" = "YOUR_GENERATED_TOKEN_HERE"}
Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -Headers $headers -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
```

## 8. Safe Validation Commands

### Test GET /latest (localhost, no token needed)
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/latest?room_id=test&run_id=test&limit=20" -Method GET
```
Expected: 200 OK

### Test POST /event WITHOUT token (should fail)
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
```
Expected: 403 "strict operator token not configured"

### Test POST /event WITH token (should succeed)
```powershell
$headers = @{"X-Brain-Token" = "YOUR_GENERATED_TOKEN_HERE"}
Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -Headers $headers -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
```
Expected: 200 OK

## 9. Expected Errors
- **strict operator token not configured** — `BRAIN_ADMIN_TOKEN` not set.
- **strict operator access required** — Token mismatch or missing `X-Brain-Token`.
- **Operator access required for non-local requests** — Non-local request without token.

## 10. Restart Script Notes
`tmp_agent/brain_v9/ops/restart_brain_v9_safe.ps1` **does not** set `BRAIN_ADMIN_TOKEN`. Operators must set it before executing the script, or they will not be able to POST events from non-local sources.

## 11. Production Deployment Notes
- Always set `BRAIN_ADMIN_TOKEN` before starting the server.
- Use a firewall or reverse proxy to restrict access to `/brain/agent-trace/event`.
- Store the token in a secrets manager (e.g., Azure Key Vault, AWS Secrets Manager).

## 12. Firewall / Reverse Proxy Cautions
- Never expose `/brain/agent-trace/event` directly to the internet without token enforcement.
- Use TLS termination at the reverse proxy.
- Validate `X-Brain-Token` at the proxy layer if possible.

## 13. Secret Handling Rules
- **NEVER** commit the token to git.
- **NEVER** include the token in UI HTML/JS.
- **NEVER** log the token.
- Regenerate periodically (e.g., every 90 days).

## 14. Rollback / Unset Token
```powershell
Remove-Item Env:\BRAIN_ADMIN_TOKEN
[Environment]::SetEnvironmentVariable("BRAIN_ADMIN_TOKEN", $null, "User")
```
After unsetting, restart Brain V9. Endpoints will revert to safe default: 403 for strict endpoints.

## 15. Troubleshooting
- **403 on GET /latest from remote**: Token missing or not matching.
- **403 on POST /event from localhost**: This is expected if token not configured; set token to enable.
- **Token works for /latest but not /event**: /event uses `StrictOperatorAccess` (no bypass); /latest uses `OperatorAccess` (localhost bypass).
