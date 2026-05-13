param(
  [Alias("RoomId")]
  [string]$RoomId = "default",

  [Alias("Port")]
  [int]$Port = 8010
)

$ErrorActionPreference="Stop"

function Fail($m){ Write-Host "FAIL: $m" -ForegroundColor Red; exit 1 }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$bak = "$server.bak_gate_$stamp"
Copy-Item -Force -LiteralPath $server -Destination $bak
Write-Host "OK: backup => $bak" -ForegroundColor DarkGray

try {
  python -m py_compile $server
  Write-Host "OK: py_compile" -ForegroundColor Green

  pwsh -ExecutionPolicy Bypass -File $smoke -RoomId $RoomId -Port $Port
  Write-Host "OK: gate PASS" -ForegroundColor Green
  exit 0
}
catch {
  Write-Host "`nGATE FAIL => rollback" -ForegroundColor Yellow
  Copy-Item -Force -LiteralPath $bak -Destination $server
  try { python -m py_compile $server | Out-Null } catch {}
  throw
}
