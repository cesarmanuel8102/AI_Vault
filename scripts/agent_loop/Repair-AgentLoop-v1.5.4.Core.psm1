Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
  param(
    [Parameter(Mandatory=$true)][string]$Identity,
    [Parameter(Mandatory=$true)][string]$FilePath,
    [string[]]$ArgumentList = @(),
    [string]$WorkingDirectory
  )
  $oldLocation = Get-Location
  try {
    if ($WorkingDirectory) { Set-Location $WorkingDirectory }
    $output = & $FilePath @ArgumentList 2>&1
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) {
      $tail = (($output | Out-String) -replace '[\r\n]+',' ').Trim()
      if ($tail.Length -gt 1000) { $tail = $tail.Substring($tail.Length - 1000) }
      throw "native command failed: $Identity exit=$code output=$tail"
    }
    return $output
  } finally {
    if ($WorkingDirectory) { Set-Location $oldLocation }
  }
}

function Invoke-AgentLoopV154DeploymentTransaction {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$ApprovedNewBaseSha,
    [Parameter(Mandatory=$true)][string]$ExpectedFront,
    [Parameter(Mandatory=$true)][int]$ExpectedIssue,
    [Parameter(Mandatory=$true)][int]$ExpectedPr,
    [Parameter(Mandatory=$true)][string]$ExpectedWorkBranch,
    [Parameter(Mandatory=$true)][string]$ExpectedOldPrHead,
    [Parameter(Mandatory=$true)][string]$ApprovedControlPlaneCommit,
    [Parameter(Mandatory=$true)][string]$ApprovedWorkerSha256,
    [scriptblock]$StopTask = { param($TaskName) Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue },
    [scriptblock]$DisableTask = { param($TaskName) Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null },
    [scriptblock]$GetTaskState = { param($TaskName) (Get-ScheduledTask -TaskName $TaskName).State },
    [scriptblock]$GetRepoHead = { param($RepoPath) (Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $RepoPath | Out-String).Trim() },
    [scriptblock]$RunRepoCommand = { param($RepoPath, [string[]]$CommandArgs) Invoke-NativeChecked -Identity $CommandArgs[0] -FilePath $CommandArgs[0] -ArgumentList $CommandArgs[1..($CommandArgs.Count-1)] -WorkingDirectory $RepoPath | Out-Null },
    [scriptblock]$GetHash = { param($Path) (Get-FileHash $Path -Algorithm SHA256).Hash },
    [scriptblock]$CopyFile = { param($Source, $Destination) Copy-Item $Source $Destination -Force },
    [scriptblock]$TrustedResume = { param($WorkerPath, $InstallRoot, $ExpectedIssue, $ExpectedFront, $ApprovedNewBaseSha, $ExpectedPr, $ExpectedWorkBranch, $ExpectedOldPrHead) Invoke-NativeChecked -Identity "python trusted-v154-resume" -FilePath "python" -ArgumentList @($WorkerPath, "--config", "$InstallRoot\config\worker.json", "--trusted-v154-resume-existing-pr", [string]$ExpectedIssue, "--expected-front", $ExpectedFront, "--expected-base-sha", $ApprovedNewBaseSha, "--expected-pr-number", [string]$ExpectedPr, "--expected-work-branch", $ExpectedWorkBranch, "--expected-pr-head", $ExpectedOldPrHead) | Out-Null },
    [scriptblock]$WriteLine = { param($Message) Write-Host $Message }
  )
  $TaskName = "AI_Vault_Kimi_GitHub_Worker"
  & $StopTask $TaskName
  & $DisableTask $TaskName
  $taskState = & $GetTaskState $TaskName
  if ($taskState -ne "Disabled") { throw "Scheduled task is not disabled; refusing install" }

  $head = & $GetRepoHead $Repo
  if (-not $head) { throw "Not a git repo" }
  if ($head -ne $ApprovedControlPlaneCommit) { throw "Unexpected control-plane commit: $head" }

  & $RunRepoCommand $Repo @("python", "-m", "py_compile", "scripts/agent_loop/local_worker/agent_worker.py")
  & $RunRepoCommand $Repo @("python", "-m", "py_compile", "scripts/agent_loop/pilot_verify.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_hardening_02.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v153_regression.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v153_base_advance.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v154_repair.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v154_transaction_notifications.py")
  & $RunRepoCommand $Repo @("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/contract/test_agent_loop_worker_v154_deploy_rollback.ps1")

  $sourceWorker = Join-Path $Repo "scripts\agent_loop\local_worker\agent_worker.py"
  $sourceSha = & $GetHash $sourceWorker
  if ($sourceSha -ne $ApprovedWorkerSha256) { throw "Unexpected worker source SHA-256: $sourceSha" }

  $stamp = Get-Date -Format "yyyyMMddTHHmmssZ"
  $installedWorker = Join-Path $InstallRoot "worker\agent_worker.py"
  $statePath = Join-Path $InstallRoot "state\issue-5.json"
  $workerBackup = Join-Path $InstallRoot "worker\agent_worker.py.bak-v154-$stamp"
  $stateBackup = Join-Path $InstallRoot "state\issue-5.json.bak-v154-$stamp"

  & $CopyFile $installedWorker $workerBackup
  & $CopyFile $statePath $stateBackup
  try {
    & $CopyFile $sourceWorker $installedWorker
    $sha = & $GetHash $installedWorker
    if ($sha -ne $ApprovedWorkerSha256) { throw "Installed worker SHA-256 mismatch: $sha" }
    & $TrustedResume $installedWorker $InstallRoot $ExpectedIssue $ExpectedFront $ApprovedNewBaseSha $ExpectedPr $ExpectedWorkBranch $ExpectedOldPrHead
  } catch {
    $primaryFailure = $_.Exception.Message
    $rollbackOk = $true
    try { & $CopyFile $workerBackup $installedWorker } catch { $rollbackOk = $false; & $WriteLine "ROLLBACK_WORKER_ERROR=$($_.Exception.Message)" }
    try { & $CopyFile $stateBackup $statePath } catch { $rollbackOk = $false; & $WriteLine "ROLLBACK_STATE_ERROR=$($_.Exception.Message)" }
    try {
      $taskAfterFailure = & $GetTaskState $TaskName
      if ($taskAfterFailure -ne "Disabled") { $rollbackOk = $false; & $WriteLine "ROLLBACK_TASK_STATE=$taskAfterFailure" }
    } catch { $rollbackOk = $false; & $WriteLine "ROLLBACK_TASK_CHECK_ERROR=$($_.Exception.Message)" }
    if ($rollbackOk) { & $WriteLine "ROLLBACK_STATUS=PASS" } else { & $WriteLine "ROLLBACK_STATUS=FAIL" }
    throw $primaryFailure
  }
  & $WriteLine "PASS: installed worker v1.5.4; scheduled task remains disabled"
  & $WriteLine "installed_sha256=$sha"
  & $WriteLine "events_path=$InstallRoot\reports\worker-events.jsonl"
  & $WriteLine "rollback_worker=Copy-Item '$workerBackup' '$installedWorker' -Force"
  & $WriteLine "manual_one_run=powershell -NoProfile -Command python C:\AI_VAULT_AGENT_WORKER\worker\agent_worker.py --config C:\AI_VAULT_AGENT_WORKER\config\worker.json --once"
  & $WriteLine "rollback_state=Copy-Item '$stateBackup' '$statePath' -Force"
}

Export-ModuleMember -Function Invoke-AgentLoopV154DeploymentTransaction, Invoke-NativeChecked
