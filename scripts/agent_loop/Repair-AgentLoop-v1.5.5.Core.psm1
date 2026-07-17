$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
  param(
    [Parameter(Mandatory=$true)][string]$Identity,
    [Parameter(Mandatory=$true)][string]$FilePath,
    [string[]]$ArgumentList = @(),
    [string]$WorkingDirectory = $PWD.Path
  )
  $old = Get-Location
  try {
    Set-Location $WorkingDirectory
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
    Set-Location $old
  }
}

function Invoke-AgentLoopV155DeploymentTransaction {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$ApprovedNewBaseSha,
    [Parameter(Mandatory=$true)][string]$ExpectedFront,
    [Parameter(Mandatory=$true)][int]$ExpectedIssue,
    [Parameter(Mandatory=$true)][int]$ExpectedPr,
    [Parameter(Mandatory=$true)][string]$ExpectedWorkBranch,
    [Parameter(Mandatory=$true)][string]$ExpectedPrHead,
    [Parameter(Mandatory=$true)][string]$ApprovedControlPlaneCommit,
    [Parameter(Mandatory=$true)][string]$ApprovedWorkerSha256,
    [scriptblock]$StopTask = { param($TaskName) Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue },
    [scriptblock]$DisableTask = { param($TaskName) Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null },
    [scriptblock]$GetTaskState = { param($TaskName) (Get-ScheduledTask -TaskName $TaskName).State },
    [scriptblock]$GetHash = { param($Path) (Get-FileHash $Path -Algorithm SHA256).Hash },
    [scriptblock]$GetRepoHead = { param($RepoPath) (Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $RepoPath | Out-String).Trim() },
    [scriptblock]$RunRepoCommand = { param($RepoPath, [string[]]$CommandArgs) Invoke-NativeChecked -Identity ($CommandArgs -join ' ') -FilePath $CommandArgs[0] -ArgumentList $CommandArgs[1..($CommandArgs.Count-1)] -WorkingDirectory $RepoPath | Out-Null },
    [scriptblock]$Recovery = { param($SourceWorker, $InstallRoot, $ExpectedIssue, $ApprovedNewBaseSha, $ExpectedPrHead, $ApprovedWorkerSha256) Invoke-NativeChecked -Identity "python trusted-v155-deploy-recover" -FilePath "python" -ArgumentList @($SourceWorker, "--config", "$InstallRoot\config\worker.json", "--trusted-v155-deploy-recover-existing-pr", [string]$ExpectedIssue, "--expected-base-sha", $ApprovedNewBaseSha, "--expected-pr-head", $ExpectedPrHead, "--source-worker", $SourceWorker, "--approved-worker-sha256", $ApprovedWorkerSha256) | Out-Null },
    [scriptblock]$WriteLine = { param($Message) Write-Host $Message }
  )
  $TaskName = "AI_Vault_Kimi_GitHub_Worker"
  & $StopTask $TaskName
  & $DisableTask $TaskName
  $taskState = & $GetTaskState $TaskName
  if ($taskState -ne "Disabled") { throw "Scheduled task is not Disabled: $taskState" }
  $repoHead = & $GetRepoHead $Repo
  if ($repoHead -ne $ApprovedControlPlaneCommit) { throw "Unexpected control-plane HEAD: $repoHead" }

  & $RunRepoCommand $Repo @("python", "-m", "py_compile", "scripts/agent_loop/local_worker/agent_worker.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v153_base_advance.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v154_repair.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v154_transaction_notifications.py")
  & $RunRepoCommand $Repo @("python", "tests/contract/test_agent_loop_worker_v155_quiescence_recovery.py")
  & $RunRepoCommand $Repo @("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/contract/test_agent_loop_worker_v155_deploy_recovery.ps1")

  $sourceWorker = Join-Path $Repo "scripts\agent_loop\local_worker\agent_worker.py"
  $sourceSha = & $GetHash $sourceWorker
  if ($sourceSha -ne $ApprovedWorkerSha256) { throw "Unexpected worker source SHA-256: $sourceSha" }
  try {
    & $Recovery $sourceWorker $InstallRoot $ExpectedIssue $ApprovedNewBaseSha $ExpectedPrHead $ApprovedWorkerSha256
  } catch {
    $primaryFailure = $_.Exception.Message
    try { if ((& $GetTaskState $TaskName) -ne "Disabled") { & $WriteLine "ROLLBACK_TASK_STATE=$(& $GetTaskState $TaskName)" } } catch { & $WriteLine "ROLLBACK_TASK_CHECK_ERROR=$($_.Exception.Message)" }
    throw $primaryFailure
  }
  $installedWorker = Join-Path $InstallRoot "worker\agent_worker.py"
  $sha = & $GetHash $installedWorker
  if ($sha -ne $ApprovedWorkerSha256) { throw "Installed worker SHA-256 mismatch after recovery: $sha" }
  & $WriteLine "PASS: installed worker v1.5.5; recovered PR #6; scheduled task remains disabled"
  & $WriteLine "installed_sha256=$sha"
  & $WriteLine "manual_one_run=powershell -NoProfile -Command python C:\AI_VAULT_AGENT_WORKER\worker\agent_worker.py --config C:\AI_VAULT_AGENT_WORKER\config\worker.json --once"
}

Export-ModuleMember -Function Invoke-AgentLoopV155DeploymentTransaction, Invoke-NativeChecked
