#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT_IBKR",
    [string]$PythonExe = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ApprovedRepoRoot {
    param([string]$Path)
    $Resolved = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $Approved = [IO.Path]::GetFullPath("C:\AI_VAULT_IBKR").TrimEnd('\')
    if ($Resolved -ine $Approved) {
        throw "REPO_ROOT_NOT_APPROVED:$Resolved"
    }
    return $Resolved
}

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

$ResolvedRepoRoot = Resolve-ApprovedRepoRoot -Path $RepoRoot
if (-not (Test-Path -LiteralPath $ResolvedRepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$ResolvedRepoRoot"
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf) -and $null -eq (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    throw "PYTHON_EXECUTABLE_NOT_FOUND:$PythonExe"
}
if ([string]$env:IBKR_AUTONOMOUS_PAPER_ARMED -match '^(?i:true|1|yes)$') {
    throw "CAPABILITY_DISCOVERY_REQUIRES_UNARMED_EXPERIMENT"
}
if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 4002 -InformationLevel Quiet)) {
    throw "IBKR_PAPER_GATEWAY_4002_NOT_LISTENING"
}

Set-Location -LiteralPath $ResolvedRepoRoot

$Result = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.cli", "discover-ibkr-capabilities",
    "--host", "127.0.0.1",
    "--port", "4002",
    "--client-id", "19751",
    "--timeout-seconds", "8"
)

if ($Result.status -eq "BLOCK") {
    throw "CAPABILITY_DISCOVERY_BLOCK:$($Result.reason_codes -join ',')"
}
if ($Result.real_order_writes_attempted -ne 0) {
    throw "CAPABILITY_DISCOVERY_ORDER_WRITE_INVARIANT_BROKEN"
}
if ($Result.outbound_allowlist_only -ne $true) {
    throw "CAPABILITY_DISCOVERY_TRANSPORT_ALLOWLIST_BROKEN"
}
if ($Result.gateway_mode -ne "PAPER") {
    throw "CAPABILITY_DISCOVERY_NOT_PAPER"
}

$Result | ConvertTo-Json -Depth 12
