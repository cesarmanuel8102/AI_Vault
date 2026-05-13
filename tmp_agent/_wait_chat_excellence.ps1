$ErrorActionPreference = "Continue"
Write-Host "=== R9.1 Chat Excellence first-iteration wait ===" -ForegroundColor Cyan

$maxWait = 720
$elapsed = 0
$interval = 30
$found = $false

while ($elapsed -lt $maxWait) {
    Start-Sleep -Seconds $interval
    $elapsed += $interval
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:8090/brain/chat_excellence/status" -TimeoutSec 10
        $total = $r.total_iterations
        Write-Host "[$elapsed s] total_iterations=$total" -ForegroundColor Yellow
        if ($total -ge 1) {
            $found = $true
            Write-Host "FIRST ITERATION DETECTED" -ForegroundColor Green
            $r | ConvertTo-Json -Depth 6
            break
        }
    } catch {
        Write-Host "[$elapsed s] err: $_" -ForegroundColor Red
    }
}

if (-not $found) {
    Write-Host "TIMEOUT after $maxWait s -- no iteration yet" -ForegroundColor Red
    Write-Host "--- Recent log lines mentioning chat_excellence ---" -ForegroundColor Cyan
    $log = Get-ChildItem 'C:\AI_VAULT\tmp_agent\logs\brain_v9_stderr_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($log) {
        Select-String -Path $log.FullName -Pattern "chat_excellence|ChatExcellence|scheduler" -SimpleMatch | Select-Object -Last 30
    }
}
