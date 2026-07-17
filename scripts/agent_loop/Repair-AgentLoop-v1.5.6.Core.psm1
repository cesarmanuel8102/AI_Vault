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
    Set-Location -LiteralPath $WorkingDirectory
    $output = & $FilePath @ArgumentList 2>&1
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) {
      $tail = (($output | Out-String) -replace '[\r\n]+',' ').Trim()
      if ($tail.Length -gt 1200) { $tail = $tail.Substring($tail.Length - 1200) }
      throw "native command failed: $Identity exit=$code output=$tail"
    }
    return $output
  }
  finally {
    Set-Location -LiteralPath $old
  }
}

function Invoke-AgentLoopV156DeploymentTransaction {
  param(
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$HistoricalBaseSha,
    [Parameter(Mandatory=$true)][string]$PrePr10BaseSha,
    [Parameter(Mandatory=$true)][string]$ApprovedFeatureHead,
    [Parameter(Mandatory=$true)][string]$ApprovedMergedBaseSha,
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
    [scriptblock]$GetHash = { param($Path) (Get-FileHash $Path -Algorithm SHA256).Hash },
    [scriptblock]$GetRepoHead = { param($RepoPath) (Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $RepoPath | Out-String).Trim() },
    [scriptblock]$GetRepoStatus = { param($RepoPath) (Invoke-NativeChecked -Identity "git status --porcelain" -FilePath "git" -ArgumentList @("status", "--porcelain") -WorkingDirectory $RepoPath | Out-String).Trim() },
    [scriptblock]$RunRepoCommand = { param($RepoPath, [string[]]$CommandArgs) Invoke-NativeChecked -Identity ($CommandArgs -join ' ') -FilePath $CommandArgs[0] -ArgumentList $CommandArgs[1..($CommandArgs.Count-1)] -WorkingDirectory $RepoPath | Out-Null },
    [scriptblock]$Recovery = {
      param($RecoveryScript,$SourceWorker,$InstallRoot,$HistoricalBaseSha,$PrePr10BaseSha,$ApprovedFeatureHead,$ApprovedMergedBaseSha,$ApprovedControlPlaneCommit,$ExpectedOldPrHead,$ExpectedFront,$ExpectedPr,$ExpectedWorkBranch,$ApprovedWorkerSha256)
      Invoke-NativeChecked -Identity "python trusted-v156-dynamic-post-merge-recovery" -FilePath "python" -ArgumentList @(
        $RecoveryScript,
        "--config", "$InstallRoot\config\worker.json",
        "--source-worker", $SourceWorker,
        "--approved-worker-sha256", $ApprovedWorkerSha256,
        "--historical-base-sha", $HistoricalBaseSha,
        "--pre-pr10-base-sha", $PrePr10BaseSha,
        "--approved-feature-head", $ApprovedFeatureHead,
        "--approved-merged-base-sha", $ApprovedMergedBaseSha,
        "--approved-control-plane-commit", $ApprovedControlPlaneCommit,
        "--expected-old-pr-head", $ExpectedOldPrHead,
        "--expected-front", $ExpectedFront,
        "--expected-pr-number", [string]$ExpectedPr,
        "--expected-work-branch", $ExpectedWorkBranch
      ) | Out-Null
    },
    [scriptblock]$WriteLine = { param($Message) Write-Host $Message }
  )

  $TaskName = "AI_Vault_Kimi_GitHub_Worker"
  & $StopTask $TaskName
  & $DisableTask $TaskName
  if ((& $GetTaskState $TaskName) -ne "Disabled") { throw "Scheduled task is not Disabled" }

  $repoHead = & $GetRepoHead $Repo
  if ($repoHead -ne $ApprovedControlPlaneCommit) { throw "Unexpected control-plane HEAD: $repoHead" }
  if ($ApprovedControlPlaneCommit -ne $ApprovedMergedBaseSha) { throw "Approved control-plane commit must equal approved merged base" }
  $repoStatus = & $GetRepoStatus $Repo
  if ($repoStatus) { throw "Control-plane checkout is dirty before validation" }

  $commands = @(
    @("python", "-m", "py_compile", "scripts/agent_loop/local_worker/agent_worker.py"),
    @("python", "-m", "py_compile", "scripts/agent_loop/local_worker/v156_recovery_common.py"),
    @("python", "-m", "py_compile", "scripts/agent_loop/local_worker/v156_recovery_transaction.py"),
    @("python", "-m", "py_compile", "scripts/agent_loop/local_worker/v156_post_merge_recovery.py"),
    @("python", "tests/contract/test_agent_loop_worker_v153_base_advance.py"),
    @("python", "tests/contract/test_agent_loop_worker_v154_repair.py"),
    @("python", "tests/contract/test_agent_loop_worker_v154_transaction_notifications.py"),
    @("python", "tests/contract/test_agent_loop_worker_v155_quiescence_recovery.py"),
    @("python", "tests/contract/test_agent_loop_worker_v156_post_merge_recovery.py"),
    @("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "tests/contract/test_agent_loop_worker_v156_deploy_recovery.ps1")
  )
  foreach ($command in $commands) { & $RunRepoCommand $Repo $command }
  $repoStatusAfterTests = & $GetRepoStatus $Repo
  if ($repoStatusAfterTests) { throw "Control-plane checkout became dirty during validation" }

  $sourceWorker = Join-Path $Repo "scripts\agent_loop\local_worker\agent_worker.py"
  $recoveryScript = Join-Path $Repo "scripts\agent_loop\local_worker\v156_post_merge_recovery.py"
  if ((& $GetHash $sourceWorker) -ne $ApprovedWorkerSha256) { throw "Unexpected worker source SHA-256" }
  if (-not (Test-Path -LiteralPath $recoveryScript -PathType Leaf)) { throw "Missing v1.5.6 dynamic recovery helper" }

  & $Recovery $recoveryScript $sourceWorker $InstallRoot $HistoricalBaseSha $PrePr10BaseSha $ApprovedFeatureHead $ApprovedMergedBaseSha $ApprovedControlPlaneCommit $ExpectedOldPrHead $ExpectedFront $ExpectedPr $ExpectedWorkBranch $ApprovedWorkerSha256

  if ((& $GetTaskState $TaskName) -ne "Disabled") { throw "Scheduled task changed state" }
  $installed = Join-Path $InstallRoot "worker\agent_worker.py"
  $installedSha = & $GetHash $installed
  if ($installedSha -ne $ApprovedWorkerSha256) { throw "Installed worker SHA mismatch" }
  & $WriteLine "PASS: installed worker v1.5.6; dynamically advanced/recovered PR #6; scheduled task remains disabled"
  & $WriteLine "installed_sha256=$installedSha"
  & $WriteLine "manual_one_run=powershell -NoProfile -Command python C:\AI_VAULT_AGENT_WORKER\worker\agent_worker.py --config C:\AI_VAULT_AGENT_WORKER\config\worker.json --once"
}

Export-ModuleMember -Function Invoke-AgentLoopV156DeploymentTransaction, Invoke-NativeChecked
