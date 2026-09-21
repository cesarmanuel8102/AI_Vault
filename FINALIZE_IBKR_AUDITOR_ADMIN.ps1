#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT",
    [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Canonical = Join-Path $RepoRoot "FINALIZE_IBKR_PREREQUISITES.ps1"
if (-not (Test-Path -LiteralPath $Canonical -PathType Leaf)) {
    throw "CANONICAL_PREREQUISITE_FINALIZER_MISSING"
}
Write-Warning "FINALIZE_IBKR_AUDITOR_ADMIN.ps1 is deprecated. Delegating to the canonical prerequisite finalizer."
& PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File $Canonical -RepoRoot $RepoRoot -PythonExe $PythonExe -SkipTaskRegistration
exit $LASTEXITCODE
