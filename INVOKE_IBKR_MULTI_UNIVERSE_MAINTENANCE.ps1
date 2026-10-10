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
        "PREDECESSOR_RETIRED",
        "SUCCESSOR_COMMITTED",
        "SUPERVISION_BOUND",
        "CANARY_EXCLUSIVE",
        "CANARY_PASS",
        "RUNTIME_BOUND",
        "ACTIVE"
    )]
    [string]$PhaseTarget = "PREPARED",

    [Parameter()]
    [string]$ConfigPath,

    [Parameter()]
    [string]$EvidencePath,

    [Parameter()]
    [string]$ApprovedHead
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
if ($ApprovedHead -and $CurrentHead -ne $ApprovedHead) {
    throw "APPROVED_HEAD_MISMATCH"
}

$Mode = if ($Apply) { "apply" } else { "validate" }
if ([string]::IsNullOrWhiteSpace($ConfigPath) -or
    [string]::IsNullOrWhiteSpace($EvidencePath)) {
    [ordered]@{
        schema = "IBKR_MULTI_UNIVERSE_MAINTENANCE_V2"
        mode = "VALIDATE_ONLY"
        status = "BLOCK"
        mutation_performed = $false
        approved_head = $CurrentHead
        reason_codes = @("MAINTENANCE_CONFIG_EVIDENCE_REQUIRED")
    } | ConvertTo-Json -Compress
    exit 0
}

$ResolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$ResolvedEvidence = (Resolve-Path -LiteralPath $EvidencePath).Path
$Python = (Get-Command python.exe -ErrorAction Stop).Source
& $Python -B -m ibkr_paper_30d.multi_universe_maintenance `
    --mode $Mode `
    --phase $PhaseTarget `
    --config $ResolvedConfig `
    --evidence $ResolvedEvidence
exit $LASTEXITCODE
