#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT",
    [string]$Branch = "codex/ibkr-paper-auditor-gate-v2",
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $Output = @(& git @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "GIT_FAILED:git $($Arguments -join ' '):$($Output -join ' | ')"
    }
    return $Output
}

$ResolvedRepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
if ($ResolvedRepoRoot -ine "C:\AI_VAULT") {
    throw "REPO_ROOT_MUST_BE_C:\AI_VAULT"
}
if (-not (Test-Path -LiteralPath $ResolvedRepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$ResolvedRepoRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $ResolvedRepoRoot ".git"))) {
    throw "NOT_A_GIT_WORKTREE:$ResolvedRepoRoot"
}
if ($null -eq (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "GIT_NOT_FOUND"
}

Set-Location -LiteralPath $ResolvedRepoRoot

$Dirty = @(& git status --porcelain=v1)
if ($LASTEXITCODE -ne 0) { throw "GIT_STATUS_FAILED" }
if ($Dirty.Count -ne 0) {
    $BackupRoot = Join-Path $ResolvedRepoRoot "state\local_sync_backups"
    [void](New-Item -ItemType Directory -Path $BackupRoot -Force)
    $Stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $StatusPath = Join-Path $BackupRoot ("dirty-status-" + $Stamp + ".txt")
    $DiffPath = Join-Path $BackupRoot ("dirty-diff-" + $Stamp + ".patch")
    $Dirty | Set-Content -LiteralPath $StatusPath -Encoding UTF8
    @(& git diff --binary HEAD) | Set-Content -LiteralPath $DiffPath -Encoding UTF8
    throw "LOCAL_SYNC_BLOCKED_DIRTY_TREE:STATUS=$StatusPath:DIFF=$DiffPath"
}

[void](Invoke-Git fetch origin --prune)
[void](Invoke-Git fetch origin $Branch)

$LocalBranchExists = $false
& git show-ref --verify --quiet ("refs/heads/" + $Branch)
if ($LASTEXITCODE -eq 0) { $LocalBranchExists = $true }

if ($LocalBranchExists) {
    [void](Invoke-Git switch $Branch)
} else {
    [void](Invoke-Git switch --track -c $Branch ("origin/" + $Branch))
}

[void](Invoke-Git pull --ff-only origin $Branch)

$LocalHead = ([string]((& git rev-parse HEAD) | Select-Object -First 1)).Trim()
if ($LASTEXITCODE -ne 0) { throw "LOCAL_HEAD_RESOLUTION_FAILED" }
$RemoteHead = ([string]((& git rev-parse ("origin/" + $Branch)) | Select-Object -First 1)).Trim()
if ($LASTEXITCODE -ne 0) { throw "REMOTE_HEAD_RESOLUTION_FAILED" }

if ($LocalHead -ne $RemoteHead) {
    throw "LOCAL_REMOTE_HEAD_MISMATCH:LOCAL=$LocalHead:REMOTE=$RemoteHead"
}

$RequiredFiles = @(
    "CODEX_HANDOFF_AUTONOMOUS_IBKR_V1.md",
    "CODEX_IBKR_AUTONOMOUS_RESEARCH_V1.md",
    "IBKR_PREREQUISITE_FINALIZATION_RUNBOOK.md",
    "FINALIZE_IBKR_PREREQUISITES.ps1",
    "RUN_IBKR_MARKET_DATA_GATE.ps1",
    "ibkr_paper_30d\autonomous_research.py",
    "ibkr_paper_30d\ibkr_research_tools.py",
    "ibkr_paper_30d\autonomous_execution.py",
    "ibkr_paper_30d\autonomous_runtime.py",
    "ibkr_paper_30d\autonomous_state.py",
    "ibkr_paper_30d\autonomous_service.py",
    "ibkr_paper_30d\experiment_ledger.py",
    "ibkr_paper_30d\prerequisite_tools.py"
)
$Missing = @($RequiredFiles | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $ResolvedRepoRoot $_) -PathType Leaf)
})
if ($Missing.Count -ne 0) {
    throw "REQUIRED_FILES_MISSING:$($Missing -join ',')"
}

$TestsPassed = $null
if (-not $SkipTests) {
    $TestFiles = @(
        "tests/ibkr_paper_30d/test_autonomous_research.py",
        "tests/ibkr_paper_30d/test_capital_boundary_risk.py",
        "tests/ibkr_paper_30d/test_autonomous_execution.py",
        "tests/ibkr_paper_30d/test_autonomous_runtime.py",
        "tests/ibkr_paper_30d/test_experiment_ledger.py",
        "tests/ibkr_paper_30d/test_autonomous_state.py",
        "tests/ibkr_paper_30d/test_autonomous_service.py",
        "tests/ibkr_paper_30d/test_autonomous_architecture_contract.py",
        "tests/ibkr_paper_30d/test_autonomous_codex_provider.py",
        "tests/ibkr_paper_30d/test_bounded_level4_structures.py",
        "tests/ibkr_paper_30d/test_prerequisite_tools.py",
        "tests/ibkr_paper_30d/test_market_observation_collector.py",
        "tests/ibkr_paper_30d/test_risk.py",
        "tests/ibkr_paper_30d/test_trader_invocation.py"
    )
    $PytestOutput = @(& python -m pytest -q @TestFiles 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "LOCAL_VALIDATION_FAILED:$($PytestOutput -join ' | ')"
    }
    $TestsPassed = ($PytestOutput -join [Environment]::NewLine)
}

$ReportRoot = Join-Path $ResolvedRepoRoot "state\ibkr_paper_30d\reports"
[void](New-Item -ItemType Directory -Path $ReportRoot -Force)
$ReceiptPath = Join-Path $ReportRoot "local_repository_sync_receipt.json"
$RequiredHashes = [ordered]@{}
foreach ($Relative in $RequiredFiles) {
    $RequiredHashes[$Relative] = (
        Get-FileHash -LiteralPath (Join-Path $ResolvedRepoRoot $Relative) -Algorithm SHA256
    ).Hash.ToLowerInvariant()
}

$Receipt = [ordered]@{
    schema = "AI_VAULT_LOCAL_SYNC_RECEIPT_V1"
    completed_at_utc = [DateTime]::UtcNow.ToString("o").Replace("+00:00", "Z")
    repo_root = $ResolvedRepoRoot
    branch = $Branch
    local_head = $LocalHead
    remote_head = $RemoteHead
    synchronized = ($LocalHead -eq $RemoteHead)
    dirty_tree_after_sync = (@(& git status --porcelain=v1)).Count -ne 0
    required_files_sha256 = $RequiredHashes
    local_validation_executed = -not $SkipTests
    local_validation_output = $TestsPassed
    paper_execution_armed = (
        [string]$env:IBKR_AUTONOMOUS_PAPER_ARMED
    ).ToLowerInvariant() -eq "true"
}
$Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8

if ($Receipt.dirty_tree_after_sync) {
    throw "WORKTREE_BECAME_DIRTY_AFTER_SYNC:$ReceiptPath"
}

[ordered]@{
    status = "PASS"
    branch = $Branch
    head = $LocalHead
    local_matches_remote = $true
    handoff = "CODEX_HANDOFF_AUTONOMOUS_IBKR_V1.md"
    receipt = $ReceiptPath
    paper_execution_armed = $Receipt.paper_execution_armed
} | ConvertTo-Json -Depth 6
