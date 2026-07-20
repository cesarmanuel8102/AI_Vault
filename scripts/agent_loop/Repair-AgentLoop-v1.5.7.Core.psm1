$ErrorActionPreference = "Stop"

function Get-Sha256 {
  param([Parameter(Mandatory=$true)][string]$Path)
  $stream = [System.IO.File]::OpenRead($Path)
  try {
    $bytes = [System.Security.Cryptography.SHA256]::Create().ComputeHash($stream)
    return ([BitConverter]::ToString($bytes) -replace "-").ToUpper()
  }
  finally { $stream.Dispose() }
}

function ConvertTo-NativeArgument {
  param([AllowNull()][string]$Argument)
  if ($null -eq $Argument) { $Argument = "" }
  if ($Argument -eq "") { return '""' }
  if ($Argument -notmatch '[\s"]') { return $Argument }
  $escaped = New-Object System.Text.StringBuilder
  [void]$escaped.Append('"')
  $slashes = 0
  foreach ($char in $Argument.ToCharArray()) {
    if ($char -eq '\') {
      $slashes += 1
      continue
    }
    if ($char -eq '"') {
      [void]$escaped.Append('\' * (($slashes * 2) + 1))
      [void]$escaped.Append('"')
      $slashes = 0
      continue
    }
    if ($slashes -gt 0) {
      [void]$escaped.Append('\' * $slashes)
      $slashes = 0
    }
    [void]$escaped.Append($char)
  }
  if ($slashes -gt 0) { [void]$escaped.Append('\' * ($slashes * 2)) }
  [void]$escaped.Append('"')
  return $escaped.ToString()
}

function Invoke-NativeChecked {
  param(
    [Parameter(Mandatory=$true)][string]$Identity,
    [Parameter(Mandatory=$true)][string]$FilePath,
    [string[]]$ArgumentList = @(),
    [string]$WorkingDirectory = $PWD.Path,
    [int]$TimeoutSeconds = 120
  )
  $old = Get-Location
  try {
    Set-Location -LiteralPath $WorkingDirectory
    # Capture stdout and stderr separately so real errors are preserved.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = ($ArgumentList | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    if (-not $proc.WaitForExit([Math]::Max(1, $TimeoutSeconds) * 1000)) {
      try { $proc.Kill() } catch {}
      throw "native command timed out: $Identity"
    }
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $code = $proc.ExitCode
    if ($null -eq $code) { $code = 0 }
    $tail = (($stdout + " " + $stderr) -replace '[\r\n]+',' ').Trim()
    if ($tail.Length -gt 1200) { $tail = $tail.Substring($tail.Length - 1200) }
    if ($code -ne 0) {
      throw "native command failed: $Identity exit=$code output=$tail"
    }
    # Surface non-empty stderr as a warning record when the command succeeded.
    if ($stderr.Trim()) {
      Write-Warning "[$Identity] stderr: $($stderr.Trim())"
    }
    return $stdout
  }
  finally {
    Set-Location -LiteralPath $old
  }
}

function Get-ControlPlaneStatusLines {
  param([Parameter(Mandatory=$true)][string]$Repo)
  $text = (Invoke-NativeChecked -Identity "git status" -FilePath "git" -ArgumentList @("status", "--porcelain", "--untracked-files=all") -WorkingDirectory $Repo | Out-String)
  return @($text -split "`r?`n" | Where-Object { $_ })
}

function Test-AllowedBytecodeStatusLine {
  param([Parameter(Mandatory=$true)][string]$Line)
  if (-not $Line.StartsWith("?? ")) { return $false }
  $path = $Line.Substring(3).Replace("\", "/")
  return ($path -match '(^|/)__pycache__/$' -or $path -match '(^|/)__pycache__/.*\.pyc$' -or $path -match '\.pyc$')
}

function Assert-ControlPlaneStatusSnapshot {
  param([Parameter(Mandatory=$true)][string]$Repo)
  $lines = @(Get-ControlPlaneStatusLines -Repo $Repo)
  foreach ($line in $lines) {
    if ($line.StartsWith("?? ")) {
      if (-not (Test-AllowedBytecodeStatusLine -Line $line)) {
        throw "Unexpected untracked file in control-plane checkout: $line"
      }
      continue
    }
    throw "Tracked or staged change in control-plane checkout: $line"
  }
  return @($lines | Sort-Object)
}

function Restore-ControlPlaneStatusSnapshot {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [string[]]$BeforeLines = @()
  )
  $before = @($BeforeLines | Sort-Object)
  $current = @(Get-ControlPlaneStatusLines -Repo $Repo | Sort-Object)
  foreach ($line in $current) {
    if (($before -notcontains $line) -and -not (Test-AllowedBytecodeStatusLine -Line $line)) {
      throw "Unexpected checkout artifact created during validation: $line"
    }
    if (-not $line.StartsWith("?? ")) {
      throw "Tracked or staged change created during validation: $line"
    }
  }
  $generated = @($current | Where-Object { ($before -notcontains $_) -and (Test-AllowedBytecodeStatusLine -Line $_) })
  $repoRoot = (Resolve-Path -LiteralPath $Repo).Path.TrimEnd('\')
  foreach ($line in $generated) {
    $relative = $line.Substring(3).Replace("/", "\")
    $target = Join-Path $repoRoot $relative
    if (-not $target.StartsWith($repoRoot + "\")) { throw "Refusing bytecode cleanup outside repo: $relative" }
    if ($relative -notmatch '(^|\\)__pycache__(\\|$)' -and $relative -notmatch '\.pyc$') {
      throw "Refusing non-bytecode cleanup: $relative"
    }
    if (Test-Path -LiteralPath $target) {
      Remove-Item -LiteralPath $target -Recurse -Force
    }
  }
  $final = @(Get-ControlPlaneStatusLines -Repo $Repo | Sort-Object)
  $beforeText = ($before -join "`n")
  $finalText = ($final -join "`n")
  if ($beforeText -ne $finalText) {
    throw "Control-plane checkout did not return to the original status snapshot"
  }
}

function Test-AgentLoopV157WorkerSymbols {
  param([Parameter(Mandatory=$true)][string]$WorkerPath)
  $text = Get-Content -LiteralPath $WorkerPath -Raw
  @("prompt_task_sentinel", "validate_executor_delivery", "_require_lossless_opencode_transport",
    "_opencode_node_entrypoint", "STATE_SCHEMA_VERSION", "EVENT_REQUIRED_FIELDS") | ForEach-Object {
    if ($text -notmatch $_) { throw "v157 symbol missing in installed worker: $_" }
  }
}

function Invoke-AgentLoopV157InstallTransaction {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$ApprovedControlPlaneCommit,
    [Parameter(Mandatory=$true)][string]$ApprovedWorkerSha256,
    [string]$TaskName = "AI_Vault_Kimi_GitHub_Worker",
    [scriptblock]$StopTask = { param($Name) Stop-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue },
    [scriptblock]$DisableTask = { param($Name) Disable-ScheduledTask -TaskName $Name -ErrorAction Stop | Out-Null },
    [scriptblock]$GetTaskState = { param($Name) (Get-ScheduledTask -TaskName $Name).State },
    [scriptblock]$GetHash = { param($Path) (Get-Sha256 $Path) },
    [scriptblock]$AfterCopyHook = { param($InstallRoot) },
    [scriptblock]$BeforeSmokeHook = { param($InstallRoot) },
    [scriptblock]$WriteLine = { param($Message) Write-Host $Message }
  )

  if ($InstallRoot -like "C:\AI_VAULT_CANONICAL*") { throw "Refusing canonical install root" }

  & $StopTask $TaskName
  & $DisableTask $TaskName
  if ((& $GetTaskState $TaskName) -ne "Disabled") { throw "Scheduled task is not Disabled" }

  $repoHead = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $Repo) | Out-String).Trim()
  if ($repoHead -ne $ApprovedControlPlaneCommit) { throw "Unexpected control-plane HEAD: $repoHead" }
  $repoStatusSnapshot = @(Assert-ControlPlaneStatusSnapshot -Repo $Repo)

  $commands = @(
    @("python", "-m", "py_compile", "$Repo\scripts\agent_loop\local_worker\agent_worker.py"),
    @("python", "$Repo\tests\contract\test_agent_loop_worker_v157_runtime_resolution.py"),
    @("python", "$Repo\tests\contract\test_agent_loop_worker_v157_real_cmd_quoting.py"),
    @("python", "$Repo\tests\contract\test_agent_loop_worker_v157_lossless_transport.py"),
    @("python", "$Repo\tests\contract\test_agent_loop_worker_v157_prompt_delivery.py"),
    @("python", "$Repo\tests\contract\test_agent_loop_worker_v157_state_event_contract.py"),
    @("python", "$Repo\tests\contract\test_agent_loop_worker_v157_codex_supervisor_contract.py")
  )
  try {
    foreach ($command in $commands) {
      $exe = $command[0]
      $args = $command[1..($command.Count-1)]
      $id = ($command | ForEach-Object { '"' + $_ + '"' }) -join ' '
      Invoke-NativeChecked -Identity $id -FilePath $exe -ArgumentList $args -WorkingDirectory $Repo | Out-Null
    }
  }
  finally {
    Restore-ControlPlaneStatusSnapshot -Repo $Repo -BeforeLines $repoStatusSnapshot
  }

  $sourceWorker = Join-Path $Repo "scripts\agent_loop\local_worker\agent_worker.py"
  $sourceWorkerContract = Join-Path $Repo "scripts\agent_loop\local_worker\worker_contract.json"
  $sourceHash = & $GetHash $sourceWorker
  if ($sourceHash -ne $ApprovedWorkerSha256) { throw "Approved worker SHA mismatch" }
  Test-AgentLoopV157WorkerSymbols -WorkerPath $sourceWorker

  $installWorker = Join-Path $InstallRoot "worker\agent_worker.py"
  $installConfig = Join-Path $InstallRoot "config\worker.json"
  $installWorkerContract = Join-Path $InstallRoot "config\worker_contract.json"
  $installState = Join-Path $InstallRoot "state"
  $installReports = Join-Path $InstallRoot "reports"

  if (Test-Path -LiteralPath $installConfig -PathType Leaf) {
    try {
      Get-Content -LiteralPath $installConfig -Raw | ConvertFrom-Json | Out-Null
    }
    catch {
      throw "Invalid existing worker config"
    }
  }

  $originalWorker = $null
  $originalWorkerBytes = $null
  $originalWorkerContract = $null
  $originalWorkerContractBytes = $null
  $originalConfig = $null
  $originalConfigHash = $null
  $stamp = (Get-Date -Format "yyyyMMddTHHmmssZ")
  $backupDir = Join-Path $InstallRoot "backups\v157-$stamp"
  New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

  $mutationStarted = $false
  try {
    if (Test-Path -LiteralPath $installWorker -PathType Leaf) {
      $originalWorker = & $GetHash $installWorker
      $originalWorkerBytes = [IO.File]::ReadAllBytes($installWorker)
      Copy-Item -LiteralPath $installWorker -Destination (Join-Path $backupDir "agent_worker.py.bak") -Force
    }
    if (Test-Path -LiteralPath $installWorkerContract -PathType Leaf) {
      $originalWorkerContract = & $GetHash $installWorkerContract
      $originalWorkerContractBytes = [IO.File]::ReadAllBytes($installWorkerContract)
      Copy-Item -LiteralPath $installWorkerContract -Destination (Join-Path $backupDir "worker_contract.json.bak") -Force
    }
    if (Test-Path -LiteralPath $installConfig -PathType Leaf) {
      $originalConfig = Get-Content -LiteralPath $installConfig -Raw
      $originalConfigHash = & $GetHash $installConfig
      Copy-Item -LiteralPath $installConfig -Destination (Join-Path $backupDir "worker.json.bak") -Force
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $installWorker) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path $installConfig) | Out-Null
    New-Item -ItemType Directory -Force -Path $installState | Out-Null
    New-Item -ItemType Directory -Force -Path $installReports | Out-Null

    $mutationStarted = $true
    Copy-Item -LiteralPath $sourceWorker -Destination $installWorker -Force
    Copy-Item -LiteralPath $sourceWorkerContract -Destination $installWorkerContract -Force
    & $AfterCopyHook $InstallRoot
    $installedHash = & $GetHash $installWorker
    if ($installedHash -ne $ApprovedWorkerSha256) { throw "Installed worker SHA mismatch" }
    Test-AgentLoopV157WorkerSymbols -WorkerPath $installWorker
    & $BeforeSmokeHook $InstallRoot

    # Post-install smoke: the installed worker must be importable and version check passes.
    $smoke = (Invoke-NativeChecked -Identity "worker version smoke" -FilePath "python" -ArgumentList @(
      "-c", "import sys; from pathlib import Path; p=Path(sys.argv[1]); ns={'__name__':'agent_worker_smoke'}; exec(p.read_text(encoding='utf-8'), ns); print(ns['WORKER_VERSION'])", $installWorker
    ) -WorkingDirectory $InstallRoot | Out-String).Trim()
    if ($smoke -ne "1.5.7") { throw "Installed worker smoke failed: $smoke" }

    if ((& $GetTaskState $TaskName) -ne "Disabled") { throw "Scheduled task changed state during transaction" }

    & $WriteLine "PASS: installed v1.5.7 worker to $InstallRoot; scheduled task remains disabled"
    & $WriteLine "V157_DEPLOY_RECOVERY_CONTRACT_PASS"
    & $WriteLine "installed_sha256=$installedHash"
    & $WriteLine "backup_dir=$backupDir"
    & $WriteLine "manual_one_run=powershell -NoProfile -Command python $installWorker --config $installConfig --once"
    return @{ status="INSTALLED_V157"; installed_sha256=$installedHash; backup_dir=$backupDir }
  }
  catch {
    $primary = $_
    if ($mutationStarted) {
      if ($originalWorker) {
        Copy-Item -LiteralPath (Join-Path $backupDir "agent_worker.py.bak") -Destination $installWorker -Force -ErrorAction SilentlyContinue
      }
      elseif (Test-Path -LiteralPath $installWorker) { Remove-Item -LiteralPath $installWorker -Force -ErrorAction SilentlyContinue }
      if ($originalWorkerContract) {
        Copy-Item -LiteralPath (Join-Path $backupDir "worker_contract.json.bak") -Destination $installWorkerContract -Force -ErrorAction SilentlyContinue
      }
      elseif (Test-Path -LiteralPath $installWorkerContract) { Remove-Item -LiteralPath $installWorkerContract -Force -ErrorAction SilentlyContinue }
      if ($originalConfig) {
        Copy-Item -LiteralPath (Join-Path $backupDir "worker.json.bak") -Destination $installConfig -Force -ErrorAction SilentlyContinue
      }
      if ($originalWorker -and ((& $GetHash $installWorker) -ne $originalWorker)) { throw "ROLLBACK_FAILED: worker hash mismatch after rollback; primary=$($primary.Exception.Message)" }
      if ((-not $originalWorker) -and (Test-Path -LiteralPath $installWorker)) { throw "ROLLBACK_FAILED: new worker still exists after rollback; primary=$($primary.Exception.Message)" }
      if ($originalWorkerContract -and ((& $GetHash $installWorkerContract) -ne $originalWorkerContract)) { throw "ROLLBACK_FAILED: worker_contract hash mismatch after rollback; primary=$($primary.Exception.Message)" }
      if ((-not $originalWorkerContract) -and (Test-Path -LiteralPath $installWorkerContract)) { throw "ROLLBACK_FAILED: new worker_contract still exists after rollback; primary=$($primary.Exception.Message)" }
      if ($originalConfigHash -and ((& $GetHash $installConfig) -ne $originalConfigHash)) { throw "ROLLBACK_FAILED: worker.json hash mismatch after rollback; primary=$($primary.Exception.Message)" }
      if ((& $GetTaskState $TaskName) -ne "Disabled") { throw "ROLLBACK_FAILED: scheduled task is not Disabled; primary=$($primary.Exception.Message)" }
    }
    throw $primary
  }
}

Export-ModuleMember -Function Invoke-AgentLoopV157InstallTransaction, Invoke-NativeChecked, Test-AgentLoopV157WorkerSymbols, Get-Sha256, Assert-ControlPlaneStatusSnapshot, Restore-ControlPlaneStatusSnapshot, ConvertTo-NativeArgument
