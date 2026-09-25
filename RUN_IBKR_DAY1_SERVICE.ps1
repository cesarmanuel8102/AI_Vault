#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [string]$PythonExe = "python",
    [string]$PowerShellExe = "powershell.exe",
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ResolvedRepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
$ApprovedRepoRoot = [IO.Path]::GetFullPath("C:\AI_VAULT_IBKR").TrimEnd('\')
if ($ResolvedRepoRoot -ine $ApprovedRepoRoot) {
    throw "REPO_ROOT_NOT_APPROVED:$ResolvedRepoRoot"
}
Set-Location -LiteralPath $ResolvedRepoRoot
$Finalizer = Join-Path $ResolvedRepoRoot "FINALIZE_IBKR_PREREQUISITES.ps1"
$LaunchAttemptId = [guid]::NewGuid().ToString("D")
$FinalizerArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Finalizer,
    "-RepoRoot", $ResolvedRepoRoot,
    "-PythonExe", $PythonExe,
    "-SkipTaskRegistration",
    "-LaunchAttemptId", $LaunchAttemptId
)
$PythonArguments = @(
    "-m", "ibkr_paper_30d.day1_launch",
    "--repo-root", $ResolvedRepoRoot,
    "--launch-attempt-id", $LaunchAttemptId
)

if ($ValidateOnly) {
    [ordered]@{
        launch_attempt_id = $LaunchAttemptId
        finalizer_arguments = $FinalizerArguments
        python_arguments = $PythonArguments
        foreground = $true
        broker_write_calls = 0
    } | ConvertTo-Json -Compress
    exit 0
}

$LaunchRoot = Join-Path $ResolvedRepoRoot "state\ibkr_paper_30d\launch"
[void](New-Item -ItemType Directory -Path $LaunchRoot -Force)
$Stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$TranscriptPath = Join-Path $LaunchRoot ("day1-" + $Stamp + "-pid" + $PID + ".log")
$TranscriptStarted = $false
try {
    Start-Transcript -LiteralPath $TranscriptPath -Append | Out-Null
    $TranscriptStarted = $true
    & $PowerShellExe @FinalizerArguments
    $FinalizerExitCode = $LASTEXITCODE
    if ($FinalizerExitCode -ne 0) {
        throw "DAY1_FINALIZER_FAILED:$FinalizerExitCode"
    }
    & $PythonExe @PythonArguments
    $LaunchExitCode = $LASTEXITCODE
    exit $LaunchExitCode
}
finally {
    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
    }
}
