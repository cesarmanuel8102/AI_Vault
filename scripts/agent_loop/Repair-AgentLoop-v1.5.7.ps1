#requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][string]$Repo,
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [Parameter(Mandatory=$true)][string]$ApprovedControlPlaneCommit,
  [Parameter(Mandatory=$true)][string]$ApprovedWorkerSha256
)
$ErrorActionPreference = "Stop"
$resolvedRepo = (Resolve-Path -LiteralPath $Repo).Path
$canonicalRoot = Join-Path "C:\" ("AI_VAULT_" + "CANONICAL")
if ($resolvedRepo -like "$canonicalRoot*") { throw "Refusing canonical path" }
if ($InstallRoot -like "$canonicalRoot*") { throw "Refusing canonical install root" }
Import-Module (Join-Path $PSScriptRoot "Repair-AgentLoop-v1.5.7.Core.psm1") -Force
Invoke-AgentLoopV157InstallTransaction `
  -Repo $Repo `
  -InstallRoot $InstallRoot `
  -ApprovedControlPlaneCommit $ApprovedControlPlaneCommit `
  -ApprovedWorkerSha256 $ApprovedWorkerSha256
