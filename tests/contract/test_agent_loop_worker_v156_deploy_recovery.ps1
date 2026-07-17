$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Import-Module (Join-Path $Root "scripts\agent_loop\Repair-AgentLoop-v1.5.6.Core.psm1") -Force

$Historical = "1" * 40
$Pre = "2" * 40
$Feature = "3" * 40
$Merged = "4" * 40
$OldHead = "5" * 40
$Front = "PILOT-KIMI-CODEX-20260716-091529"
$Branch = "agent/pilot-20260716-091529"

function New-Install {
  $dir = Join-Path ([IO.Path]::GetTempPath()) ("v156-install-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "worker") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "state") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "config") | Out-Null
  Set-Content -LiteralPath (Join-Path $dir "worker\agent_worker.py") -Value "old-worker" -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $dir "state\issue-5.json") -Value '{"cycles":3}' -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $dir "config\worker.json") -Value '{}' -Encoding UTF8
  return $dir
}

function New-Repo {
  $repo = Join-Path ([IO.Path]::GetTempPath()) ("v156-repo-" + [guid]::NewGuid().ToString("N"))
  $local = Join-Path $repo "scripts\agent_loop\local_worker"
  New-Item -ItemType Directory -Force -Path $local | Out-Null
  $source = Join-Path $local "agent_worker.py"
  $helper = Join-Path $local "v156_post_merge_recovery.py"
  Set-Content -LiteralPath $source -Value "new-worker-156" -Encoding UTF8
  Set-Content -LiteralPath $helper -Value "print('helper')" -Encoding UTF8
  return @($repo, $source, $helper, (Get-FileHash $source -Algorithm SHA256).Hash)
}

function Invoke-TestTransaction {
  param(
    $Install,
    $Repo,
    $WorkerSha,
    [scriptblock]$Recovery,
    [string]$RepoHead = $Merged,
    [string]$ControlCommit = $Merged,
    [string]$RepoStatus = ""
  )
  Invoke-AgentLoopV156DeploymentTransaction `
    -Repo $Repo -InstallRoot $Install -HistoricalBaseSha $Historical -PrePr10BaseSha $Pre `
    -ApprovedFeatureHead $Feature -ApprovedMergedBaseSha $Merged -ExpectedFront $Front `
    -ExpectedIssue 5 -ExpectedPr 6 -ExpectedWorkBranch $Branch -ExpectedOldPrHead $OldHead `
    -ApprovedControlPlaneCommit $ControlCommit -ApprovedWorkerSha256 $WorkerSha `
    -StopTask { param($TaskName) } -DisableTask { param($TaskName) } `
    -GetTaskState { param($TaskName) "Disabled" } -GetRepoHead { param($RepoPath) $RepoHead } `
    -GetRepoStatus { param($RepoPath) $RepoStatus } `
    -RunRepoCommand { param($RepoPath, [string[]]$CommandArgs) } -Recovery $Recovery `
    -WriteLine { param($Message) Write-Host $Message }
}

function Test-SuccessArgumentPlumbing {
  $install = New-Install
  $repo, $source, $helper, $sha = New-Repo
  $script:calls = 0
  Invoke-TestTransaction $install $repo $sha {
    param($RecoveryScript,$SourceWorker,$InstallRoot,$HistoricalBaseSha,$PrePr10BaseSha,$ApprovedFeatureHead,$ApprovedMergedBaseSha,$ApprovedControlPlaneCommit,$ExpectedOldPrHead,$ExpectedFront,$ExpectedPr,$ExpectedWorkBranch,$ApprovedWorkerSha256)
    $script:calls += 1
    if ($RecoveryScript -ne $helper -or $SourceWorker -ne $source) { throw "wrong recovery source" }
    if ($HistoricalBaseSha -ne $Historical -or $PrePr10BaseSha -ne $Pre) { throw "wrong base lineage" }
    if ($ApprovedFeatureHead -ne $Feature -or $ApprovedMergedBaseSha -ne $Merged -or $ApprovedControlPlaneCommit -ne $Merged) { throw "wrong post-merge authorization" }
    if ($ExpectedOldPrHead -ne $OldHead -or $ExpectedFront -ne $Front -or $ExpectedPr -ne 6 -or $ExpectedWorkBranch -ne $Branch) { throw "wrong pilot identity" }
    if ($ApprovedWorkerSha256 -ne $sha) { throw "wrong worker SHA" }
    Copy-Item -LiteralPath $SourceWorker -Destination (Join-Path $InstallRoot "worker\agent_worker.py") -Force
  }
  if ($script:calls -ne 1) { throw "atomic recovery not called exactly once" }
  if ((Get-FileHash (Join-Path $install "worker\agent_worker.py") -Algorithm SHA256).Hash -ne $sha) { throw "worker not installed" }
}

function Test-RecoveryFailureDoesNotPrintPass {
  $install = New-Install
  $repo, $source, $helper, $sha = New-Repo
  $before = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  try {
    Invoke-TestTransaction $install $repo $sha { param($a,$b,$c,$d,$e,$f,$g,$h,$i,$j,$k,$l,$m) throw "controlled recovery failure" }
    throw "expected failure"
  } catch {
    if ($_.Exception.Message -notmatch "controlled recovery failure") { throw }
  }
  if ((Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw) -ne $before) { throw "unexpected worker mutation" }
}

function Test-ControlCommitMustEqualMergedBase {
  $install = New-Install
  $repo, $source, $helper, $sha = New-Repo
  $script:recoveryCalled = $false
  try {
    Invoke-TestTransaction $install $repo $sha { param($a,$b,$c,$d,$e,$f,$g,$h,$i,$j,$k,$l,$m) $script:recoveryCalled = $true } -RepoHead ("6" * 40) -ControlCommit ("6" * 40)
    throw "expected authorization failure"
  } catch {
    if ($_.Exception.Message -notmatch "must equal approved merged base") { throw }
  }
  if ($script:recoveryCalled) { throw "recovery ran despite control/merged mismatch" }
}

function Test-DirtyCheckoutFailsBeforeRecovery {
  $install = New-Install
  $repo, $source, $helper, $sha = New-Repo
  $script:recoveryCalled = $false
  try {
    Invoke-TestTransaction $install $repo $sha { param($a,$b,$c,$d,$e,$f,$g,$h,$i,$j,$k,$l,$m) $script:recoveryCalled = $true } -RepoStatus " M scripts/agent_loop/local_worker/v156_recovery_transaction.py"
    throw "expected dirty checkout failure"
  } catch {
    if ($_.Exception.Message -notmatch "checkout is dirty") { throw }
  }
  if ($script:recoveryCalled) { throw "recovery ran with dirty control-plane checkout" }
}

Test-SuccessArgumentPlumbing
Test-RecoveryFailureDoesNotPrintPass
Test-ControlCommitMustEqualMergedBase
Test-DirtyCheckoutFailsBeforeRecovery
Write-Host '{"status":"PASS","tests":["dynamic_arguments","failure","control_equals_merged","dirty_checkout"],"atomic_command":true}'
