# Process Kill Candidate Classification

- status: `NO_SAFE_LOCK_PROCESS_CANDIDATE_FOUND`
- candidate_processes_detected: `10`
- safe_candidates_count: `0`

## Candidates
- PID `244420` `python.exe` category `python` safe_to_close `false` reason: does not clearly reference absolute C:\AI_VAULT cmd: ``
- PID `23388` `ollama.exe` category `ollama_denied` safe_to_close `false` reason: protected/system/denylisted process; does not clearly reference absolute C:\AI_VAULT cmd: ``
- PID `265004` `python.exe` category `python` safe_to_close `false` reason: does not clearly reference absolute C:\AI_VAULT; QC/strategy runner detected; not closed because absolute legacy path/handle ownership is unproven and trading/QC should not be interrupted by this front cmd: `"C:\Users\cesar\AppData\Local\Programs\Python\Python311\python.exe" tmp_agent\strategies\mean_reversion_eq\run_phase311_bull_put_guard_qc_revalidation_2026-06-12.py guard_risk10_width10_delta195`
- PID `27224` `node.exe` category `node` safe_to_close `false` reason: does not clearly reference absolute C:\AI_VAULT cmd: ``
- PID `22300` `powershell.exe` category `shell` safe_to_close `false` reason: does not clearly reference absolute C:\AI_VAULT cmd: ``
- PID `262024` `powershell.exe` category `shell` safe_to_close `false` reason: protected/system/denylisted process; does not clearly reference absolute C:\AI_VAULT cmd: `powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference = 'Stop'; $cpuByPid = @{}; Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | ForEach-Object { $cpuByPid[[int]$_.IDProcess] = [double]$_.PercentProcessorTime }; Get-CimInstance ...`
- PID `260828` `powershell.exe` category `shell` safe_to_close `false` reason: protected/system/denylisted process; does not clearly reference absolute C:\AI_VAULT cmd: `powershell.exe -NoProfile -NonInteractive -Command "$ErrorActionPreference = 'Stop'; $cpuByPid = @{}; Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | ForEach-Object { $cpuByPid[[int]$_.IDProcess] = [double]$_.PercentProcessorTime }; Get-CimInstance ...`
- PID `10488` `pwsh.exe` category `shell` safe_to_close `false` reason: does not clearly reference absolute C:\AI_VAULT cmd: `"C:\Program Files\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -NonInteractive -EncodedCommand JABFAHIAcgBvAHIAQQBjAHQAaQBvAG4AUAByAGUAZgBlAHIAZQBuAGMAZQAgAD0AIAAnAFMAdABvAHAAJwANAAoAJABQAHIAbwBnAHIAZQBzAHMAUAByAGUAZgBlAHIAZQBuAGMAZQAgAD0AIAAnAFMAaQBsAGUAbgB0AGwA...`
- PID `31272` `pwsh.exe` category `shell` safe_to_close `false` reason: does not clearly reference absolute C:\AI_VAULT cmd: ``
- PID `257296` `pwsh.exe` category `shell` safe_to_close `false` reason: references canonical path; denied; does not clearly reference absolute C:\AI_VAULT cmd: `"C:\Program Files\PowerShell\7\pwsh.exe" -Command "try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
$root='C:\AI_VAULT_CANONICAL'
$outDir=Join-Path $root 'tmp_agent\front_legacy_lock_release_and_quarantine_retry_01'
$disc=[ordered]@{sche...`
