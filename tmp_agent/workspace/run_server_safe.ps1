# run_server_safe.ps1
# Brain Lab - safe runner (compile gate + minimal smoke)
# Usage:
#   pwsh -File .\run_server_safe.ps1
# Optional:
#   $env:PORT="8010"  (default 8010)

$ErrorActionPreference = "Stop"

$PORT = [int]($env:PORT ?? "8010")
$HOST = "127.0.0.1"
$BASE = "http://$HOST`:$PORT"
$headers = @{ "x-room-id" = "default" }

$rootIdentity = "C:\AI_VAULT\00_identity"
$tmpAgentRoot = "C:\AI_VAULT\tmp_agent"

$serverPy = Join-Path $rootIdentity "brain_server.py"
$routerPy = Join-Path $rootIdentity "brain_router.py"
$toolsFs = Join-Path $rootIdentity "tools_fs.py"
$applyGate = Join-Path $tmpAgentRoot "apply_gate.py"

function Write-Ok($msg) { Write-Host $msg -ForegroundColor Green }
function Write-Warn($msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Bad($msg) { Write-Host $msg -ForegroundColor Red }

function Kill-PortListener([int]$port) {
  $pid = (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
  if ($pid) {
    try { Stop-Process -Id $pid -Force; Write-Warn "Killed PID $pid listening on $port" }
    catch { Write-Warn "Could not kill PID $pid: $($_.Exception.Message)" }
  }
}

function Compile-Gate([string[]]$paths) {
  foreach ($p in $paths) { if (-not (Test-Path $p)) { throw "MISSING_FILE: $p" } }
  & python -m py_compile @paths
  if ($LASTEXITCODE -ne 0) { throw "PY_COMPILE_FAILED (exit=$LASTEXITCODE)" }
  Write-Ok "py_compile OK: $($paths -join ', ')"
}

function Wait-Http([string]$url, [int]$timeoutSec = 10) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
    try { Invoke-RestMethod -Uri $url -TimeoutSec 2 | Out-Null; return $true }
    catch { Start-Sleep -Milliseconds 250 }
  }
  return $false
}

function Smoke-Minimal() {
  $oa = Invoke-RestMethod -Uri "$BASE/openapi.json" -TimeoutSec 5
  if (-not $oa.paths) { throw "SMOKE_FAIL: openapi missing paths" }

  $paths = @($oa.paths.PSObject.Properties.Name)
  $required = @(
    "/v1/agent/plan",
    "/v1/agent/execute",
    "/v1/agent/execute_step",
    "/v1/agent/evaluate",
    "/v1/agent/plan_refresh"
  )
  foreach ($r in $required) {
    if ($paths -notcontains $r) { throw "SMOKE_FAIL: missing route $r" }
  }
  Write-Ok "SMOKE: routes present OK"

  $planReq = @{ goal="SAFE_RUN_SMOKE"; room_id="default" } | ConvertTo-Json
  $plan = Invoke-RestMethod -Method Post -Uri "$BASE/v1/agent/plan" -Headers $headers -ContentType "application/json" -Body $planReq -TimeoutSec 10
  if (-not $plan.ok) { throw "SMOKE_FAIL: plan not ok" }
  Write-Ok "SMOKE: plan OK (status=$($plan.plan.status))"

  $steps = @($plan.plan.steps)
  $hasS1 = $false; $hasS2 = $false
  foreach ($s in $steps) {
    if ($s.id -eq "S1") { $hasS1 = $true }
    if ($s.id -eq "S2") { $hasS2 = $true }
  }

  if ($hasS1) {
    Invoke-RestMethod -Method Post -Uri "$BASE/v1/agent/execute_step" -Headers $headers -ContentType "application/json" `
      -Body (@{room_id="default"; step_id="S1"; mode="propose"} | ConvertTo-Json) -TimeoutSec 10 | Out-Null
    Write-Ok "SMOKE: execute_step S1 OK"
  }

  if ($hasS2) {
    Invoke-RestMethod -Method Post -Uri "$BASE/v1/agent/execute_step" -Headers $headers -ContentType "application/json" `
      -Body (@{room_id="default"; step_id="S2"; mode="propose"} | ConvertTo-Json) -TimeoutSec 10 | Out-Null
    Write-Ok "SMOKE: execute_step S2 OK"
  }

  $rf = Invoke-RestMethod -Method Post -Uri "$BASE/v1/agent/plan_refresh" -Headers $headers -ContentType "application/json" `
    -Body (@{room_id="default"} | ConvertTo-Json) -TimeoutSec 10
  if (-not $rf.ok) { throw "SMOKE_FAIL: plan_refresh not ok" }
  Write-Ok "SMOKE: plan_refresh OK (updated=$($rf.updated))"

  $evalReq = @{ room_id="default"; observation=@{ ok=$true; note="SAFE_RUN_SMOKE"; ts=(Get-Date).ToString("o") } } | ConvertTo-Json -Depth 10
  $ev = Invoke-RestMethod -Method Post -Uri "$BASE/v1/agent/evaluate" -Headers $headers -ContentType "application/json" -Body $evalReq -TimeoutSec 10
  if (-not $ev.ok) { throw "SMOKE_FAIL: evaluate not ok" }
  Write-Ok "SMOKE: evaluate OK (plan.status=$($ev.plan.status))"
  # STATUS endpoint (read-only visibility)
  $st = Invoke-RestMethod -Method Post -Uri "$BASE/v1/agent/status" -Headers $headers -ContentType "application/json" `
    -Body (@{ room_id="default" } | ConvertTo-Json) -TimeoutSec 10

  Write-Ok ("STATUS: plan.status={0} steps_total={1} pending_approvals={2}" -f `
    $st.summary.status, $st.summary.steps_total, $st.summary.pending_approvals_count)

  if ($st.pending_approvals -and $st.pending_approvals.Count -gt 0) {
    Write-Warn "PENDING APPROVALS:"
    foreach ($k in $st.pending_approvals.Keys) {
      Write-Warn ("  {0} => {1}" -f $k, $st.pending_approvals[$k])
    }
  }

}

try {
  Set-Location $rootIdentity
  $env:BRAIN_TMP_AGENT_ROOT = $tmpAgentRoot
  $env:PYTHONPATH = "$env:BRAIN_TMP_AGENT_ROOT;$env:PYTHONPATH"

  Kill-PortListener -port $PORT
  Compile-Gate -paths @($serverPy, $routerPy, $toolsFs, $applyGate)

  $p = Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","brain_server:app","--host",$HOST,"--port","$PORT","--log-level","info" -PassThru -WindowStyle Normal
  Write-Ok "Started uvicorn PID $($p.Id) on $BASE"

  if (-not (Wait-Http -url "$BASE/openapi.json" -timeoutSec 12)) {
    throw "SERVER_START_TIMEOUT: $BASE/openapi.json not responding"
  }

  Smoke-Minimal
  Write-Ok "SAFE_RUN OK: server healthy at $BASE"
  exit 0
}
catch {
  Write-Bad "SAFE_RUN FAILED: $($_.Exception.Message)"
  try { Kill-PortListener -port $PORT } catch {}
  exit 1
}