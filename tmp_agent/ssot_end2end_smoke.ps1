$ErrorActionPreference="Stop"
$base="http://127.0.0.1:8010"
function New-Room($p){ "{0}_{1}" -f $p,(Get-Date -Format "yyyyMMdd_HHmmss") }

# server arriba
(Invoke-WebRequest -UseBasicParsing -Uri ($base + "/openapi.json")).StatusCode | Out-Null

$room = New-Room "room_ssot_e2e"
$hdr  = @{ "x-room-id"=$room; "Content-Type"="application/json" }

Write-Host ("ROOM="+$room) -ForegroundColor Yellow

# A) POST /plan (debe persistir plan.json)
Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$base/v1/agent/plan" -Headers $hdr `
  -Body (@{goal="SSOT_E2E_SMOKE"} | ConvertTo-Json -Depth 10) -ContentType "application/json" | Out-Null

# B) run_once -> propone step
$r1 = Invoke-RestMethod -Method Post -Uri "$base/v1/agent/run_once" -Headers $hdr `
  -Body (@{} | ConvertTo-Json) -ContentType "application/json"
Write-Host ("run_once.action={0} step_id={1}" -f $r1.action, $r1.step_id) -ForegroundColor Cyan
if ($r1.action -ne "propose_write_step") { throw "FAIL: run_once.action=$($r1.action)" }

# C) run -> needs_approval
$r2 = Invoke-RestMethod -Method Post -Uri "$base/v1/agent/run" -Headers $hdr `
  -Body (@{} | ConvertTo-Json) -ContentType "application/json"
Write-Host ("run.needs_approval={0} token={1} status={2}" -f $r2.needs_approval, $r2.approve_token, $r2.summary.status) -ForegroundColor Cyan
if (-not $r2.needs_approval) { throw "FAIL: run.needs_approval != True" }
if (-not $r2.approve_token)  { throw "FAIL: run.approve_token vacío" }

# D) completar con runner
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\AI_VAULT\tmp_agent\dev_loop_run.ps1" `
  -Room $room -MaxIters 25 -ShowSummary -OutText -SafeWrite

# E) evaluate (persistir last_eval)
$evalBody=@{ observation=@{ ok=$true; room_id=$room; note="E2E_EVAL_NOTE" } } | ConvertTo-Json -Depth 10
Invoke-RestMethod -Method Post -Uri "$base/v1/agent/evaluate" -Headers $hdr -Body $evalBody -ContentType "application/json" | Out-Null

# F) GET /plan
$p = Invoke-RestMethod -Method Get -Uri "$base/v1/agent/plan" -Headers @{ "x-room-id"=$room }
Write-Host ("GET.plan.room_id={0}" -f $p.plan.room_id) -ForegroundColor Green
Write-Host ("GET.plan.status={0}" -f $p.plan.status) -ForegroundColor Green
Write-Host ("GET.last_eval.note={0}" -f $p.plan.last_eval.observation.note) -ForegroundColor Green

if ($p.plan.room_id -ne $room) { throw "FAIL: GET plan.room_id mismatch" }
if ($p.plan.status -ne "complete") { throw "FAIL: GET plan.status expected=complete actual=$($p.plan.status)" }
if ($p.plan.last_eval.observation.note -ne "E2E_EVAL_NOTE") { throw "FAIL: last_eval.note mismatch" }

# G) archivo físico
$fp="C:\AI_VAULT\tmp_agent\state\rooms\$room\plan.json"
"plan.json exists=$([IO.File]::Exists($fp)) path=$fp" | Write-Host
if (-not [IO.File]::Exists($fp)) { throw "FAIL: plan.json no existe" }

$raw = Get-Content -LiteralPath $fp -Raw
if ($raw -notmatch "E2E_EVAL_NOTE") { throw "FAIL: plan.json no contiene last_eval.note" }

Write-Host "OK: SSOT E2E SMOKE PASS" -ForegroundColor Yellow
