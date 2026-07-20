$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path (Join-Path $PSScriptRoot "..") "..")

Import-Module (Join-Path $Root "scripts\agent_loop\Repair-AgentLoop-v1.5.7.Core.psm1") -Force

function New-TempInstall {
  $dir = Join-Path ([IO.Path]::GetTempPath()) ("v157-install-test-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "worker") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "config") | Out-Null
  New-Item -ItemType Directory -Force -Path (Join-Path $dir "state") | Out-Null
  Set-Content -LiteralPath (Join-Path $dir "worker\agent_worker.py") -Value "old-worker" -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $dir "config\worker.json") -Value '{}' -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $dir "config\worker_contract.json") -Value '{"old":true}' -Encoding UTF8
  return $dir
}

function Assert-InstallPreserved {
  param(
    [Parameter(Mandatory=$true)][string]$Install,
    [Parameter(Mandatory=$true)][string]$BeforeWorker,
    [Parameter(Mandatory=$true)][string]$BeforeConfig,
    [AllowNull()][string]$BeforeWorkerContract
  )
  if ((Get-Content -LiteralPath (Join-Path $Install "worker\agent_worker.py") -Raw) -ne $BeforeWorker) { throw "worker rollback mismatch" }
  if ((Get-Content -LiteralPath (Join-Path $Install "config\worker.json") -Raw) -ne $BeforeConfig) { throw "worker.json rollback mismatch" }
  $contractPath = Join-Path $Install "config\worker_contract.json"
  if ([string]::IsNullOrEmpty($BeforeWorkerContract)) {
    if (Test-Path -LiteralPath $contractPath) { throw "new worker_contract was not removed" }
  } else {
    if ((Get-Content -LiteralPath $contractPath -Raw) -ne $BeforeWorkerContract) { throw "worker_contract rollback mismatch" }
  }
  if (Test-Path -LiteralPath (Join-Path $Install "state\mutated.json")) { throw "state was modified" }
  if (Test-Path -LiteralPath (Join-Path $Install "reports\mutated.json")) { throw "reports were modified" }
}

function New-CleanRepo {
  $repo = Join-Path ([IO.Path]::GetTempPath()) ("v157-clean-repo-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $repo | Out-Null
  Invoke-NativeChecked -Identity "git init" -FilePath "git" -ArgumentList @("init") -WorkingDirectory $repo | Out-Null
  Invoke-NativeChecked -Identity "git config" -FilePath "git" -ArgumentList @("config", "user.email", "test@example.invalid") -WorkingDirectory $repo | Out-Null
  Invoke-NativeChecked -Identity "git config" -FilePath "git" -ArgumentList @("config", "user.name", "test") -WorkingDirectory $repo | Out-Null
  $sourceFiles = @(
    "scripts/agent_loop/local_worker/agent_worker.py",
    "scripts/agent_loop/local_worker/worker_contract.json",
    ".github/workflows/agent-loop-pilot.yml",
    ".github/codex/review-schema.json",
    ".github/codex/prompts/agent-loop-supervisor.md",
    "tests/contract/test_agent_loop_worker_v157_runtime_resolution.py",
    "tests/contract/test_agent_loop_worker_v157_real_cmd_quoting.py",
    "tests/contract/test_agent_loop_worker_v157_lossless_transport.py",
    "tests/contract/test_agent_loop_worker_v157_prompt_delivery.py",
    "tests/contract/test_agent_loop_worker_v157_state_event_contract.py",
    "tests/contract/test_agent_loop_worker_v157_codex_supervisor_contract.py",
    "scripts/agent_loop/Repair-AgentLoop-v1.5.7.Core.psm1",
    "tests/contract/test_agent_loop_worker_v157_deploy_recovery.ps1"
  )
  foreach ($rel in $sourceFiles) {
    $src = Join-Path $Root $rel
    $dst = Join-Path $repo $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
  }
  Invoke-NativeChecked -Identity "git add" -FilePath "git" -ArgumentList @("add", ".") -WorkingDirectory $repo | Out-Null
  Invoke-NativeChecked -Identity "git commit" -FilePath "git" -ArgumentList @("commit", "-m", "v157 clean deploy source") -WorkingDirectory $repo | Out-Null
  return $repo
}

function Test-InstallTransaction {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  $lines = New-Object System.Collections.Generic.List[string]
  $beforeConfig = Get-Sha256 (Join-Path $install "config\worker.json")

  $result = Invoke-AgentLoopV157InstallTransaction `
    -Repo $repo `
    -InstallRoot $install `
    -ApprovedControlPlaneCommit $control `
    -ApprovedWorkerSha256 $approved `
    -StopTask { param($Name) } `
    -DisableTask { param($Name) } `
    -GetTaskState { param($Name) "Disabled" } `
    -GetHash { param($Path) (Get-Sha256 $Path) } `
    -WriteLine { param($Message) $lines.Add([string]$Message) }

  $installedHash = Get-Sha256 (Join-Path $install "worker\agent_worker.py")
  if ($installedHash -ne $approved) { throw "installed worker SHA mismatch" }
  if (-not (Test-Path -LiteralPath (Join-Path $install "config\worker_contract.json") -PathType Leaf)) { throw "worker_contract.json not installed" }
  if ((Get-Sha256 (Join-Path $install "config\worker.json")) -ne $beforeConfig) { throw "worker.json was modified" }
  if ($result.status -ne "INSTALLED_V157") { throw "unexpected status $($result.status)" }
  $markerCount = @($lines | Where-Object { $_ -eq "V157_DEPLOY_RECOVERY_CONTRACT_PASS" }).Count
  if ($markerCount -ne 1) { throw "expected exactly one pass marker; got $markerCount" }
  $status = ((Invoke-NativeChecked -Identity "git status" -FilePath "git" -ArgumentList @("status", "--porcelain", "--untracked-files=all") -WorkingDirectory $repo) | Out-String).Trim()
  if ($status) { throw "successful transaction left checkout artifacts: $status" }
}

function Test-RollbackOnBadSha {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $badSha = "0" * 64
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  $before = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $badSha `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" }
    throw "expected SHA mismatch failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "Approved worker SHA mismatch") { throw }
  }
  if ((Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw) -ne $before) { throw "worker was mutated despite failed transaction" }
  if ((& { "Disabled" }) -ne "Disabled") { throw "task state changed" }
}

function Test-RollbackOnPostInstallFailure {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  $beforeWorker = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  $beforeConfig = Get-Content -LiteralPath (Join-Path $install "config\worker.json") -Raw
  $beforeContract = Get-Content -LiteralPath (Join-Path $install "config\worker_contract.json") -Raw
  $script:taskChecks = 0
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) $script:taskChecks += 1; if ($script:taskChecks -le 1) { "Disabled" } else { "Running" } } `
      -GetHash { param($Path) (Get-Sha256 $Path) } `
      -WriteLine { param($Message) } | Out-Null
    throw "expected post-install failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "Scheduled task changed state") { throw }
  }
  Assert-InstallPreserved -Install $install -BeforeWorker $beforeWorker -BeforeConfig $beforeConfig -BeforeWorkerContract $beforeContract
}

function Test-RollbackRemovesNewWorkerContract {
  $repo = New-CleanRepo
  $install = New-TempInstall
  Remove-Item -LiteralPath (Join-Path $install "config\worker_contract.json") -Force
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  $beforeWorker = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  $beforeConfig = Get-Content -LiteralPath (Join-Path $install "config\worker.json") -Raw
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" } `
      -AfterCopyHook { param($Root) throw "Injected post-copy failure" } `
      -WriteLine { param($Message) } | Out-Null
    throw "expected post-copy failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "Injected post-copy failure") { throw }
  }
  Assert-InstallPreserved -Install $install -BeforeWorker $beforeWorker -BeforeConfig $beforeConfig -BeforeWorkerContract $null
}

function Test-RollbackOnInstalledHashMismatch {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  $beforeWorker = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  $beforeConfig = Get-Content -LiteralPath (Join-Path $install "config\worker.json") -Raw
  $beforeContract = Get-Content -LiteralPath (Join-Path $install "config\worker_contract.json") -Raw
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" } `
      -GetHash { param($Path) if ($Path -like "*worker\agent_worker.py" -and $Path -like "$install*") { "bad" * 16 } else { Get-Sha256 $Path } } `
      -WriteLine { param($Message) } | Out-Null
    throw "expected installed worker hash mismatch"
  }
  catch {
    if ($_.Exception.Message -notmatch "Installed worker SHA mismatch") { throw }
  }
  Assert-InstallPreserved -Install $install -BeforeWorker $beforeWorker -BeforeConfig $beforeConfig -BeforeWorkerContract $beforeContract
}

function Test-RollbackOnInstalledSymbolFailure {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  $beforeWorker = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  $beforeConfig = Get-Content -LiteralPath (Join-Path $install "config\worker.json") -Raw
  $beforeContract = Get-Content -LiteralPath (Join-Path $install "config\worker_contract.json") -Raw
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" } `
      -GetHash { param($Path) if ($Path -like "$install*worker\agent_worker.py") { $approved } else { Get-Sha256 $Path } } `
      -AfterCopyHook { param($Root) (Get-Content -LiteralPath (Join-Path $Root "worker\agent_worker.py") -Raw).Replace("prompt_task_sentinel", "prompt_task_missing") | Set-Content -LiteralPath (Join-Path $Root "worker\agent_worker.py") -Encoding UTF8 } `
      -WriteLine { param($Message) } | Out-Null
    throw "expected installed worker symbol failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "v157 symbol missing") { throw }
  }
  Assert-InstallPreserved -Install $install -BeforeWorker $beforeWorker -BeforeConfig $beforeConfig -BeforeWorkerContract $beforeContract
}

function Test-RollbackOnSmokeFailure {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  $beforeWorker = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  $beforeConfig = Get-Content -LiteralPath (Join-Path $install "config\worker.json") -Raw
  $beforeContract = Get-Content -LiteralPath (Join-Path $install "config\worker_contract.json") -Raw
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" } `
      -BeforeSmokeHook { param($Root) (Get-Content -LiteralPath (Join-Path $Root "worker\agent_worker.py") -Raw).Replace('WORKER_VERSION = "1.5.7"', 'WORKER_VERSION = "0.0.0"') | Set-Content -LiteralPath (Join-Path $Root "worker\agent_worker.py") -Encoding UTF8 } `
      -WriteLine { param($Message) } | Out-Null
    throw "expected installed worker smoke failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "native command failed: worker version smoke") { throw }
  }
  Assert-InstallPreserved -Install $install -BeforeWorker $beforeWorker -BeforeConfig $beforeConfig -BeforeWorkerContract $beforeContract
}

function Test-InvalidConfigFailsClosed {
  $repo = New-CleanRepo
  $install = New-TempInstall
  Set-Content -LiteralPath (Join-Path $install "config\worker.json") -Value "{not-json" -Encoding UTF8
  $beforeWorker = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  $beforeConfig = Get-Content -LiteralPath (Join-Path $install "config\worker.json") -Raw
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" } | Out-Null
    throw "expected invalid config failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "Invalid existing worker config") { throw }
  }
  if ((Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw) -ne $beforeWorker) { throw "worker changed after invalid config" }
  if ((Get-Content -LiteralPath (Join-Path $install "config\worker.json") -Raw) -ne $beforeConfig) { throw "config changed after invalid config" }
}

function Test-BadControlPlaneCommitFailsClosed {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $beforeWorker = Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit ("1" * 40) `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" } | Out-Null
    throw "expected control-plane commit failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "Unexpected control-plane HEAD") { throw }
  }
  if ((Get-Content -LiteralPath (Join-Path $install "worker\agent_worker.py") -Raw) -ne $beforeWorker) { throw "worker changed after bad control-plane commit" }
}

function Test-UntrackedUnexpectedBlocked {
  param([Parameter(Mandatory=$true)][string]$RelativePath)
  $repo = New-CleanRepo
  $install = New-TempInstall
  $path = Join-Path $repo $RelativePath
  New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
  Set-Content -LiteralPath $path -Value "unexpected" -Encoding UTF8
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  try {
    Invoke-AgentLoopV157InstallTransaction `
      -Repo $repo `
      -InstallRoot $install `
      -ApprovedControlPlaneCommit $control `
      -ApprovedWorkerSha256 $approved `
      -StopTask { param($Name) } `
      -DisableTask { param($Name) } `
      -GetTaskState { param($Name) "Disabled" } | Out-Null
    throw "expected unexpected untracked failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "Unexpected untracked") { throw }
  }
}

function Test-BytecodeGeneratedAllowedAndCleaned {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  Invoke-AgentLoopV157InstallTransaction `
    -Repo $repo `
    -InstallRoot $install `
    -ApprovedControlPlaneCommit $control `
    -ApprovedWorkerSha256 $approved `
    -StopTask { param($Name) } `
    -DisableTask { param($Name) } `
    -GetTaskState { param($Name) "Disabled" } `
    -WriteLine { param($Message) } | Out-Null
  $status = ((Invoke-NativeChecked -Identity "git status" -FilePath "git" -ArgumentList @("status", "--porcelain", "--untracked-files=all") -WorkingDirectory $repo) | Out-String).Trim()
  if ($status) { throw "bytecode was not cleaned: $status" }
}

function Test-PreexistingBytecodePreserved {
  $repo = New-CleanRepo
  $install = New-TempInstall
  $cacheDir = Join-Path $repo "tests\contract\__pycache__"
  New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
  $preexisting = Join-Path $cacheDir "preexisting.pyc"
  Set-Content -LiteralPath $preexisting -Value "keep-me" -Encoding UTF8
  $approved = Get-Sha256 (Join-Path $repo "scripts\agent_loop\local_worker\agent_worker.py")
  $control = ((Invoke-NativeChecked -Identity "git rev-parse" -FilePath "git" -ArgumentList @("rev-parse", "HEAD") -WorkingDirectory $repo) | Out-String).Trim()
  Invoke-AgentLoopV157InstallTransaction `
    -Repo $repo `
    -InstallRoot $install `
    -ApprovedControlPlaneCommit $control `
    -ApprovedWorkerSha256 $approved `
    -StopTask { param($Name) } `
    -DisableTask { param($Name) } `
    -GetTaskState { param($Name) "Disabled" } `
    -WriteLine { param($Message) } | Out-Null
  if (-not (Test-Path -LiteralPath $preexisting -PathType Leaf)) { throw "preexisting bytecode was removed" }
  if ((Get-Content -LiteralPath $preexisting -Raw) -notmatch "keep-me") { throw "preexisting bytecode was altered" }
}

function Test-NativeArgumentHandling {
  $tmp = Join-Path ([IO.Path]::GetTempPath()) ("v157-native-args-" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $tmp | Out-Null
  $echo = Join-Path $tmp "echo_args.py"
  Set-Content -LiteralPath $echo -Encoding UTF8 -Value @'
import json, sys
print(json.dumps(sys.argv[1:]))
'@
  $result = Invoke-NativeChecked -Identity "arg echo" -FilePath "python" -ArgumentList @($echo, "path with spaces", 'quote "inside"', "") -WorkingDirectory $tmp
  $args = $result | ConvertFrom-Json
  if ($args[0] -ne "path with spaces") { throw "space arg mismatch" }
  if ($args[1] -ne 'quote "inside"') { throw "quote arg mismatch" }
  if ($args[2] -ne "") { throw "empty arg mismatch" }

  $warn = Join-Path $tmp "stderr_zero.py"
  Set-Content -LiteralPath $warn -Encoding UTF8 -Value "import sys; sys.stderr.write('warning-line'); print('ok')"
  $warnOut = Invoke-NativeChecked -Identity "stderr zero" -FilePath "python" -ArgumentList @($warn) -WorkingDirectory $tmp 3>&1
  if (($warnOut | Out-String) -notmatch "ok") { throw "stderr zero stdout missing" }

  $err = Join-Path $tmp "stderr_fail.py"
  Set-Content -LiteralPath $err -Encoding UTF8 -Value "import sys; sys.stderr.write('error-line'); sys.exit(7)"
  try {
    Invoke-NativeChecked -Identity "stderr fail" -FilePath "python" -ArgumentList @($err) -WorkingDirectory $tmp | Out-Null
    throw "expected native failure"
  }
  catch {
    if ($_.Exception.Message -notmatch "exit=7" -or $_.Exception.Message -notmatch "error-line") { throw }
  }
}

function Test-RefuseCanonicalPath {
  try {
    Invoke-AgentLoopV157InstallTransaction -Repo $Root -InstallRoot "C:\AI_VAULT_CANONICAL" -ApprovedControlPlaneCommit "x" -ApprovedWorkerSha256 "y"
    throw "expected canonical path refusal"
  }
  catch {
    if ($_.Exception.Message -notmatch "Refusing canonical") { throw }
  }
}

Test-InstallTransaction
Test-RollbackOnBadSha
Test-RollbackOnPostInstallFailure
Test-RollbackRemovesNewWorkerContract
Test-RollbackOnInstalledHashMismatch
Test-RollbackOnInstalledSymbolFailure
Test-RollbackOnSmokeFailure
Test-InvalidConfigFailsClosed
Test-BadControlPlaneCommitFailsClosed
Test-UntrackedUnexpectedBlocked -RelativePath "unexpected.txt"
Test-UntrackedUnexpectedBlocked -RelativePath "script.ps1"
Test-UntrackedUnexpectedBlocked -RelativePath "scripts\agent_loop\unexpected.ps1"
Test-BytecodeGeneratedAllowedAndCleaned
Test-PreexistingBytecodePreserved
Test-NativeArgumentHandling
Test-RefuseCanonicalPath
Write-Host 'V157_DEPLOY_RECOVERY_CONTRACT_PASS'
Write-Host '{"status":"PASS","tests":["install_transaction","rollback_on_bad_sha","rollback_on_post_install_failure","rollback_removes_new_worker_contract","rollback_on_installed_hash_mismatch","rollback_on_installed_symbol_failure","rollback_on_smoke_failure","invalid_config","bad_control_plane_commit","untracked_unexpected","bytecode_cleaned","preexisting_bytecode_preserved","native_arguments","refuse_canonical_path"],"atomic_command":true}'
