#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT",
    [string]$PythonExe = "python",
    [switch]$Scheduled
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Canonical = Join-Path $RepoRoot "RUN_IBKR_MARKET_DATA_GATE.ps1"
if (-not (Test-Path -LiteralPath $Canonical -PathType Leaf)) {
    throw "CANONICAL_MARKET_DATA_GATE_RUNNER_MISSING"
}
Write-Warning "FINALIZE_IBKR_MARKET_DATA.ps1 is deprecated. Delegating to RUN_IBKR_MARKET_DATA_GATE.ps1."
$Arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Canonical, "-RepoRoot", $RepoRoot, "-PythonExe", $PythonExe)
if ($Scheduled) { $Arguments += "-Scheduled" }
& PowerShell.exe @Arguments
exit $LASTEXITCODE
