$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Import-Module (Join-Path $Root "scripts\agent_loop\Repair-AgentLoop-v1.5.4.Core.psm1") -Force

function Assert-True($Condition, $Message) { if (-not $Condition) { throw $Message } }

function New-TestNativeScript($Dir, [int]$ExitCode, [string]$Text) {
  $path = Join-Path $Dir ("native-" + [guid]::NewGuid().ToString("N") + ".cmd")
  "@echo off`r`necho $Text`r`nexit /b $ExitCode`r`n" | Set-Content -Encoding ASCII $path
  return $path
}

function New-ScenarioRoot {
  $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("agent-loop-v154-ps-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force $tmp | Out-Null
  $repo = Join-Path $tmp "repo"
  $install = Join-Path $tmp "install"
  New-Item -ItemType Directory -Force (Join-Path $repo "scripts\agent_loop\local_worker") | Out-Null
  New-Item -ItemType Directory -Force (Join-Path $install "worker") | Out-Null
  New-Item -ItemType Directory -Force (Join-Path $install "state") | Out-Null
  $sourceWorker = Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py"
  $installedWorker = Join-Path $install "worker\agent_worker.py"
  $statePath = Join-Path $install "state\issue-5.json"
  [IO.File]::WriteAllBytes($sourceWorker, [Text.Encoding]::UTF8.GetBytes("replacement-v154-worker"))
  [IO.File]::WriteAllBytes($installedWorker, [Text.Encoding]::UTF8.GetBytes("original-worker-bytes"))
  [IO.File]::WriteAllBytes($statePath, [Text.Encoding]::UTF8.GetBytes('{"status":"original"}'))
  return [pscustomobject]@{ Root=$tmp; Repo=$repo; Install=$install; SourceWorker=$sourceWorker; InstalledWorker=$installedWorker; StatePath=$statePath; ApprovedSha=(Get-FileHash $sourceWorker -Algorithm SHA256).Hash }
}

function Invoke-TestTransaction($Scenario, [string]$Mode, [bool]$FailWorkerRestore=$false) {
  $global:v154_messages = New-Object System.Collections.Generic.List[string]
  $global:v154_commands = New-Object System.Collections.Generic.List[string]
  $global:v154_taskState = "Disabled"
  $global:v154_failWorkerRestore = $FailWorkerRestore
  $global:v154_mode = $Mode
  $global:v154_okNative = New-TestNativeScript $Scenario.Root 0 "native ok"
  $global:v154_badNative = New-TestNativeScript $Scenario.Root 1 "native failed intentionally"
  try {
    Invoke-AgentLoopV154DeploymentTransaction `
      -Repo $Scenario.Repo `
      -InstallRoot $Scenario.Install `
      -ApprovedNewBaseSha ("b" * 40) `
      -ExpectedFront "PILOT-KIMI-CODEX-20260716-091529" `
      -ExpectedIssue 5 `
      -ExpectedPr 6 `
      -ExpectedWorkBranch "agent/pilot-20260716-091529" `
      -ExpectedOldPrHead ("6" * 40) `
      -ApprovedControlPlaneCommit ("a" * 40) `
      -ApprovedWorkerSha256 $Scenario.ApprovedSha `
        -StopTask { param($TaskName) $global:v154_taskState = "Disabled" } `
        -DisableTask { param($TaskName) $global:v154_taskState = "Disabled" } `
        -GetTaskState { param($TaskName) $global:v154_taskState } `
      -GetRepoHead { param($RepoPath) "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" } `
      -RunRepoCommand {
        param($RepoPath, [string[]]$CommandArgs)
        $global:v154_commands.Add(($CommandArgs -join " "))
        if ($global:v154_mode -eq "compile_fail" -and ($CommandArgs -join " ") -match "py_compile") {
          Invoke-NativeChecked -Identity "fake py_compile" -FilePath $global:v154_badNative -ArgumentList @()
        } else {
          Invoke-NativeChecked -Identity "fake test" -FilePath $global:v154_okNative -ArgumentList @()
        }
      } `
      -GetHash { param($Path) (Get-FileHash $Path -Algorithm SHA256).Hash } `
      -CopyFile {
        param($Source, $Destination)
        if ($global:v154_failWorkerRestore -and ($Source -like "*.bak-v154-*") -and ($Destination -like "*worker*agent_worker.py")) { throw "forced worker restore failure" }
        Copy-Item $Source $Destination -Force
      } `
      -TrustedResume {
        param($WorkerPath, $InstallRoot, $ExpectedIssue, $ExpectedFront, $ApprovedNewBaseSha, $ExpectedPr, $ExpectedWorkBranch, $ExpectedOldPrHead)
        $global:v154_commands.Add("trusted-resume $WorkerPath")
        if ($global:v154_mode -eq "resume_fail") {
          Invoke-NativeChecked -Identity "python trusted-v154-resume" -FilePath $global:v154_badNative -ArgumentList @()
        } else {
          Invoke-NativeChecked -Identity "python trusted-v154-resume" -FilePath $global:v154_okNative -ArgumentList @()
        }
      } `
      -WriteLine { param($Message) $global:v154_messages.Add($Message) }
    return [pscustomobject]@{ ok=$true; error=""; messages=$global:v154_messages; commands=$global:v154_commands; task=$global:v154_taskState }
  } catch {
    return [pscustomobject]@{ ok=$false; error=$_.Exception.Message; messages=$global:v154_messages; commands=$global:v154_commands; task=$global:v154_taskState }
  }
}

$results = @()

# 1. Native exit 1 during py_compile: no install, no PASS.
$s = New-ScenarioRoot
try {
  $origWorker = [IO.File]::ReadAllBytes($s.InstalledWorker); $origState = [IO.File]::ReadAllBytes($s.StatePath)
  $r = @(Invoke-TestTransaction $s "compile_fail")[-1]
  Assert-True (-not $r.ok) "compile_fail unexpectedly succeeded"
  Assert-True ($r.error -match "native command failed: fake py_compile exit=1") "compile failure did not come from native helper: $($r.error)"
  Assert-True ([Convert]::ToBase64String([IO.File]::ReadAllBytes($s.InstalledWorker)) -eq [Convert]::ToBase64String($origWorker)) "compile_fail installed worker"
  Assert-True ([Convert]::ToBase64String([IO.File]::ReadAllBytes($s.StatePath)) -eq [Convert]::ToBase64String($origState)) "compile_fail changed state"
  Assert-True ($r.task -eq "Disabled") "compile_fail task not disabled"
  Assert-True (($r.messages -join "`n") -notmatch "PASS: installed worker") "compile_fail printed PASS"
  $results += [pscustomobject]@{ scenario="compile_native_exit_1"; status="PASS" }
} finally { Remove-Item -LiteralPath $s.Root -Recurse -Force -ErrorAction SilentlyContinue }

# 2. Resume native exit 1 after install: rollback PASS and primary native error preserved.
$s = New-ScenarioRoot
try {
  $origWorker = [IO.File]::ReadAllBytes($s.InstalledWorker); $origState = [IO.File]::ReadAllBytes($s.StatePath)
  $r = @(Invoke-TestTransaction $s "resume_fail")[-1]
  Assert-True (-not $r.ok) "resume_fail unexpectedly succeeded"
  Assert-True ($r.error -match "native command failed: python trusted-v154-resume exit=1") "resume native error not preserved: $($r.error)"
  Assert-True ([Convert]::ToBase64String([IO.File]::ReadAllBytes($s.InstalledWorker)) -eq [Convert]::ToBase64String($origWorker)) "resume_fail did not restore worker"
  Assert-True ([Convert]::ToBase64String([IO.File]::ReadAllBytes($s.StatePath)) -eq [Convert]::ToBase64String($origState)) "resume_fail did not restore state"
  Assert-True (($r.messages -join "`n") -match "ROLLBACK_STATUS=PASS") "resume_fail did not report rollback PASS"
  Assert-True (($r.messages -join "`n") -notmatch "PASS: installed worker") "resume_fail printed PASS"
  $results += [pscustomobject]@{ scenario="resume_native_exit_1_rollback_pass"; status="PASS" }
} finally { Remove-Item -LiteralPath $s.Root -Recurse -Force -ErrorAction SilentlyContinue }

# 3. Resume zero: transaction succeeds and PASS prints once.
$s = New-ScenarioRoot
try {
  $r = @(Invoke-TestTransaction $s "success")[-1]
  Assert-True ($r.ok) "success scenario failed: $($r.error)"
  Assert-True ($r.task -eq "Disabled") "success task not disabled"
  $passCount = @($r.messages | Where-Object { $_ -match "PASS: installed worker" }).Count
  Assert-True ($passCount -eq 1) "PASS count was $passCount"
  $results += [pscustomobject]@{ scenario="resume_native_exit_0_success"; status="PASS" }
} finally { Remove-Item -LiteralPath $s.Root -Recurse -Force -ErrorAction SilentlyContinue }

# Rollback failure remains covered.
$s = New-ScenarioRoot
try {
  $r = @(Invoke-TestTransaction $s "resume_fail" $true)[-1]
  Assert-True (-not $r.ok) "rollback_fail unexpectedly succeeded"
  Assert-True (($r.messages -join "`n") -match "ROLLBACK_STATUS=FAIL") "rollback_fail did not report FAIL"
  Assert-True ($r.task -eq "Disabled") "rollback_fail task not disabled"
  Assert-True (($r.commands -join "`n") -notmatch "--once") "rollback_fail ran worker once"
  $results += [pscustomobject]@{ scenario="resume_native_exit_1_rollback_fail"; status="PASS" }
} finally { Remove-Item -LiteralPath $s.Root -Recurse -Force -ErrorAction SilentlyContinue }

@{ status="PASS"; scenarios=$results } | ConvertTo-Json -Depth 6
