# Brain V9 / Agent V2 — Local Operations Runbook

Front: `FRONT-BRAIN-AGENT-V2-STABILIZE-LOCAL-OPERATION-RUNBOOK-AUTOSTART-01`
Workspace: `C:\AI_VAULT_CANONICAL`
Baseline: `af16b50ff186f97bf61f2bea0b6486d591ea490d`

> Conservative operational stabilization only. This runbook never modifies runtime
> source, memory, FAISS, broker/trading, governance, or security logic. All commands
> are read-only except where an explicit start/stop/restart is requested.

## Architecture (what runs where)

| Service | Port | Launcher (canonical) | Module |
|---------|------|----------------------|--------|
| Brain API | **8091** | `tmp_agent/brain_v9/start_safe_server.py` | `brain_v9.main:app` (uvicorn, 127.0.0.1) |
| Dashboard | **8092** | `tmp_agent/brain_v9/dashboard/dashboard_app:app` (uvicorn `-c`) | `tmp_agent.brain_v9.dashboard.dashboard_app:app` |
| Legacy dashboard | 8070 | — | **INACTIVE — do not use. Current dashboard is 8092.** |

The dashboard router prefix is **`/brain-dashboard`** (set in `dashboard_routes.py`).
Auth header for strict operator endpoints: **`X-Brain-Token: <BRAIN_ADMIN_TOKEN>`**.

---

## 0. Prerequisites — set the token once per shell

```powershell
# Set the admin token in YOUR environment. NEVER hardcode it into source or a script body.
$env:BRAIN_ADMIN_TOKEN = "<your-operator-token-here>"   # read from your secret store
# All commands below read this env var. It is never printed in full.
```

> If you must check whether the token is set, print only a redacted prefix:
> `if ($env:BRAIN_ADMIN_TOKEN) { $env:BRAIN_ADMIN_TOKEN.Substring(0,8) + "***REDACTED" } else { "<none>" }`

All paths below assume `cd C:\AI_VAULT_CANONICAL`.

---

## 1. Check status (read-only)

```powershell
# Listener + owner PID for 8091 / 8092 / 8070
Get-NetTCPConnection -State Listen -LocalPort 8091,8092,8070 -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess, State | Format-Table -AutoSize

# Map owning PIDs to python processes with command lines
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
```
Or use the helper script:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tmp_agent\brain_v9\ops\status_brain_local.ps1
```

## 2. Start 8091 only (Brain API)

```powershell
# Token must already be in $env:BRAIN_ADMIN_TOKEN.
$env:PYTHONPATH = "C:\AI_VAULT_CANONICAL"
$env:PYTHONIOENCODING = "utf-8"
Start-Process -FilePath "python" `
  -ArgumentList "tmp_agent/brain_v9/start_safe_server.py" `
  -WorkingDirectory "C:\AI_VAULT_CANONICAL" `
  -WindowStyle Hidden -PassThru |
  Select-Object Id, StartTime
```
> `start_safe_server.py` is the canonical safe launcher. It uses
> `WindowsSelectorEventLoopPolicy`, binds 127.0.0.1:8091, and does NOT hardcode a token.

## 3. Start 8092 only (Dashboard)

```powershell
$env:PYTHONPATH = "C:\AI_VAULT_CANONICAL"
$env:PYTHONIOENCODING = "utf-8"
$cmd = "import uvicorn; uvicorn.run('tmp_agent.brain_v9.dashboard.dashboard_app:app', host='127.0.0.1', port=8092, log_level='info', reload=False)"
$proc = Start-Process -FilePath "python" -ArgumentList @("-c", $cmd) `
  -WorkingDirectory "C:\AI_VAULT_CANONICAL" `
  -RedirectStandardOutput "tmp_agent\brain_v9\dashboard_only_8092.log" `
  -RedirectStandardError  "tmp_agent\brain_v9\dashboard_only_8092.err.log" `
  -WindowStyle Hidden -PassThru
$proc.Id | Out-File -FilePath "tmp_agent\brain_v9\dashboard_only_8092.pid" -Encoding ascii -NoNewline
$proc.Id
```

## 4. Start both

Run section 2, wait ~3s, then run section 3. Verify with section 1 and section 10/11.

## 5. Stop 8091

```powershell
# Find the PID that OWNS port 8091, then stop ONLY that process.
$pid8091 = (Get-NetTCPConnection -State Listen -LocalPort 8091 -ErrorAction SilentlyContinue).OwningProcess
if ($pid8091) {
  Get-CimInstance Win32_Process -Filter "ProcessId=$pid8091" | Select-Object ProcessId, CommandLine
  Stop-Process -Id $pid8091 -Force
  "Stopped 8091 owner PID $pid8091"
} else { "8091 not listening" }
```
> **Never** run `Stop-Process -Name python` or kill all `python.exe`. Only kill the PID owning the target port.

## 6. Stop 8092

```powershell
$pid8092 = (Get-NetTCPConnection -State Listen -LocalPort 8092 -ErrorAction SilentlyContinue).OwningProcess
if ($pid8092) {
  Get-CimInstance Win32_Process -Filter "ProcessId=$pid8092" | Select-Object ProcessId, CommandLine
  Stop-Process -Id $pid8092 -Force
  "Stopped 8092 owner PID $pid8092"
} else { "8092 not listening" }
```

## 7. Restart both

Run section 5 (stop 8091), section 6 (stop 8092), wait 2s, then section 2 + section 3,
then verify with section 10/11.

## 8. Detect stale PID files

```powershell
Get-ChildItem -Path "tmp_agent\brain_v9" -Filter "*.pid" -ErrorAction SilentlyContinue | ForEach-Object {
  $rec = (Get-Content $_.FullName -Raw).Trim()
  $alive = [bool](Get-Process -Id $rec -ErrorAction SilentlyContinue)
  [PSCustomObject]@{ File=$_.Name; RecordedPID=$rec; Alive=$alive; Verdict=$(if($alive){'VALID'}else{'STALE'}) }
} | Format-Table -AutoSize
```

## 9. Clean stale PID files safely

Only remove a PID file when its recorded PID is confirmed NOT running (section 8).
```powershell
# Example: remove a specific stale file after confirming via section 8
# Remove-Item -Path "tmp_agent\brain_v9\start_local_browser_operational_launcher.pid" -Force
```
> Do NOT delete `dashboard_only_8092.pid` while 8092 is running. Never delete whole directories.

## 10. Verify 8091 health

```powershell
try { (Invoke-WebRequest -Uri "http://127.0.0.1:8091/health" -UseBasicParsing -TimeoutSec 8).StatusCode }
catch { "ERROR: " + $_.Exception.Message }
# Expect: 200  -> {"status":"healthy","sessions":N,"version":"9.0.0","safe_mode":false}
```

## 11. Verify 8092 health

```powershell
try { (Invoke-WebRequest -Uri "http://127.0.0.1:8092/health" -UseBasicParsing -TimeoutSec 8).StatusCode }
catch { "ERROR: " + $_.Exception.Message }
# Expect: 200 -> {"ok":true,"dashboard":"brain_persistent_autonomy","port":8092}
```

## 12. Verify agent status (token redacted)

```powershell
$h = @{ "X-Brain-Token" = $env:BRAIN_ADMIN_TOKEN }
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:8091/v2/agent/status" -UseBasicParsing -TimeoutSec 8 -Headers $h
  "STATUS=" + $r.StatusCode
  $r.Content   # body may be inspected; token is NOT echoed by the server
} catch { "ERROR: " + $_.Exception.Message }
```

## 13. Verify capabilities (token redacted)

```powershell
$h = @{ "X-Brain-Token" = $env:BRAIN_ADMIN_TOKEN }
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:8091/v2/agent/capabilities" -UseBasicParsing -TimeoutSec 8 -Headers $h
  "STATUS=" + $r.StatusCode
  $r.Content
} catch { "ERROR: " + $_.Exception.Message }
```

## 14. Inspect logs

```powershell
# Most recently modified logs
Get-ChildItem -Path "tmp_agent\brain_v9" -Filter "*.log" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 8 Name, Length, LastWriteTime | Format-Table -AutoSize

# Tail a specific log (last 40 lines)
# Get-Content "tmp_agent\brain_v9\start_local_browser_operational_brain.log" -Tail 40
```
Key logs: `brain_server_stdout.log`, `brain_server_stderr.log`,
`start_local_browser_operational_brain.log`, `start_local_browser_operational_dashboard.err.log`.

## 15. Diagnose provider degraded / HTTP 429

A **429 Too Many Requests** comes from the **upstream model provider** (quota / rate-limit / unfunded),
NOT from the local service. The literal substring `429` in dashboard access logs is usually a remote
TCP port number (e.g. `127.0.0.1:56429`), not an HTTP status.

**Recovery sequence (safe):**
1. Confirm local services up (section 10 + 11). Do NOT restart unless they are actually down.
2. Check the aggregate dashboard status — `degraded:false` and `kimi:ok` means provider is fine:
   ```powershell
   (Invoke-WebRequest -Uri "http://127.0.0.1:8092/brain-dashboard/status" -UseBasicParsing -TimeoutSec 8).Content
   ```
3. If degraded: check provider account quota/funding in the provider dashboard.
4. Wait + exponential backoff, then retry the chat prompt.
5. Do NOT manually edit provider credentials. Let the runtime provider-selector fail over if a second provider is configured.
6. Inspect the failing run trace to confirm the 429 came from the provider:
   ```powershell
   $h = @{ "X-Brain-Token" = $env:BRAIN_ADMIN_TOKEN }
   (Invoke-WebRequest -Uri "http://127.0.0.1:8091/v2/agent/runs/<run_id>/trace" -UseBasicParsing -Headers $h).Content
   ```
7. If degradation persists, the runtime returns a deterministic parity-finalizer fallback reply (safe, no writes). Continue read-only use until quota is restored.

## 16. Dashboard endpoint probing (actually do it, don't infer)

Probe these and record status + body preview. Do NOT infer route content from the repo or from memory.

```powershell
function Probe([string]$u){ try { $r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 8; "{0}  {1}" -f $r.StatusCode,$u } catch { $c=$null; if($_.Exception.Response){$c=[int]$_.Exception.Response.StatusCode}; "{0}  {1}  ({2})" -f $c,$u,$_.Exception.Message } }

# Public
Probe "http://127.0.0.1:8091/health"
Probe "http://127.0.0.1:8092/"
Probe "http://127.0.0.1:8092/health"
Probe "http://127.0.0.1:8092/brain-dashboard/status"
Probe "http://127.0.0.1:8092/brain-dashboard/agent-v2/status"
# Token-gated (strict)
$h = @{ "X-Brain-Token" = $env:BRAIN_ADMIN_TOKEN }
try { (Invoke-WebRequest -Uri "http://127.0.0.1:8091/v2/agent/status" -UseBasicParsing -Headers $h).StatusCode } catch { $_.Exception.Message }
try { (Invoke-WebRequest -Uri "http://127.0.0.1:8091/v2/agent/capabilities" -UseBasicParsing -Headers $h).StatusCode } catch { $_.Exception.Message }
```
Reference results from this front: see `dashboard_endpoint_probe.json`.
Note: `8092/brain-dashboard/chat` returns **405** on GET — it is POST-only; 405 means the route EXISTS.

## 17. 8070 legacy vs 8092 current

- **8070 is legacy / INACTIVE** (connection refused; no listener).
- **8092 is the current dashboard** (`/`, `/health`, `/brain-dashboard/*`).
- If something points you at 8070, treat it as a stale reference and use 8092 instead.
- Do not start anything on 8070.

## 18. Recovery when chat UI returns a structured fallback

A structured fallback reply (e.g. `deterministic_parity_finalizer`) means the request degraded
safely. No writes occur.

1. Confirm 8091 + 8092 are up (sections 10/11).
2. Check `8092/brain-dashboard/status` for `degraded` and provider `ok` (section 15).
3. If provider degraded → follow section 15.
4. If provider healthy but fallback still appears → inspect the run trace (section 15 step 6) and the logs (section 14). This is a planner/runtime observation, NOT something to hot-fix in ops. Report it.
5. Do NOT restart services unless a listener is actually down.

## 19. Recovery when provider works but route_probe was NOT executed

Tag: `DASHBOARD_ENDPOINT_ANALYSIS_INCOMPLETE_NO_ROUTE_PROBE`.

If the agent correctly identifies endpoints but does not actually probe them live (and says so
honestly), that is a planner observation — **do not repair planner logic in ops**.

Operational mitigation:
1. Run section 16 yourself to get authoritative live endpoint.
2. Record results in `dashboard_endpoint_probe.*` for operator review.
3. Continue using the verified 8091/8092 endpoints.

## 20. What NOT to do

- **Do not** edit `api_security.py`.
- **Do not** hardcode the token into `start_safe_server.py` or any script body.
- **Do not** touch `.env`.
- **Do not** delete `memory/`, `semantic/`, or FAISS index files.
- **Do not** kill unrelated `python.exe` processes — only kill the PID owning the target port.
- **Do not** run `git reset`, `git clean`, `git stash`, `git commit --amend`, or any force push.
- **Do not** start Autonomy R2.
- **Do not** start trading / broker / IBKR / real-money paths.
- **Do not** use port 8070.
- **Do not** run `start_full_server.py` for safe local ops (it enables unsafe dev endpoints + autonomy).
- **Do not** modify `start_local_browser_operational.py` or `start_local_browser_operational_launcher.py`
  (the latter is not in this repo) without explicit approval.

---

## Helper scripts (Phase 4)

`tmp_agent/brain_v9/ops/`:
- `status_brain_local.ps1` — read-only status (listeners, owners, PID files, health).
- `start_brain_local.ps1`  — start 8091 and/or 8092 detached (token from env, never hardcoded).
- `stop_brain_local.ps1`   — stop only the PID owning the named port; confirms first unless `-Force`.
- `restart_brain_local.ps1`— stop then start both, then verify health.

All scripts read `BRAIN_ADMIN_TOKEN` from the environment and redact it in output.
