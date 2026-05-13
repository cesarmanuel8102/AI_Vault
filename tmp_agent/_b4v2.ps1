$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:8090"

function Show-Patterns {
    try {
        $r = Invoke-RestMethod -Uri "$base/brain/learned/patterns" -TimeoutSec 5
        Write-Host ("[patterns] count={0}" -f $r.count) -ForegroundColor Cyan
        foreach ($p in $r.patterns) {
            Write-Host ("  - {0} | {1} -> {2} | conf={3}" -f `
                $p.id, $p.tool_class, $p.correction.to_tool, $p.confidence)
        }
    } catch { Write-Host "[patterns ERR]" }
}

function Show-Counters {
    try {
        $c = (Invoke-RestMethod -Uri "$base/brain/validators" -TimeoutSec 5).live_module_counters
        $rel = $c.PSObject.Properties | Where-Object { $_.Name -match "learned|self_test|auto_rewrite" }
        Write-Host "[counters]" -ForegroundColor Cyan
        foreach ($r in $rel) { Write-Host ("  {0} = {1}" -f $r.Name, $r.Value) }
    } catch {}
}

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "B4v2: Force run_command with PS cmdlet (should fail then learn)" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

# First, manually invoke run_command with a PS cmdlet via the tools test endpoint
# This bypasses the agent's tendency to use run_powershell directly

Write-Host ""
Write-Host "--- BEFORE ---" -ForegroundColor Green
Show-Patterns
Show-Counters

# Use the low-level tool test to force run_command with Get-Date
$toolBody = @{
    tool = "run_command"
    args = @{ cmd = "Get-Date" }
} | ConvertTo-Json -Compress

Write-Host ""
Write-Host "--- Forcing run_command('Get-Date') via tool execute ---" -ForegroundColor Yellow

# We need to call the tool directly somehow... let's use a special chat
# that the agent will DEFINITELY try run_command on

$chatBody = @{
    session_id = "b4v2_force"
    message = @"
IMPORTANTE: Ejecuta EXACTAMENTE este tool call:
tool: run_command
args: {"cmd": "Get-Date"}

No uses otro tool. Quiero probar especificamente run_command con ese comando.
"@
} | ConvertTo-Json

Write-Host ("body: {0}" -f $chatBody.Substring(0, [Math]::Min(300, $chatBody.Length)))
$t0 = Get-Date
try {
    $resp = Invoke-RestMethod -Uri "$base/chat" -Method POST -Body $chatBody `
        -ContentType "application/json" -TimeoutSec 180
    $ms = ((Get-Date) - $t0).TotalMilliseconds
    Write-Host ("Response in {0:N0}ms" -f $ms) -ForegroundColor Cyan
    Write-Host ("success={0}" -f $resp.success) -ForegroundColor Magenta
    Write-Host "response:" -ForegroundColor Magenta
    Write-Host ($resp.response.Substring(0, [Math]::Min(600, $resp.response.Length)))
} catch {
    Write-Host ("CHAT FAILED: {0}" -f $_.Exception.Message) -ForegroundColor Red
}

Write-Host ""
Write-Host "--- AFTER ---" -ForegroundColor Green
Show-Patterns
Show-Counters
