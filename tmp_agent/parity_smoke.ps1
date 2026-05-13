$ErrorActionPreference="Stop"

$base="http://127.0.0.1:8010"
function New-Room($p){ "{0}_{1}" -f $p,(Get-Date -Format "yyyyMMdd_HHmmss") }

# 0) server arriba
(Invoke-WebRequest -UseBasicParsing -Uri ($base + "/openapi.json")).StatusCode | Out-Null

$room = New-Room "room_parity_smoke"
$hdr  = @{ "x-room-id"=$room; "Content-Type"="application/json" }

Write-Host ("ROOM="+$room) -ForegroundColor Yellow

# 1) plan
Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$base/v1/agent/plan" -Headers $hdr `
  -Body (@{goal="RUNNER_PARITY_HARD"} | ConvertTo-Json -Depth 10) -ContentType "application/json" | Out-Null

# 2) run_once
$r1 = Invoke-RestMethod -Method Post -Uri "$base/v1/agent/run_once" -Headers $hdr `
  -Body (@{} | ConvertTo-Json) -ContentType "application/json"

if ($r1.action -ne "propose_write_step") { throw "PARITY_FAIL: run_once.action=$($r1.action)" }
if (-not $r1.step_id) { throw "PARITY_FAIL: run_once.step_id vacío" }

Write-Host ("OK: run_once => action={0} step_id={1}" -f $r1.action, $r1.step_id) -ForegroundColor Green

# 3) run
$r2 = Invoke-RestMethod -Method Post -Uri "$base/v1/agent/run" -Headers $hdr `
  -Body (@{} | ConvertTo-Json) -ContentType "application/json"

if (-not $r2.needs_approval) { throw "PARITY_FAIL: run.needs_approval != True" }
if (-not $r2.approve_token)  { throw "PARITY_FAIL: run.approve_token vacío" }

Write-Host ("OK: run => needs_approval=True token={0} status={1}" -f $r2.approve_token, $r2.summary.status) -ForegroundColor Green

# 4) GET /plan
$p = Invoke-RestMethod -Method Get -Uri "$base/v1/agent/plan" -Headers @{ "x-room-id"=$room }
if (-not $p.plan -or -not $p.plan.steps) { throw "PARITY_FAIL: plan.steps vacío" }

$step = $p.plan.steps | Where-Object { $_.id -eq $r1.step_id } | Select-Object -First 1
if (-not $step) { throw "PARITY_FAIL: no encontré step_id=$($r1.step_id)" }

if ($step.status -ne "proposed") { throw "PARITY_FAIL: step.status=$($step.status)" }
if ($step.required_approve -ne $r2.approve_token) { throw "PARITY_FAIL: required_approve != approve_token" }

Write-Host ("OK: plan => step={0} status=proposed token match" -f $step.id) -ForegroundColor Green

# 5) completar
Write-Host "Running dev_loop_run.ps1 to completion (SafeWrite)..." -ForegroundColor Cyan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\AI_VAULT\tmp_agent\dev_loop_run.ps1" `
  -Room $room -MaxIters 25 -ShowSummary -OutText -SafeWrite

$p2 = Invoke-RestMethod -Method Get -Uri "$base/v1/agent/plan" -Headers @{ "x-room-id"=$room }
Write-Host ("FINAL PLAN.status={0}" -f $p2.plan.status) -ForegroundColor Yellow
