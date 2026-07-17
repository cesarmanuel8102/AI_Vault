#requires -RunAsAdministrator
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
  [Parameter(Mandatory=$true)][string]$ApprovedWorkerSha256
)
$ErrorActionPreference = "Stop"
$resolvedRepo = (Resolve-Path -LiteralPath $Repo).Path
if ($resolvedRepo -like "C:\AI_VAULT_CANONICAL*") { throw "Refusing canonical path" }
Import-Module (Join-Path $PSScriptRoot "Repair-AgentLoop-v1.5.6.Core.psm1") -Force
Invoke-AgentLoopV156DeploymentTransaction `
  -Repo $Repo `
  -InstallRoot $InstallRoot `
  -HistoricalBaseSha $HistoricalBaseSha `
  -PrePr10BaseSha $PrePr10BaseSha `
  -ApprovedFeatureHead $ApprovedFeatureHead `
  -ApprovedMergedBaseSha $ApprovedMergedBaseSha `
  -ExpectedFront $ExpectedFront `
  -ExpectedIssue $ExpectedIssue `
  -ExpectedPr $ExpectedPr `
  -ExpectedWorkBranch $ExpectedWorkBranch `
  -ExpectedOldPrHead $ExpectedOldPrHead `
  -ApprovedControlPlaneCommit $ApprovedControlPlaneCommit `
  -ApprovedWorkerSha256 $ApprovedWorkerSha256
