param(
  [string]$Repo = "C:\AI_VAULT_AGENT_WORKER\control-plane-v153",
  [string]$InstallRoot = "C:\AI_VAULT_AGENT_WORKER",
  [Parameter(Mandatory=$true)][string]$ExpectedOldBaseSha,
  [Parameter(Mandatory=$true)][string]$ApprovedNewBaseSha,
  [string]$ExpectedFront = "PILOT-KIMI-CODEX-20260716-091529",
  [int]$ExpectedIssue = 5,
  [int]$ExpectedPr = 6,
  [string]$ExpectedWorkBranch = "agent/pilot-20260716-091529",
  [Parameter(Mandatory=$true)][string]$ExpectedOldPrHead,
  [Parameter(Mandatory=$true)][string]$ApprovedControlPlaneCommit,
  [Parameter(Mandatory=$true)][string]$ApprovedWorkerSha256
)
$ErrorActionPreference = "Stop"
function Fail($m){ Write-Host "FAIL: $m"; exit 1 }
function Require-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "Run this script from an elevated Administrator PowerShell"
  }
}
function Test-PilotVerifyLocal($Repo, $InstallRoot, $ExpectedFront) {
  $stamp = Get-Date -Format "yyyyMMddTHHmmssZ"
  $verifyRepo = Join-Path $InstallRoot "reports\pilot-verify-v153-$stamp\repo"
  New-Item -ItemType Directory -Force (Join-Path $verifyRepo "scripts\agent_loop") | Out-Null
  New-Item -ItemType Directory -Force (Join-Path $verifyRepo "docs\agent_loop\pilot") | Out-Null
  Copy-Item (Join-Path $Repo "scripts\agent_loop\pilot_verify.py") (Join-Path $verifyRepo "scripts\agent_loop\pilot_verify.py") -Force
  Push-Location $verifyRepo
  try {
    git init | Out-Null
    git config user.name "agent-loop-v153-test"
    git config user.email "agent-loop-v153-test@example.invalid"
    @"
# Agent Loop Pilot
WORKER_VERSION=1.5.2
FRONT_ID=$ExpectedFront
STATUS=PASS
EXECUTOR=KIMI_OPENCODE_OLLAMA
SUPERVISOR=CODEX_GITHUB_ACTION
"@ | Set-Content -Encoding UTF8 docs\agent_loop\pilot\PILOT_MARKER.md
    @"
{"schema_version":1,"worker_version":"1.5.2","status":"PASS"}
"@ | Set-Content -Encoding UTF8 docs\agent_loop\pilot\EXECUTOR_REPORT.json
    git add docs\agent_loop\pilot\PILOT_MARKER.md docs\agent_loop\pilot\EXECUTOR_REPORT.json scripts\agent_loop\pilot_verify.py
    git commit -m "seed old pilot state" | Out-Null
    @"
# Agent Loop Pilot
WORKER_VERSION=1.5.3
FRONT_ID=$ExpectedFront
STATUS=PASS
EXECUTOR=KIMI_OPENCODE_OLLAMA
SUPERVISOR=CODEX_GITHUB_ACTION
"@ | Set-Content -Encoding UTF8 docs\agent_loop\pilot\PILOT_MARKER.md
    python scripts/agent_loop/pilot_verify.py --local
  } finally {
    Pop-Location
  }
}
Require-Administrator
if ((Resolve-Path $Repo).Path -like "C:\AI_VAULT_CANONICAL*") { Fail "Refusing canonical path" }
try { Stop-ScheduledTask -TaskName AI_Vault_Kimi_GitHub_Worker -ErrorAction SilentlyContinue } catch {}
try { Disable-ScheduledTask -TaskName AI_Vault_Kimi_GitHub_Worker -ErrorAction Stop | Out-Null } catch { Fail "Could not disable scheduled task: $($_.Exception.Message)" }
$task = Get-ScheduledTask -TaskName AI_Vault_Kimi_GitHub_Worker
if ($task.State -ne "Disabled") { Fail "Scheduled task is not disabled; refusing install" }
Push-Location $Repo
try {
  $head = (git rev-parse HEAD).Trim()
  if (-not $head) { Fail "Not a git repo" }
  if ($head -ne $ApprovedControlPlaneCommit) { Fail "Unexpected control-plane commit: $head" }
  python -m py_compile scripts/agent_loop/local_worker/agent_worker.py
  python -m py_compile scripts/agent_loop/pilot_verify.py
  python tests/contract/test_agent_loop_worker_hardening_02.py
  python tests/contract/test_agent_loop_worker_v153_regression.py
  Test-PilotVerifyLocal $Repo $InstallRoot $ExpectedFront
  $sourceSha = (Get-FileHash scripts\agent_loop\local_worker\agent_worker.py -Algorithm SHA256).Hash
  if ($sourceSha -ne $ApprovedWorkerSha256) { Fail "Unexpected worker source SHA-256: $sourceSha" }
  $stamp = Get-Date -Format "yyyyMMddTHHmmssZ"
  $workerBackup = "$InstallRoot\worker\agent_worker.py.bak-v153-$stamp"
  $stateBackup = "$InstallRoot\state\issue-5.json.bak-v153-$stamp"
  Copy-Item "$InstallRoot\worker\agent_worker.py" $workerBackup -Force
  Copy-Item scripts/agent_loop/local_worker/agent_worker.py "$InstallRoot\worker\agent_worker.py" -Force
  $sha = (Get-FileHash "$InstallRoot\worker\agent_worker.py" -Algorithm SHA256).Hash
  if ($sha -ne $ApprovedWorkerSha256) { Fail "Installed worker SHA-256 mismatch: $sha" }
  Copy-Item "$InstallRoot\state\issue-5.json" $stateBackup -Force
  python "$InstallRoot\worker\agent_worker.py" --config "$InstallRoot\config\worker.json" --trusted-base-advance-existing-pr $ExpectedIssue --expected-front $ExpectedFront --expected-old-base-sha $ExpectedOldBaseSha --approved-new-base-sha $ApprovedNewBaseSha --approved-control-plane-commit $ApprovedControlPlaneCommit --expected-pr-number $ExpectedPr --expected-work-branch $ExpectedWorkBranch --expected-old-pr-head $ExpectedOldPrHead
  Enable-ScheduledTask -TaskName AI_Vault_Kimi_GitHub_Worker | Out-Null
  Write-Host "PASS: installed worker v1.5.3"
  Write-Host "installed_sha256=$sha"
  Write-Host "events_path=$InstallRoot\reports\worker-events.jsonl"
  Write-Host "rollback_worker=Copy-Item '$workerBackup' '$InstallRoot\worker\agent_worker.py' -Force"
  Write-Host "rollback_state=Copy-Item '$stateBackup' '$InstallRoot\state\issue-5.json' -Force"
} finally { Pop-Location }
