# Force kill ALL python processes on 8090, clear __pycache__, restart
$conns = Get-NetTCPConnection -LocalPort 8090 -ErrorAction SilentlyContinue
foreach ($c in $conns) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2

# Clear pycache to ensure fresh bytecode
$pycacheDirs = Get-ChildItem -Path 'C:\AI_VAULT\tmp_agent\brain_v9' -Recurse -Directory -Filter '__pycache__'
foreach ($d in $pycacheDirs) {
    Remove-Item -Path $d.FullName -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Cleared: $($d.FullName)"
}

# Restart with stderr/stdout captured to log files
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$logDir = 'C:\AI_VAULT\tmp_agent\logs'
$stdoutLog = "$logDir\brain_v9_stdout_$ts.log"
$stderrLog = "$logDir\brain_v9_stderr_$ts.log"

Start-Process -FilePath python -ArgumentList '-m','brain_v9.main' `
    -WorkingDirectory 'C:\AI_VAULT\tmp_agent' `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog

Start-Sleep -Seconds 6
try {
    $health = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8090/health).Content
    Write-Host "Health: $health"
    Write-Host "Logs: $stderrLog"
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
}
