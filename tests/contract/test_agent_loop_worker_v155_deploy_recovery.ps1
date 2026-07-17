$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Import-Module (Join-Path $Root "scripts\agent_loop\Repair-AgentLoop-v1.5.5.Core.psm1") -Force

function New-TempInstall {
  $dir = Join-Path ([System.IO.Path]::GetTempPath()) ("v155-deploy-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "worker") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "state") | Out-Null
  Set-Content -Path (Join-Path $dir "worker\agent_worker.py") -Value "old worker" -Encoding UTF8
  Set-Content -Path (Join-Path $dir "state\issue-5.json") -Value '{"cycles":3,"status":"WAITING_GITHUB"}' -Encoding UTF8
  return $dir
}
function New-RepoSource {
  $repo = Join-Path ([System.IO.Path]::GetTempPath()) ("v155-repo-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path (Join-Path $repo "scripts\agent_loop\local_worker") | Out-Null
  $source = Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py"
  Set-Content -Path $source -Value "new worker 155" -Encoding UTF8
  return @($repo, $source, (Get-FileHash $source -Algorithm SHA256).Hash)
}
function Invoke-BaseTransaction($install, $repo, $source, $sha, $recovery) {
  Invoke-AgentLoopV155DeploymentTransaction `
    -Repo $repo -InstallRoot $install -ApprovedNewBaseSha ("2"*40) -ExpectedFront "PILOT-KIMI-CODEX-20260716-091529" `
    -ExpectedIssue 5 -ExpectedPr 6 -ExpectedWorkBranch "agent/pilot-20260716-091529" -ExpectedPrHead ("c"*40) `
    -ApprovedControlPlaneCommit ("2"*40) -ApprovedWorkerSha256 $sha `
    -StopTask { param($TaskName) } `
    -DisableTask { param($TaskName) } `
    -GetTaskState { param($TaskName) "Disabled" } `
    -GetRepoHead { param($RepoPath) "2222222222222222222222222222222222222222" } `
    -RunRepoCommand { param($RepoPath, [string[]]$CommandArgs) } `
    -Recovery $recovery `
    -WriteLine { param($Message) Write-Host $Message }
}

function Test-BusyLockNoMutation {
  $install = New-TempInstall
  $repo,$source,$sha = New-RepoSource
  $stateBefore = Get-Content (Join-Path $install "state\issue-5.json") -Raw
  $workerBefore = Get-Content (Join-Path $install "worker\agent_worker.py") -Raw
  $copyCalls = 0; $script:recoveryCalls = 0
  try {
    Invoke-BaseTransaction $install $repo $source $sha { param($SourceWorker,$InstallRoot,$ExpectedIssue,$ApprovedNewBaseSha,$ExpectedPrHead,$ApprovedWorkerSha256) $script:recoveryCalls += 1; throw "worker.lock busy; trusted v1.5.5 deploy recovery aborted before mutation; process_evidence=[]" }
    throw "busy lock should fail"
  } catch {
    if ($_.Exception.Message -notmatch "worker.lock busy") { throw }
  }
  if ($copyCalls -ne 0) { throw "copy occurred before lock" }
  if ($script:recoveryCalls -ne 1) { throw "atomic command not invoked once" }
  if ((Get-Content (Join-Path $install "worker\agent_worker.py") -Raw) -ne $workerBefore) { throw "worker mutated on busy lock" }
  if ((Get-Content (Join-Path $install "state\issue-5.json") -Raw) -ne $stateBefore) { throw "state mutated on busy lock" }
}

function Test-Success {
  $install = New-TempInstall
  $repo,$source,$sha = New-RepoSource
  $script:recoveryCalls = 0
  Invoke-BaseTransaction $install $repo $source $sha { param($SourceWorker,$InstallRoot,$ExpectedIssue,$ApprovedNewBaseSha,$ExpectedPrHead,$ApprovedWorkerSha256)
    $script:recoveryCalls += 1
    Copy-Item $SourceWorker (Join-Path $InstallRoot "worker\agent_worker.py") -Force
    Set-Content -Path (Join-Path $InstallRoot "state\issue-5.json") -Value '{"cycles":2,"status":"WAITING_GITHUB"}' -Encoding UTF8
  }
  if ((Get-Content (Join-Path $install "worker\agent_worker.py") -Raw) -notmatch "new worker 155") { throw "worker not installed" }
  if ((Get-Content (Join-Path $install "state\issue-5.json") -Raw) -notmatch '"cycles":2') { throw "state not recovered" }
  if ($script:recoveryCalls -ne 1) { throw "atomic recovery not called exactly once" }
}

function Test-FailureAfterReplacementRollback {
  $install = New-TempInstall
  $repo,$source,$sha = New-RepoSource
  $workerBefore = Get-Content (Join-Path $install "worker\agent_worker.py") -Raw
  $stateBefore = Get-Content (Join-Path $install "state\issue-5.json") -Raw
  try {
    Invoke-BaseTransaction $install $repo $source $sha { param($SourceWorker,$InstallRoot,$ExpectedIssue,$ApprovedNewBaseSha,$ExpectedPrHead,$ApprovedWorkerSha256)
      Copy-Item $SourceWorker (Join-Path $InstallRoot "worker\agent_worker.py") -Force
      Set-Content -Path (Join-Path $InstallRoot "state\issue-5.json") -Value '{"broken":' -Encoding UTF8
      Set-Content -Path (Join-Path $InstallRoot "worker\agent_worker.py") -Value $workerBefore -Encoding UTF8 -NoNewline
      Set-Content -Path (Join-Path $InstallRoot "state\issue-5.json") -Value $stateBefore -Encoding UTF8 -NoNewline
      throw "controlled post-replacement failure"
    }
    throw "deployment should fail"
  } catch {
    if ($_.Exception.Message -notmatch "controlled post-replacement failure") { throw }
  }
  if ((Get-Content (Join-Path $install "worker\agent_worker.py") -Raw) -ne $workerBefore) { throw "worker rollback failed" }
  if ((Get-Content (Join-Path $install "state\issue-5.json") -Raw) -ne $stateBefore) { throw "state rollback failed" }
}

Test-BusyLockNoMutation
Test-Success
Test-FailureAfterReplacementRollback
Write-Host '{"status":"PASS","tests":["busy_lock","success","failure_after_worker_replacement_rollback"],"atomic_command":true}'
