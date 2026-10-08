#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT_IBKR",
    [string]$PythonExe = "python",
    [Parameter(Mandatory = $true)][string]$ApprovedHead,
    [switch]$Scheduled,
    [switch]$InspectStatus,
    [switch]$ForceFresh
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "CodexIBKRMarketDataGate"
$ReportRoot = Join-Path $RepoRoot "state\ibkr_paper_30d\reports"
$LedgerPath = Join-Path $ReportRoot "market_observations.jsonl"
$PolicyPath = Join-Path $ReportRoot "market_data_policy_v1.json"
$ValidationPath = Join-Path $ReportRoot "market_data_validation.json"
$StatePath = Join-Path $ReportRoot "market_gate_collection_state.json"

function Invoke-PythonJson {
    param([string[]]$Arguments)
    $PriorErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $Output = @(& $PythonExe @Arguments 2>&1)
        $PythonExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PriorErrorActionPreference
    }
    if ($PythonExitCode -ne 0) {
        throw "PYTHON_COMMAND_FAILED:$($Arguments -join ' '):$($Output -join ' | ')"
    }
    $Candidates = @($Output | Where-Object { ([string]$_).TrimStart().StartsWith("{") })
    if ($Candidates.Count -eq 0) {
        throw "PYTHON_JSON_OUTPUT_MISSING:$($Output -join ' | ')"
    }
    return ([string]$Candidates[-1] | ConvertFrom-Json)
}

function Invoke-Day1ForegroundService {
    $Day1Script = Join-Path $ResolvedRepoRoot "RUN_IBKR_DAY1_SERVICE.ps1"
    if (-not (Test-Path -LiteralPath $Day1Script -PathType Leaf)) {
        throw "DAY1_SERVICE_SCRIPT_MISSING"
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Day1Script `
        -RepoRoot $ResolvedRepoRoot -PythonExe $PythonExe -ApprovedHead $ApprovedHead
    $Day1ExitCode = $LASTEXITCODE
    if ($Day1ExitCode -ne 0) {
        throw "DAY1_FOREGROUND_SERVICE_FAILED:$Day1ExitCode"
    }
}

function Resolve-MarketGateMode {
    param([bool]$IsScheduled, [bool]$IsInspectStatus, [bool]$IsForceFresh)
    if ($IsScheduled -eq $IsInspectStatus) {
        throw "EXACTLY_ONE_MARKET_GATE_MODE_REQUIRED"
    }
    if ($IsForceFresh -and -not $IsScheduled) {
        throw "FORCE_FRESH_REQUIRES_SCHEDULED_MODE"
    }
    if ($IsScheduled -and $IsForceFresh) { return "COLLECT_FRESH" }
    if ($IsScheduled) { return "REUSE_EXISTING" }
    return "INSPECT_EXISTING"
}

function Get-ExistingMarketGateStatus {
    if (-not (Test-Path -LiteralPath $ValidationPath -PathType Leaf)) {
        return [ordered]@{
            status = "MISSING"
            market_data_gate = "BLOCK"
            reusable_for_scheduled_launch = $false
        }
    }
    if (-not (Test-Path -LiteralPath $PolicyPath -PathType Leaf)) {
        return [ordered]@{
            status = "MISSING_POLICY"
            market_data_gate = "BLOCK"
            reusable_for_scheduled_launch = $false
        }
    }
    try {
        $Existing = Get-Content -LiteralPath $ValidationPath -Raw | ConvertFrom-Json
    }
    catch {
        return [ordered]@{
            status = "INVALID"
            market_data_gate = "BLOCK"
            reusable_for_scheduled_launch = $false
        }
    }
    $HasGate = $null -ne $Existing.PSObject.Properties["market_data_gate"]
    $HasStatus = $null -ne $Existing.PSObject.Properties["status"]
    $HasFrozen = $null -ne $Existing.PSObject.Properties["market_data_policy_frozen"]
    $Reusable = (
        $HasGate -and $Existing.market_data_gate -eq "PASS" -and
        $HasStatus -and $Existing.status -eq "PASS" -and
        $HasFrozen -and $Existing.market_data_policy_frozen -eq $true
    )
    return [ordered]@{
        status = "INSPECTED"
        market_data_gate = $(if ($Reusable) { "PASS" } else { "BLOCK" })
        reusable_for_scheduled_launch = $Reusable
    }
}

function Test-ReadOnlyReconciliation {
    param([object]$ReadOnly)

    $RequiredFields = @(
        "status",
        "reason_codes",
        "real_ibkr_read_only_identity_gate",
        "paper_account_identity_gate",
        "expected_account_identity_bound",
        "paper_account_namespace_ok",
        "managed_account_count",
        "heartbeat_ok",
        "gateway_mode",
        "outbound_allowlist_only",
        "real_order_writes_attempted",
        "account_summary_consistent",
        "query_completeness"
    )
    foreach ($Name in $RequiredFields) {
        if ($null -eq $ReadOnly.PSObject.Properties[$Name]) { return $false }
    }
    $RequiredQueries = @(
        "managed_accounts",
        "positions",
        "open_orders",
        "executions",
        "current_time"
    )
    foreach ($Name in $RequiredQueries) {
        if (
            $null -eq $ReadOnly.query_completeness.PSObject.Properties[$Name] -or
            $ReadOnly.query_completeness.$Name -ne $true
        ) { return $false }
    }
    $Reasons = @($ReadOnly.reason_codes)
    $StatusAccepted = (
        [string]$ReadOnly.status -eq "PASS" -or
        (
            [string]$ReadOnly.status -eq "PARTIAL" -and
            $Reasons.Count -eq 1 -and
            [string]$Reasons[0] -eq "ACCOUNT_SUMMARY_FIELDS_INCOMPLETE"
        )
    )
    return (
        $StatusAccepted -and
        [string]$ReadOnly.real_ibkr_read_only_identity_gate -eq "PASS" -and
        [string]$ReadOnly.paper_account_identity_gate -eq "PASS" -and
        $ReadOnly.expected_account_identity_bound -eq $true -and
        $ReadOnly.paper_account_namespace_ok -eq $true -and
        [int]$ReadOnly.managed_account_count -eq 1 -and
        $ReadOnly.heartbeat_ok -eq $true -and
        [string]$ReadOnly.gateway_mode -eq "PAPER" -and
        $ReadOnly.outbound_allowlist_only -eq $true -and
        [int]$ReadOnly.real_order_writes_attempted -eq 0 -and
        $ReadOnly.account_summary_consistent -eq $true
    )
}

function Get-EasternNow {
    $Zone = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    return [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $Zone)
}

function Assert-RegularCollectionStart {
    $Now = Get-EasternNow
    if ($Now.DayOfWeek -in @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)) {
        throw "MARKET_DATA_COLLECTION_REQUIRES_WEEKDAY"
    }
    $Minutes = $Now.Hour * 60 + $Now.Minute
    if ($Minutes -lt (9 * 60 + 35) -or $Minutes -gt (14 * 60 + 45)) {
        throw "START_BETWEEN_09_35_AND_14_45_ET"
    }
}

function Archive-CollectionEvidence {
    param([string]$Reason)
    $CandidatePaths = @(
        $LedgerPath,
        $PolicyPath,
        (Join-Path $ReportRoot "market_observation.json"),
        (Join-Path $ReportRoot "market_policy_freeze.json"),
        $ValidationPath,
        $StatePath
    )
    $Existing = @($CandidatePaths | Where-Object { Test-Path -LiteralPath $_ })
    if ($Existing.Count -eq 0) { return }
    $Stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $Archive = Join-Path $ReportRoot ("archive\market-gate-" + $Stamp + "-" + $Reason)
    [void](New-Item -ItemType Directory -Path $Archive -Force)
    foreach ($Path in $Existing) {
        Move-Item -LiteralPath $Path -Destination (Join-Path $Archive ([IO.Path]::GetFileName($Path))) -Force
    }
}

function Initialize-CleanEvidence {
    if (Test-Path -LiteralPath $StatePath) { return }
    [void](New-Item -ItemType Directory -Path $ReportRoot -Force)
    $CandidatePaths = @(
        $LedgerPath,
        $PolicyPath,
        (Join-Path $ReportRoot "market_observation.json"),
        (Join-Path $ReportRoot "market_policy_freeze.json"),
        $ValidationPath
    )
    $Existing = @($CandidatePaths | Where-Object { Test-Path -LiteralPath $_ })
    if ($Existing.Count -gt 0) {
        $Stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
        $Archive = Join-Path $ReportRoot ("archive\market-gate-" + $Stamp)
        [void](New-Item -ItemType Directory -Path $Archive -Force)
        foreach ($Path in $Existing) {
            Move-Item -LiteralPath $Path -Destination (Join-Path $Archive ([IO.Path]::GetFileName($Path))) -Force
        }
    }
    [ordered]@{
        schema = "MARKET_DATA_GATE_COLLECTION_STATE_V1"
        started_at_utc = [DateTime]::UtcNow.ToString("o").Replace("+00:00", "Z")
        protocol = "3x5min_windows_31min_start_separation"
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding UTF8
}

function Wait-UntilUtc {
    param([DateTime]$Target)
    while ([DateTime]::UtcNow -lt $Target) {
        $Remaining = ($Target - [DateTime]::UtcNow).TotalSeconds
        $Slice = [Math]::Min([Math]::Max($Remaining, 1), 60)
        Start-Sleep -Seconds ([int][Math]::Ceiling($Slice))
    }
}

function Resolve-ApprovedRepoRoot {
    param([string]$RepoRoot)
    $Resolved = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
    $Approved = [IO.Path]::GetFullPath("C:\AI_VAULT_IBKR").TrimEnd('\')
    if ($Resolved -ine $Approved) {
        throw "REPO_ROOT_NOT_APPROVED:$Resolved"
    }
    return $Resolved
}

$ResolvedRepoRoot = Resolve-ApprovedRepoRoot -RepoRoot $RepoRoot
if (-not (Test-Path -LiteralPath $ResolvedRepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$ResolvedRepoRoot"
}
$GateMode = Resolve-MarketGateMode `
    -IsScheduled $Scheduled.IsPresent `
    -IsInspectStatus $InspectStatus.IsPresent `
    -IsForceFresh $ForceFresh.IsPresent
if ($GateMode -eq "INSPECT_EXISTING") {
    Get-ExistingMarketGateStatus | ConvertTo-Json -Depth 4
    exit 0
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf) -and $null -eq (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    throw "PYTHON_EXECUTABLE_NOT_FOUND:$PythonExe"
}
Set-Location -LiteralPath $ResolvedRepoRoot

if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 4002 -InformationLevel Quiet)) {
    throw "IBKR_PAPER_GATEWAY_4002_NOT_LISTENING"
}

if ($GateMode -eq "REUSE_EXISTING") {
    $ExistingStatus = Get-ExistingMarketGateStatus
    if ($ExistingStatus.reusable_for_scheduled_launch -ne $true) {
        throw "MARKET_DATA_BASELINE_NOT_REUSABLE_USE_FORCE_FRESH"
    }
    $ReadOnly = Invoke-PythonJson -Arguments @(
        "-m", "ibkr_paper_30d.cli", "inspect-ibkr-readonly",
        "--host", "127.0.0.1", "--port", "4002"
    )
    if (-not (Test-ReadOnlyReconciliation -ReadOnly $ReadOnly)) {
        throw "READONLY_IDENTITY_GATE_NOT_PASS:$($ReadOnly.reason_codes -join ',')"
    }
    $Validation = Invoke-PythonJson -Arguments @(
        "-m", "ibkr_paper_30d.cli", "validate-real-market-data",
        "--host", "127.0.0.1", "--port", "4002",
        "--policy", $PolicyPath
    )
    if ($Validation.market_data_gate -ne "PASS") {
        throw "MARKET_DATA_QUICK_CHECK_BLOCK:$($Validation.reason_codes -join ',')"
    }
    $Ready = Invoke-PythonJson -Arguments @(
        "-m", "ibkr_paper_30d.prerequisite_tools", "readiness",
        "--report-root", $ReportRoot
    )
    Invoke-Day1ForegroundService
    exit 0
}

Assert-RegularCollectionStart
Archive-CollectionEvidence -Reason "forced-refresh"
Initialize-CleanEvidence

$ReadOnly = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.cli", "inspect-ibkr-readonly",
    "--host", "127.0.0.1", "--port", "4002"
)
if (-not (Test-ReadOnlyReconciliation -ReadOnly $ReadOnly)) {
    throw "READONLY_IDENTITY_GATE_NOT_PASS:$($ReadOnly.reason_codes -join ',')"
}

try {
    $Starts = @()
    for ($Index = 0; $Index -lt 3; $Index++) {
        if ($Index -gt 0) {
            $Target = $Starts[$Index - 1].AddMinutes(31)
            Wait-UntilUtc -Target $Target
        }
        $Starts += [DateTime]::UtcNow
        $Observation = Invoke-PythonJson -Arguments @(
            "-m", "ibkr_paper_30d.cli", "observe-market-data",
            "--host", "127.0.0.1", "--port", "4002",
            "--symbols", "SPY", "QQQ", "IEF",
            "--cadence-seconds", "4",
            "--window-seconds", "330"
        )
        if ($Observation.status -ne "PASS") {
            throw "MARKET_OBSERVATION_BLOCK:$($Observation.reason_codes -join ',')"
        }
    }

    $Freeze = Invoke-PythonJson -Arguments @(
        "-m", "ibkr_paper_30d.cli", "freeze-market-policy",
        "--ledger", $LedgerPath,
        "--destination", $PolicyPath
    )
    if ($Freeze.status -notin @("PASS", "ALREADY_FROZEN")) {
        throw "MARKET_POLICY_FREEZE_BLOCK:$($Freeze.reason_codes -join ',')"
    }

    $Validation = Invoke-PythonJson -Arguments @(
        "-m", "ibkr_paper_30d.cli", "validate-real-market-data",
        "--host", "127.0.0.1", "--port", "4002",
        "--policy", $PolicyPath
    )
    if ($Validation.market_data_gate -ne "PASS") {
        throw "MARKET_DATA_GATE_BLOCK:$($Validation.reason_codes -join ',')"
    }
}
catch {
    Archive-CollectionEvidence -Reason "failed"
    throw
}

$Ready = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.prerequisite_tools", "readiness",
    "--report-root", $ReportRoot
)

Invoke-Day1ForegroundService
exit 0
