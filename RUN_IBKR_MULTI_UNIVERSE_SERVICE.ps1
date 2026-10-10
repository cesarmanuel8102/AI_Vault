#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$ApprovedHead,
    [Parameter(Mandatory = $true)][string]$TransitionAuthorityPath,
    [string]$PythonExe = "python",
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ResolvedRepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
$ResolvedAuthorityPath = [IO.Path]::GetFullPath($TransitionAuthorityPath)
if ($ApprovedHead -notmatch '^[0-9a-fA-F]{40}$') {
    throw "APPROVED_HEAD_INVALID"
}
if (-not (Test-Path -LiteralPath $ResolvedAuthorityPath -PathType Leaf)) {
    throw "TRANSITION_AUTHORITY_MISSING"
}
$Authority = Get-Content -LiteralPath $ResolvedAuthorityPath -Raw | ConvertFrom-Json
if ([string]$Authority.schema -ne "MULTI_UNIVERSE_LAUNCH_AUTHORITY_V1") {
    throw "TRANSITION_AUTHORITY_INVALID"
}
$SuccessorEpochId = [string]$Authority.successor_epoch_id
$SuccessorDefinitionSha256 = [string]$Authority.successor_definition_sha256
if ([string]::IsNullOrWhiteSpace($SuccessorEpochId)) {
    throw "SUCCESSOR_EPOCH_ID_MISSING"
}
if ($SuccessorDefinitionSha256 -notmatch '^[0-9a-fA-F]{64}$') {
    throw "SUCCESSOR_DEFINITION_SHA256_INVALID"
}

$CurrentHead = ([string]((& git -C $ResolvedRepoRoot rev-parse HEAD 2>$null) | Select-Object -First 1)).Trim().ToLowerInvariant()
if ($CurrentHead -ne $ApprovedHead.ToLowerInvariant()) {
    throw "APPROVED_HEAD_MISMATCH"
}
$LaunchAttemptId = [guid]::NewGuid().ToString("D")
$Arguments = @(
    "-B", "-m", "ibkr_paper_30d.day1_launch",
    "--repo-root", $ResolvedRepoRoot,
    "--launch-attempt-id", $LaunchAttemptId,
    "--approved-head", $ApprovedHead.ToLowerInvariant(),
    "--target-successor-epoch-id", $SuccessorEpochId,
    "--target-successor-definition-sha256", $SuccessorDefinitionSha256.ToLowerInvariant(),
    "--multi-universe-authority-path", $ResolvedAuthorityPath
)

if ($ValidateOnly) {
    [ordered]@{
        status = "VALIDATED_ONLY"
        launch_attempt_id = $LaunchAttemptId
        python_arguments = $Arguments
        legacy_market_gate_invoked = $false
        broker_write_calls = 0
        mutations_performed = 0
    } | ConvertTo-Json -Compress
    exit 0
}

Set-Location -LiteralPath $ResolvedRepoRoot
& $PythonExe @Arguments
exit $LASTEXITCODE
