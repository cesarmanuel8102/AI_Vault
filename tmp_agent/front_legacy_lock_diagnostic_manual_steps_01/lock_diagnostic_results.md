# Lock Diagnostic Results

Read-only diagnostics only. No process was killed, no service was stopped, and no settings were changed.

## Process CommandLine Matches
- PID 262592 pwsh.exe: "C:\Program Files\PowerShell\7\pwsh.exe" -Command "try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
$root='C:\AI_VAULT_CANONICAL'
$outDir=Join-Path $root 'tmp_agent\front_legacy_lock_diagnostic_manual_steps_01'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$results=[ordered]@{
  schema_version='front_legacy_lock_diagnostic_manual_steps_01_lock_diagnostic_v1'
  generated_at_utc=(Get-Date).ToUniversalTime().ToString('o')
  process_commandline_matches=@()
  process_path_matches=@()
  known_ports=@()
  named_processes=@()
  handle_tool=[ordered]@{where_handle=@(); where_handle64=@(); installed=$false; output=''; error=$null}
  defender_search_notes=@('Windows Search/Defender not modified. If no user process explains the lock, inspect manually.')
  no_process_killed=$true
  no_service_stopped=$true
  no_settings_modified=$true
}
try {
  $results.process_commandline_matches = @(Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | Where-Object { $_.CommandLine -match 'AI_VAULT' } | ForEach-Object { [ordered]@{ProcessId=$_.ProcessId; Name=$_.Name; CommandLine=$_.CommandLine} })
} catch { $results.process_commandline_error = $_.Exception.Message }
try {
  $results.process_path_matches = @(Get-Process | Select-Object Id,ProcessName,Path | Where-Object { $_.Path -match 'AI_VAULT' } | ForEach-Object { [ordered]@{Id=$_.Id; ProcessName=$_.ProcessName; Path=$_.Path} })
} catch { $results.process_path_error = $_.Exception.Message }
foreach ($port in 8090,8010,3000,11434) {
  try {
    $conns = @(Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess)
    foreach ($c in $conns) {
      $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
      $results.known_ports += [ordered]@{port=$port; state=[string]$c.State; owning_process=$c.OwningProcess; process_name=$proc.ProcessName; path=$proc.Path}
    }
  } catch { $results.known_ports += [ordered]@{port=$port; error=$_.Exception.Message} }
}
foreach ($name in @('python','python3','uvicorn','node','ollama','docker')) {
  try {
    $procs = @(Get-Process -Name $name -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path,StartTime)
    foreach ($proc in $procs) { $results.named_processes += [ordered]@{query=$name; Id=$proc.Id; ProcessName=$proc.ProcessName; Path=$proc.Path; StartTime=($proc.StartTime.ToString('o'))} }
  } catch { $results.named_processes += [ordered]@{query=$name; error=$_.Exception.Message} }
}
try { $results.handle_tool.where_handle = @((where.exe handle 2>$null)) } catch {}
try { $results.handle_tool.where_handle64 = @((where.exe handle64 2>$null)) } catch {}
$handleExe=$null
if ($results.handle_tool.where_handle64.Count -gt 0) { $handleExe=$results.handle_tool.where_handle64[0] }
elseif ($results.handle_tool.where_handle.Count -gt 0) { $handleExe=$results.handle_tool.where_handle[0] }
if ($handleExe) {
  $results.handle_tool.installed=$true
  try { $results.handle_tool.output = (& $handleExe 'C:\AI_VAULT' 2>&1 | Out-String) } catch { $results.handle_tool.error=$_.Exception.Message }
} else { $results.handle_tool.output='HANDLE_TOOL_NOT_INSTALLED' }
$jsonPath=Join-Path $outDir 'lock_diagnostic_results.json'
$mdPath=Join-Path $outDir 'lock_diagnostic_results.md'
$results | ConvertTo-Json -Depth 8 | Set-Content -Path $jsonPath -Encoding UTF8
$md = New-Object System.Collections.Generic.List[string]
$md.Add('# Lock Diagnostic Results')
$md.Add('')
$md.Add('Read-only diagnostics only. No process was killed, no service was stopped, and no settings were changed.')
$md.Add('')
$md.Add('## Process CommandLine Matches')
foreach ($proc in $results.process_commandline_matches) { $md.Add(('- PID {0} {1}: {2}' -f $proc.ProcessId, $proc.Name, $proc.CommandLine)) }
if ($results.process_commandline_matches.Count -eq 0) { $md.Add('- none') }
$md.Add('')
$md.Add('## Process Path Matches')
foreach ($proc in $results.process_path_matches) { $md.Add(('- PID {0} {1}: {2}' -f $proc.Id, $proc.ProcessName, $proc.Path)) }
if ($results.process_path_matches.Count -eq 0) { $md.Add('- none') }
$md.Add('')
$md.Add('## Known Ports')
foreach ($portRow in $results.known_ports) { $md.Add(('- port {0}: PID {1} {2} state {3} path {4}' -f $portRow.port, $portRow.owning_process, $portRow.process_name, $portRow.state, $portRow.path)) }
if ($results.known_ports.Count -eq 0) { $md.Add('- no listeners/connections found on checked ports') }
$md.Add('')
$md.Add('## Named Processes')
foreach ($proc in $results.named_processes) { $md.Add(('- {0}: PID {1} {2} path {3} start {4}' -f $proc.query, $proc.Id, $proc.ProcessName, $proc.Path, $proc.StartTime)) }
if ($results.named_processes.Count -eq 0) { $md.Add('- none') }
$md.Add('')
$md.Add('## Handle Tool')
$md.Add(('- installed: {0}' -f $results.handle_tool.installed))
$md.Add(('- output: {0}' -f $results.handle_tool.output))
$md.Add('')
$md.Add('## Windows Search / Defender')
$md.Add('- not modified; document as possible manual inspection if no clear user process explains the lock.')
$md | Set-Content -Path $mdPath -Encoding UTF8
$results | ConvertTo-Json -Depth 8"

## Process Path Matches
- none

## Known Ports
- port 8090: PID 0 Idle state TimeWait path 
- port 8090: PID 244420 python state Listen path 
- port 8090: PID 244420 python state FinWait2 path 
- port 8090: PID 0 Idle state TimeWait path 
- port 8090: PID 0 Idle state TimeWait path 
- port 8090: PID 0 Idle state TimeWait path 
- port 11434: PID 23388 ollama state Listen path 

## Named Processes
- python: PID 244420 python path  start 2026-06-11T03:34:25.3805715-04:00
- python: PID 265004 python path C:\Users\cesar\AppData\Local\Programs\Python\Python311\python.exe start 2026-06-11T23:23:42.2913627-04:00
- node: PID 27224 node path  start 2026-06-06T12:44:12.4226737-04:00
- ollama: PID 23388 ollama path  start 2026-06-06T12:20:15.5155116-04:00

## Handle Tool
- installed: False
- output: HANDLE_TOOL_NOT_INSTALLED

## Windows Search / Defender
- not modified; document as possible manual inspection if no clear user process explains the lock.
