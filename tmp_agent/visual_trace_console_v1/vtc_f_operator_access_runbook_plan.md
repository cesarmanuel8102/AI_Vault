# VTC-F1 Operator Access Runbook / Deployment Guide

## Scope
Document how operators configure BRAIN_ADMIN_TOKEN for strict operator access gates.

## What is BRAIN_ADMIN_TOKEN?
- Environment variable expected by `require_operator_access` and `require_strict_operator_access` in `tmp_agent/brain_v9/api_security.py`.
- Used to authenticate non-local HTTP requests to sensitive endpoints.
- Never hardcoded. Never logged. Only compared via `hmac.compare_digest()` (timing-attack resistant).

## Endpoints Affected

### GET /brain/agent-trace/latest
- **Auth**: `require_operator_access` (localhost bypass allowed)
- **Local OK**: YES (if request comes from 127.0.0.1, ::1, localhost, testclient)
- **Remote**: Requires `X-Brain-Token` header if `BRAIN_ADMIN_TOKEN` is configured

### GET /brain/agent-trace/stream
- **Auth**: `require_operator_access` (localhost bypass allowed)
- **Same rules as /latest**

### POST /brain/agent-trace/event
- **Auth**: `require_strict_operator_access` (NO localhost bypass)
- **Always requires** `BRAIN_ADMIN_TOKEN` AND matching `X-Brain-Token`
- If token not configured: returns **403 "strict operator token not configured"**

## Configuration Steps (PowerShell)

### Step 1: Generate a secure token
Do NOT use a simple password. Generate a random token:
```powershell
# Generate 32-byte random hex token
$token = -join ((1..32) | ForEach-Object { '{0:X2}' -f (Get-Random -Maximum 256) })
Write-Host "Generated token (save securely): $token"
```

### Step 2: Set environment variable before launch
Option A — Session-only (PowerShell):
```powershell
$env:BRAIN_ADMIN_TOKEN = "YOUR_GENERATED_TOKEN_HERE"
```

Option B — System environment (requires restart):
```powershell
[Environment]::SetEnvironmentVariable("BRAIN_ADMIN_TOKEN", "YOUR_GENERATED_TOKEN_HERE", "User")
```

### Step 3: Verify token is set
```powershell
if ($env:BRAIN_ADMIN_TOKEN) { Write-Host "Token configured" } else { Write-Host "WARNING: Token NOT configured" }
```

### Step 4: Update restart script (optional)
Add to `tmp_agent/brain_v9/ops/restart_brain_v9_safe.ps1`:
```powershell
# Before Start-Process
if (-not $env:BRAIN_ADMIN_TOKEN) {
  Write-Error "BRAIN_ADMIN_TOKEN is not configured. Refusing to start."
  exit 1
}
```

## Testing the Token

### Test from localhost (should succeed without token)
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/latest?room_id=test&run_id=test" -Method GET
```
Expected: 200 OK

### Test strict endpoint without token (should fail)
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
```
Expected: 403 "strict operator token not configured"

### Test with token (should succeed)
```powershell
$headers = @{"X-Brain-Token" = "YOUR_GENERATED_TOKEN_HERE"}
Invoke-WebRequest -Uri "http://127.0.0.1:8090/brain/agent-trace/event" -Method POST -Headers $headers -ContentType "application/json" -Body '{"room_id":"test","run_id":"test","type":"tool","title":"t","text":"t","severity":"info","data":{}}'
```
Expected: 200 OK

## Security Rules
- Never commit `BRAIN_ADMIN_TOKEN` to git.
- Never include token in UI HTML/JS.
- Never log token values.
- Regenerate token periodically.
- Use firewall/reverse-proxy to restrict non-local access to sensitive endpoints.

## Rollback
If token causes issues, unset env var and restart:
```powershell
Remove-Item Env:\BRAIN_ADMIN_TOKEN
# restart Brain V9
```
Endpoints will revert to "strict operator token not configured" (safe default).

## Evidence
VTC-C demonstrated that without token, POST /brain/agent-trace/event returns 403.
VTC-F closes the documentation gap discovered during that test.
