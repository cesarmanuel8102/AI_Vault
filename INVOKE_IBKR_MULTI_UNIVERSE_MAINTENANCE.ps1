[CmdletBinding()]
param(
    [Parameter()]
    [string]$RepoRoot = "C:\AI_VAULT_IBKR_WHATIF_FIX",

    [Parameter()]
    [switch]$ValidateOnly,

    [Parameter()]
    [switch]$Apply,

    [Parameter()]
    [ValidateSet(
        "PREPARED",
        "PREDECESSOR_QUIESCED",
        "CANARY_EXCLUSIVE",
        "CANARY_PASS",
        "PREDECESSOR_RETIRED",
        "SUCCESSOR_COMMITTED",
        "RUNTIME_BOUND",
        "ACTIVE"
    )]
    [string]$PhaseTarget,

    [Parameter()]
    [string]$OwnerReceiptPath,

    [Parameter()]
    [string]$CanaryReceiptPath,

    [Parameter()]
    [string]$SuccessorReceiptPath,

    [Parameter()]
    [string]$ApprovedHead,

    [Parameter()]
    [string]$ExclusiveLockEvidencePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Apply -and $ValidateOnly) {
    throw "MAINTENANCE_MODE_AMBIGUOUS"
}

$ResolvedRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$CurrentHead = (& git -C $ResolvedRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $CurrentHead) {
    throw "REPOSITORY_HEAD_UNAVAILABLE"
}

if ($Apply) {
    $Required = @{
        OwnerReceiptPath = $OwnerReceiptPath
        CanaryReceiptPath = $CanaryReceiptPath
        SuccessorReceiptPath = $SuccessorReceiptPath
        ApprovedHead = $ApprovedHead
        ExclusiveLockEvidencePath = $ExclusiveLockEvidencePath
        PhaseTarget = $PhaseTarget
    }
    foreach ($Entry in $Required.GetEnumerator()) {
        if ([string]::IsNullOrWhiteSpace([string]$Entry.Value)) {
            throw "MAINTENANCE_APPLY_AUTHORITY_INCOMPLETE:$($Entry.Key)"
        }
    }
    foreach ($Receipt in @(
        $OwnerReceiptPath,
        $CanaryReceiptPath,
        $SuccessorReceiptPath,
        $ExclusiveLockEvidencePath
    )) {
        if (-not (Test-Path -LiteralPath $Receipt -PathType Leaf)) {
            throw "MAINTENANCE_RECEIPT_MISSING"
        }
    }
    if ($CurrentHead -ne $ApprovedHead) {
        throw "APPROVED_HEAD_MISMATCH"
    }
    [ordered]@{
        schema = "IBKR_MULTI_UNIVERSE_MAINTENANCE_V1"
        mode = "APPLY_PREPARED"
        mutation_performed = $false
        phase_target = $PhaseTarget
        approved_head = $CurrentHead
        reason_codes = @("OWNER_REVIEW_REQUIRED_BEFORE_APPLY")
    } | ConvertTo-Json -Compress
    exit 0
}

[ordered]@{
    schema = "IBKR_MULTI_UNIVERSE_MAINTENANCE_V1"
    mode = "VALIDATE_ONLY"
    mutation_performed = $false
    approved_head = $CurrentHead
    reason_codes = @()
} | ConvertTo-Json -Compress
