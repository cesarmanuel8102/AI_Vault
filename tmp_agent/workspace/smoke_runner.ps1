param(
  [Alias("RoomId")]
  [string]$RoomIdParam = "",

  [Alias("Port")]
  [int]$PortParam = 8010
)

$ErrorActionPreference = "Stop"

# ---------------- CONFIG ----------------
$Root    = "C:\AI_VAULT\00_identity"
$Tmp     = "C:\AI_VAULT\tmp_agent"
$HostIP  = "127.0.0.1"
$Port    = 8010
$RoomId  = "default"

if ($RoomIdParam) { $RoomId = $RoomIdParam }
if ($PortParam)   { $Port   = $PortParam }

$UrlBase = "http://$HostIP`:$Port"
$Audit   = Join-Path $Tmp "state\rooms\$RoomId\audit.ndjson"
$LogsDir = Join-Path $Tmp "workspace"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

function Fail($msg) {
  Write-Host "FAIL: $msg" -ForegroundColor Red
  exit 1
}

function Assert($cond, $msg) {
  if (-not $cond) { Fail $msg }
}

function Get-LineCount([string]$Path) {
  if (-not (Test-Path $Path)) { return 0 }
  return (Get-Content -LiteralPath $Path | Measure-Object).Count
}

function Wait-OpenApi([int]$Tries = 16, [int]$SleepMs = 500) {
  for ($i=0; $i -lt $Tries; $i++) {
    Start-Sleep -Milliseconds $SleepMs
    try {
      $r = Invoke-WebRequest -UseBasicParsing -Uri "$UrlBase/openapi.json" -TimeoutSec 1
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
    Write-Host "`n--- tail ERR (120) ---" -ForegroundColor Yellow
    if (Test-Path $err) { Get-Content -LiteralPath $err -Tail 120 }
    Fail "server no levantó /openapi.json"
  }
}

function Invoke-Smoke() {
  $hdr = @{ "x-room-id" = $RoomId }

  $before = Get-LineCount $Audit

  Invoke-RestMethod -Method Get -Uri "$UrlBase/v1/agent/plan" -Headers $hdr -TimeoutSec 5 | Out-Null

  $body = @{ req = @{ room_id = $RoomId; metrics = @{ ok = 1 }; notes = "smoke_runner" } } | ConvertTo-Json -Depth 8
  Invoke-RestMethod -Method Post -Uri "$UrlBase/v1/agent/evaluate" -Headers $hdr -ContentType "application/json" -Body $body -TimeoutSec 5 | Out-Null

  $body2 = @{ room_id = $RoomId } | ConvertTo-Json -Depth 6
  Invoke-RestMethod -Method Post -Uri "$UrlBase/v1/agent/run_once" -Headers $hdr -ContentType "application/json" -Body $body2 -TimeoutSec 8 | Out-Null

  $after = Get-LineCount $Audit
  $delta = $after - $before

  Write-Host "lines_added=$delta (before=$before after=$after)" -ForegroundColor Cyan
  Assert ($delta -eq 3) "audit.ndjson debe crecer exactamente +3 líneas (plan/evaluate/run_once). got=$delta"

  $tail = Get-Content -LiteralPath $Audit -Tail 3
  $objs = @()
  foreach ($line in $tail) {
    try { $objs += ($line | ConvertFrom-Json) }
    catch { Fail "audit.ndjson contiene una línea inválida JSON en tail" }
  }

  $expected = @(
    "audit_mw:/v1/agent/plan",
    "audit_mw:/v1/agent/evaluate",
    "audit_mw:/v1/agent/run_once"
  )

  for ($i=0; $i -lt 3; $i++) {
    $o = $objs[$i]
    Assert ($o.room_id -eq $RoomId) "room_id mismatch en audit tail[$i]"
    Assert ($o.event -eq $expected[$i]) "event mismatch en audit tail[$i]. expected=$($expected[$i]) got=$($o.event)"
    Assert ($o.ts) "missing ts en audit tail[$i]"
    Assert ($o.plan_sha256) "missing plan_sha256 en audit tail[$i]"

    Assert ($o.extra) "missing extra en audit tail[$i]"
    Assert ($o.extra.method) "missing extra.method en audit tail[$i]"
    Assert ($o.extra.req_id) "missing extra.req_id en audit tail[$i]"
    Assert (($o.extra.status_code -eq 200) -or ($o.extra.status_code -eq 201)) "unexpected status_code en audit tail[$i]"
    Assert (($o.extra.duration_ms -is [int]) -or ($o.extra.duration_ms -is [long])) "duration_ms no es int en audit tail[$i]"
    Assert ($o.extra.client_host) "missing extra.client_host en audit tail[$i]"
  }

  Write-Host "`nOK: SMOKE PASS" -ForegroundColor Green
  $tail | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
}

Restart-Server
Invoke-Smoke
exit 0
