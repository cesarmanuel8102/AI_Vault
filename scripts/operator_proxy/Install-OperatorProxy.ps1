#requires -RunAsAdministrator
param([Parameter(Mandatory=$true)][string]$Repo,[string]$InstallRoot='C:\AI_VAULT_CODEX_BRIDGE',[Parameter(Mandatory=$true)][string]$ApprovedCommit)
$ErrorActionPreference='Stop'; Import-Module (Join-Path $PSScriptRoot 'Repair-OperatorProxy.psm1') -Force; Invoke-OperatorProxyInstall -Repo $Repo -InstallRoot $InstallRoot -ApprovedCommit $ApprovedCommit
