param(
  [string]$Repo = "C:\AI_VAULT_AGENT_WORKER\control-plane-v153",
  [string]$InstallRoot = "C:\AI_VAULT_AGENT_WORKER",
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
Require-Administrator
if ((Resolve-Path $Repo).Path -like "C:\AI_VAULT_CANONICAL*") { Fail "Refusing canonical path" }
Import-Module (Join-Path $PSScriptRoot "Repair-AgentLoop-v1.5.4.Core.psm1") -Force
Invoke-AgentLoopV154DeploymentTransaction `
  -Repo $Repo `
  -InstallRoot $InstallRoot `
  -ApprovedNewBaseSha $ApprovedNewBaseSha `
  -ExpectedFront $ExpectedFront `
  -ExpectedIssue $ExpectedIssue `
  -ExpectedPr $ExpectedPr `
  -ExpectedWorkBranch $ExpectedWorkBranch `
  -ExpectedOldPrHead $ExpectedOldPrHead `
  -ApprovedControlPlaneCommit $ApprovedControlPlaneCommit `
  -ApprovedWorkerSha256 $ApprovedWorkerSha256
