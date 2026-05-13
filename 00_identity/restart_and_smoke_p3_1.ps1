$ErrorActionPreference="Stop"

# ---- CONFIG ----
$Port = 8010
$Root = "C:\AI_VAULT\00_identity"
$Py   = (Get-Command python).Source
$Api  = "http://127.0.0.1:$Port"
$Rooms= "C:\AI_VAULT\tmp_agent\state\rooms"

Write-Host "[P3.1] python=$Py"
Write-Host "[P3.1] root=$Root"
Write-Host "[P3.1] api =$Api"
Write-Host ""

# ---- STOP LISTENER (if any) ----
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if($listener){
  $pidListen = $listener.OwningProcess
  Write-Host "[P3.1] Stopping listener PID $pidListen on port $Port..."
  Stop-Process -Id $pidListen -Force
  Start-Sleep -Milliseconds 600
}else{
  Write-Host "[P3.1] No listener on port $Port."
}

# ---- START UVICORN in new window ----
$cmd = "cd `"$Root`"; `"$Py`" -m uvicorn brain_server:app --host 127.0.0.1 --port $Port --log-level info"
Write-Host "[P3.1] Starting uvicorn in new pwsh window..."
Start-Process -FilePath "pwsh.exe" -ArgumentList @("-NoExit","-NoProfile","-ExecutionPolicy","Bypass","-Command",$cmd) | Out-Null

# ---- WAIT HEALTHZ ----
$ok = $false
for($i=0; $i -lt 40; $i++){
  Start-Sleep -Milliseconds 350
  try { Invoke-RestMethod "$Api/v1/agent/healthz" | Out-Null; $ok=$true; break } catch {}
}
if(-not $ok){
  throw "[P3.1] FAIL: healthz no responde en $Api/v1/agent/healthz"
}
Write-Host "[P3.1] OK: healthz responde."
Write-Host ""

# ---- SMOKE P3.1: plan -> run_once(propose) -> status(blocked) -> check episode -> apply -> check per-run ----
$rid = "room_p3_1_smoke_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss")
Write-Host "[P3.1] SMOKE room_id=$rid"

$plan = @{
  room_id = $rid
  status  = "active"
  steps   = @(
    @{
      id="S1"; step_id="S1"; status="todo"
      tool_name="append_file"
      tool_args=@{
        path="C:\AI_VAULT\tmp_agent\state\rooms\$rid\smoke_p3_1.txt"
        content="hello_episode`n"
      }
    }
  )
}

Invoke-RestMethod -Method Post -Uri "$Api/v1/agent/plan" -ContentType "application/json" -Body ($plan | ConvertTo-Json -Depth 30) | Out-Null
$r = Invoke-RestMethod -Method Post -Uri "$Api/v1/agent/run_once" -ContentType "application/json" -Body (@{ room_id=$rid } | ConvertTo-Json)
$s = Invoke-RestMethod "$Api/v1/agent/status?room_id=$rid"

if(-not $s.blocked){
  throw "[P3.1] FAIL: status.blocked=null (se esperaba proposal bloqueada)"
}
Write-Host "[P3.1] OK: blocked proposal_id=$($s.blocked.proposal_id)"

# episode should exist after run_once (phase=run_once)
$roomDir = Join-Path $Rooms $rid
$ep      = Join-Path $roomDir "episode.json"
$epDir   = Join-Path $roomDir "episodes"

if(-not (Test-Path $ep)){
  throw "[P3.1] FAIL: episode.json no existe tras run_once: $ep"
}
if(-not (Test-Path $epDir)){
  throw "[P3.1] FAIL: episodes/ no existe tras run_once: $epDir"
}

$ej = Get-Content -Raw $ep | ConvertFrom-Json
Write-Host "[P3.1] episode.json OK: phase=$($ej.phase) run_id=$($ej.run_id) room_id=$($ej.room_id)"

# Apply (approve_token contract)
$body = @{ room_id=$rid; approve_token=$s.blocked.required_approve } | ConvertTo-Json
$a = Invoke-RestMethod -Method Post -Uri "$Api/v1/agent/apply" -ContentType "application/json" -Body $body

if(-not $a.ok){
  throw "[P3.1] FAIL: apply ok=false: $($a | ConvertTo-Json -Depth 10)"
}
Write-Host "[P3.1] OK: apply ejecutó step_id=$($a.step_id)"

# verify file written
$f = "C:\AI_VAULT\tmp_agent\state\rooms\$rid\smoke_p3_1.txt"
if(-not (Test-Path $f)){
  throw "[P3.1] FAIL: smoke file missing: $f"
}
Write-Host "[P3.1] OK: smoke file exists. bytes=$((Get-Item $f).Length)"

# verify per-run file exists (using run_id from episode.json)
$perrun = Join-Path $epDir ("episode_{0}.json" -f $ej.run_id)
if(-not (Test-Path $perrun)){
  throw "[P3.1] FAIL: per-run episode missing: $perrun"
}
Write-Host "[P3.1] OK: per-run episode exists: $perrun"

Write-Host ""
Write-Host "[P3.1] PASS: episode.json + episodes/ + per-run OK"
Write-Host "[P3.1] Room artifacts:"
Write-Host "  $ep"
Write-Host "  $perrun"
Write-Host "  $f"
