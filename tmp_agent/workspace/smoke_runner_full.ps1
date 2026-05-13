param(
  [Alias("RoomId")]
  [string]$RoomIdParam = "",
  [Alias("Port")]
  [int]$PortParam = 8010,
  [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

# ---------------- CONFIG ----------------
$Root    = "C:\AI_VAULT\00_identity"
$Tmp     = "C:\AI_VAULT\tmp_agent"
$HostIP  = "127.0.0.1"
$Port    = 8010
$RoomId  = "smoke_full_" + (Get-Date -Format "yyyyMMdd_HHmmss")
if ($RoomIdParam) { $RoomId = $RoomIdParam }
if ($PortParam)   { $Port   = $PortParam }

$UrlBase = "http://$HostIP`:$Port"
$RoomDir = Join-Path $Tmp "state\rooms\$RoomId"
$PlanPath    = Join-Path $RoomDir "plan.json"
$Audit   = Join-Path $RoomDir "audit.ndjson"
$LogsDir = Join-Path $Tmp "workspace"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $RoomDir | Out-Null

function Fail($msg) { Write-Host "FAIL: $msg" -ForegroundColor Red; exit 1 }
function Assert($cond, $msg) { if (-not $cond) { Fail $msg } }

function Get-LineCount([string]$Path) {
  if (-not (Test-Path $Path)) { return 0 }
  return (Get-Content -LiteralPath $Path | Measure-Object).Count
}

function Wait-OpenApi([int]$Tries = 16, [int]$SleepMs = 500) {
  for ($i=0; $i -lt $Tries; $i++) {
    Start-Sleep -Milliseconds $SleepMs
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "$UrlBase/openapi.json" -TimeoutSec 2
      if ($r.StatusCode -eq 200) { return $true }
    } catch {}
  }
  return $false
}

function Restart-Server() {
  Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

  Start-Sleep -Milliseconds 300

  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $out = Join-Path $LogsDir "uvicorn_${Port}_$stamp.out.log"
  $err = Join-Path $LogsDir "uvicorn_${Port}_$stamp.err.log"

  $p = Start-Process -PassThru -FilePath "python" -WorkingDirectory $Root -ArgumentList @(
    "-m","uvicorn","brain_server:app","--host",$HostIP,"--port",$Port.ToString(),"--log-level","info","--access-log"
  ) -RedirectStandardOutput $out -RedirectStandardError $err

  Write-Host "PID=$($p.Id) OUT=$out ERR=$err" -ForegroundColor DarkGray

  if (-not (Wait-OpenApi)) {
    Write-Host "`n--- tail ERR (200) ---" -ForegroundColor Yellow
    if (Test-Path $err) { Get-Content -LiteralPath $err -Tail 200 }
    Fail "server no levantó /openapi.json"
  }
}

function Get-Json([string]$url, [hashtable]$hdr) {
  return Invoke-RestMethod -Method Get -Uri $url -Headers $hdr -TimeoutSec 10
}
function Post-Json([string]$url, [hashtable]$hdr, $obj) {
  $body = ($obj | ConvertTo-Json -Depth 12)
  return Invoke-RestMethod -Method Post -Uri $url -Headers $hdr -ContentType "application/json" -Body $body -TimeoutSec 15
}

function Ensure-Endpoint($openapi, [string]$path, [string]$method) {
  $p = $openapi.paths.$path
  Assert ($null -ne $p) "openapi missing path: $path"
  $m = $p.$method
  Assert ($null -ne $m) "openapi missing method: $method $path"
}

function Read-Plan() {
  Assert (Test-Path $PlanPath) "plan.json no existe en $PlanPath"
  return (Get-Content -LiteralPath $PlanPath -Raw | ConvertFrom-Json)
}

function Step-ById($planObj, [string]$id) {
  return ($planObj.steps | Where-Object { $_.id -eq $id } | Select-Object -First 1)
}

# ---------------- RUN ----------------
if (-not $NoRestart) { Restart-Server } else { if (-not (Wait-OpenApi)) { Fail "server no respondió /openapi.json" } }

$hdr = @{ "x-room-id" = $RoomId }

# OpenAPI sanity
$openapi = Get-Json "$UrlBase/openapi.json" @{}
Ensure-Endpoint $openapi "/v1/agent/plan" "get"
Ensure-Endpoint $openapi "/v1/agent/plan" "post"
Ensure-Endpoint $openapi "/v1/agent/run" "post"
Ensure-Endpoint $openapi "/v1/agent/run_once" "post"
Ensure-Endpoint $openapi "/v1/agent/apply" "post"
Ensure-Endpoint $openapi "/v1/agent/reject" "post"
Ensure-Endpoint $openapi "/v1/agent/proposal" "get"
Ensure-Endpoint $openapi "/v1/agent/proposals" "get"
Ensure-Endpoint $openapi "/v1/agent/proposals_active" "get"
Ensure-Endpoint $openapi "/v1/agent/evaluation" "get"
Ensure-Endpoint $openapi "/v1/agent/evaluations" "get"
Ensure-Endpoint $openapi "/v1/agent/audit" "get"
Ensure-Endpoint $openapi "/v1/agent/audits" "get"
Ensure-Endpoint $openapi "/v1/agent/status" "get"
Ensure-Endpoint $openapi "/v1/agent/rooms" "get"
Ensure-Endpoint $openapi "/v1/agent/cleanup_preview" "get"
Ensure-Endpoint $openapi "/v1/agent/cleanup_apply" "post"

Write-Host "OK: OpenAPI endpoints presentes" -ForegroundColor Green

# --- Baseline audit lines
$beforeAudit = Get-LineCount $Audit

# 1) PLAN POST (2 steps: list_dir + write_file)
$targetFile = Join-Path $Tmp "workspace\smoke_full_write.txt"
$planObj = @{
  room_id = $RoomId
  steps = @(
    @{ id="1"; status="todo"; tool_name="list_dir";  tool_args=@{ path="C:\AI_VAULT" } }
    @{ id="2"; status="todo"; tool_name="write_file"; tool_args=@{ path=$targetFile; content="smoke_full`n" } }
  )
}
Post-Json "$UrlBase/v1/agent/plan" $hdr $planObj | Out-Null

# 2) PLAN GET
$pg = Get-Json "$UrlBase/v1/agent/plan" $hdr
Assert ($pg.ok -eq $true) "GET /plan ok=false"
Assert ($pg.plan.room_id -eq $RoomId) "GET /plan room_id mismatch"

# 3) RUN (should execute step1 and block at step2 proposed)
$resRun = Post-Json "$UrlBase/v1/agent/run" $hdr @{ room_id=$RoomId; max_steps=10 }
Assert ($resRun.ok -eq $true) "POST /run ok=false"
Assert ($resRun.blocked) "POST /run no devolvió blocked (debe bloquear en write)"
Assert ($resRun.blocked.step_id -eq "2") "POST /run blocked.step_id esperado=2"
Assert ($resRun.blocked.proposal_id) "POST /run blocked.proposal_id missing"
Assert ($resRun.blocked.required_approve) "POST /run blocked.required_approve missing"

# 4) proposals_active (should include blocked proposal)
$pa = Get-Json "$UrlBase/v1/agent/proposals_active?room_id=$RoomId" $hdr
Assert ($pa.ok -eq $true) "GET /proposals_active ok=false"
Assert ($pa.items.Count -ge 1) "GET /proposals_active items vacío"
Assert (($pa.items | Where-Object { $_.proposal_id -eq $resRun.blocked.proposal_id } | Measure-Object).Count -ge 1) "blocked proposal no aparece en proposals_active"

# 5) proposal inspect
$proposalId = $resRun.blocked.proposal_id
$prop = Get-Json "$UrlBase/v1/agent/proposal?proposal_id=$proposalId" $hdr
Assert ($prop.ok -eq $true) "GET /proposal ok=false"
Assert ($prop.proposal.proposal_id -eq $proposalId) "GET /proposal mismatch proposal_id"
Assert ($prop.proposal.room_id -eq $RoomId) "GET /proposal room_id mismatch"

# 6) APPLY (execute write)
$approve = $resRun.blocked.required_approve
$resApply = Post-Json "$UrlBase/v1/agent/apply" $hdr @{ room_id=$RoomId; approve_token=$approve }
Assert ($resApply.ok -eq $true) "POST /apply ok=false"
Assert (Test-Path $targetFile) "apply no creó archivo: $targetFile"
$content = Get-Content -LiteralPath $targetFile -Raw
# SMOKE_FIX_WRITE_CRLF_NORMALIZE_V4
$content = ($content -replace "`r`n","`n")
$content = $content.TrimEnd("`n") + "`n"
Assert ($content -eq "smoke_full`n") "contenido inesperado en $targetFile"

# 7) PLAN should be complete (both done)
$plan = Read-Plan
Assert ($plan.status -eq "complete") "plan.status esperado=complete"
$s1 = Step-ById $plan "1"
$s2 = Step-ById $plan "2"
Assert ($s1.status -eq "done") "step1 status != done"
Assert ($s2.status -eq "done") "step2 status != done"

# 8) EVALUATE -> should persist + readable via GET evaluation(s)
Post-Json "$UrlBase/v1/agent/evaluate" $hdr @{ req = @{ room_id=$RoomId; metrics=@{ ok=1; score=0.99 }; notes="smoke_full" } } | Out-Null

$eval = Get-Json "$UrlBase/v1/agent/evaluation" $hdr
Assert ($eval.ok -eq $true) "GET /evaluation ok=false"
Assert ($eval.evaluation.room_id -eq $RoomId) "evaluation.room_id mismatch"

$evals = Get-Json "$UrlBase/v1/agent/evaluations?limit=5" $hdr
Assert ($evals.ok -eq $true) "GET /evaluations ok=false"
Assert ($evals.items.Count -ge 1) "GET /evaluations items vacío"

# 9) AUDIT GET + AUDITS tail
$a1 = Get-Json "$UrlBase/v1/agent/audit?room_id=$RoomId" $hdr
Assert ($a1.ok -eq $true) "GET /audit ok=false"
Assert ($a1.event.room_id -eq $RoomId) "audit.event room_id mismatch"
$aN = Get-Json "$UrlBase/v1/agent/audits?limit=5&room_id=$RoomId" $hdr
Assert ($aN.ok -eq $true) "GET /audits ok=false"

# 10) STATUS
$st = Get-Json "$UrlBase/v1/agent/status?room_id=$RoomId" $hdr
Assert ($st.ok -eq $true) "GET /status ok=false"
Assert ($st.plan_summary.status -eq "complete") "status.plan_summary.status != complete"

# 11) ROOMS list (should include current)
$rooms = Get-Json "$UrlBase/v1/agent/rooms?limit=200" @{}
Assert ($rooms.ok -eq $true) "GET /rooms ok=false"
Assert (($rooms.items | Where-Object { $_.room_id -eq $RoomId } | Measure-Object).Count -ge 1) "rooms no incluye room actual"

# 12) REJECT flow smoke (rebuild plan to force proposal again, then reject)
$rejectFile = Join-Path $Tmp "workspace\smoke_full_reject.txt"
Post-Json "$UrlBase/v1/agent/plan" $hdr @{
  room_id=$RoomId
  steps=@(
    @{ id="1"; status="todo"; tool_name="write_file"; tool_args=@{ path=$rejectFile; content="reject_me`n" } }
  )
} | Out-Null

$r2 = Post-Json "$UrlBase/v1/agent/run" $hdr @{ room_id=$RoomId; max_steps=10 }
Assert ($r2.ok -eq $true) "run (reject flow) ok=false"
Assert ($r2.blocked) "run (reject flow) no bloqueó"
$rejTok = $r2.blocked.required_approve
Post-Json "$UrlBase/v1/agent/reject" $hdr @{ room_id=$RoomId; approve_token=$rejTok; reason="smoke_full_reject" } | Out-Null
$plan2 = Read-Plan
$st1 = Step-ById $plan2 "1"
Assert ($st1.status -eq "todo") "reject no devolvió step a todo"
Assert (-not (Test-Path $rejectFile)) "reject no debe ejecutar write_file"

# 13) CLEANUP preview+apply (no debe borrar nada si no hay orphans matching)
$cp = Get-Json "$UrlBase/v1/agent/cleanup_preview?older_than_hours=1&only_orphans=true&room_prefix=room_&limit=50&allow_id_prefix=prop_&exclude_ids=proposal_template" @{}
Assert ($cp.ok -eq $true) "cleanup_preview ok=false"

$bodyCleanup = @{
  confirm="DELETE"
  older_than_hours=1
  only_orphans=$true
  room_prefix="room_"
  max_delete=5
  allow_id_prefix="prop_"
  exclude_ids=@("proposal_template")
}
$ca = Post-Json "$UrlBase/v1/agent/cleanup_apply" @{} $bodyCleanup
Assert ($ca.ok -eq $true) "cleanup_apply ok=false"

# Audit growth sanity (should have grown >= a few lines)
$afterAudit = Get-LineCount $Audit
Assert (($afterAudit - $beforeAudit) -ge 3) "audit no creció lo esperado (delta<3). before=$beforeAudit after=$afterAudit"

Write-Host "`nOK: SMOKE FULL PASS room_id=$RoomId" -ForegroundColor Green
Write-Host "Plan: $PlanPath" -ForegroundColor DarkGray
Write-Host "Audit: $Audit" -ForegroundColor DarkGray
Write-Host "Wrote: $targetFile" -ForegroundColor DarkGray
exit 0



# SMOKE_FIX_WRITE_CRLF_NORMALIZE_V4

# SMOKE_FIX_PLANPATH_RENAME_V1
