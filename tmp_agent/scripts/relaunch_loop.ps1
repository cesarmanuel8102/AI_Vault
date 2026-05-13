# Kill recent python and relaunch with -u
$procs = Get-Process python -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    if ($p.StartTime -gt (Get-Date).AddMinutes(-10)) {
        Stop-Process -Id $p.Id -Force
    }
}
Start-Sleep -Seconds 2
Start-Process python -ArgumentList '-u','C:/AI_VAULT/tmp_agent/scripts/v20b_param_loop_runner.py' -RedirectStandardOutput 'C:/AI_VAULT/tmp_agent/strategies/yoel_options/param_loop_output.log' -RedirectStandardError 'C:/AI_VAULT/tmp_agent/strategies/yoel_options/param_loop_error.log' -NoNewWindow
Write-Output "Launched param loop runner"
