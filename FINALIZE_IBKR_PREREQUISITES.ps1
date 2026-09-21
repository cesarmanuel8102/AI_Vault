#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT",
    [string]$PythonExe = "python",
    [switch]$SkipTaskRegistration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedAuditorSid = "S-1-5-21-214160970-1890373857-4055601883-1012"
$AuditorUser = "CodexAuditorV1"
$ProgramRoot = "C:\ProgramData\CodexAuditorV1"
$RuntimeRoot = Join-Path $ProgramRoot "runtime"
$ProvisioningRoot = Join-Path $ProgramRoot "provisioning"
$ExportsRoot = Join-Path $ProgramRoot "exports"
$ReportsRoot = Join-Path $ProgramRoot "reports"
$TargetManifest = Join-Path $ProvisioningRoot "AUDITOR_PROBE_TARGET_MANIFEST_V1.json"
$DeploymentManifest = Join-Path $ProvisioningRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT_MANIFEST.json"
$RuntimeManifest = Join-Path $RuntimeRoot "AUDITOR_RUNTIME_MANIFEST_V2.json"
$ProbePath = Join-Path $RuntimeRoot "AUDITOR_GATE_V2_PROBE.ps1"
$CanonicalReportRoot = Join-Path $ResolvedRepoRoot "state\ibkr_paper_30d\reports"
$ReadOnlyReport = Join-Path $CanonicalReportRoot "read_only_real_paper_reconciliation.json"
$CanonicalAuditorReceipt = Join-Path $CanonicalReportRoot "auditor_gate_v2_receipt.json"
$MarketValidation = Join-Path $CanonicalReportRoot "market_data_validation.json"
$MarketTaskName = "CodexIBKRMarketDataGate"
$CanonicalAcceptance = Join-Path $ResolvedRepoRoot "AUDITOR_MONTH1_PAPER_RESIDUAL_RISK_ACCEPTANCE_V1.json"

function Assert-Administrator {
    $Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $Principal = New-Object Security.Principal.WindowsPrincipal($Identity)
    if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "ADMINISTRATOR_REQUIRED"
    }
}

function Get-Sha256Lower {
    param([string]$LiteralPath)
    return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-PythonJson {
    param([string[]]$Arguments)
    $Output = @(& $PythonExe @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "PYTHON_COMMAND_FAILED:$($Arguments -join ' '):$($Output -join ' | ')"
    }
    $Candidates = @($Output | Where-Object { ([string]$_).TrimStart().StartsWith("{") })
    if ($Candidates.Count -eq 0) {
        throw "PYTHON_JSON_OUTPUT_MISSING:$($Output -join ' | ')"
    }
    return ([string]$Candidates[-1] | ConvertFrom-Json)
}

function New-RandomSecurePassword {
    $Bytes = New-Object byte[] 36
    $Rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Rng.GetBytes($Bytes) } finally { $Rng.Dispose() }
    $Plain = ([Convert]::ToBase64String($Bytes) + "!Aa9")
    try {
        return ConvertTo-SecureString $Plain -AsPlainText -Force
    }
    finally {
        $Plain = $null
    }
}

function Quote-Argument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

Assert-Administrator

$ResolvedRepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
if ($ResolvedRepoRoot -ine "C:\AI_VAULT") {
    throw "REPO_ROOT_MUST_BE_C:\AI_VAULT"
}
if (-not (Test-Path -LiteralPath $ResolvedRepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$ResolvedRepoRoot"
}
$ResolvedPython = if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
    [IO.Path]::GetFullPath($PythonExe)
} else {
    (Get-Command $PythonExe -ErrorAction Stop).Source
}
Set-Location -LiteralPath $ResolvedRepoRoot
[void](New-Item -ItemType Directory -Path $CanonicalReportRoot -Force)

if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 4002 -InformationLevel Quiet)) {
    throw "IBKR_PAPER_GATEWAY_4002_NOT_LISTENING"
}

$ReadOnly = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.cli", "inspect-ibkr-readonly",
    "--host", "127.0.0.1", "--port", "4002"
)
if ($ReadOnly.status -ne "PASS") {
    throw "READONLY_IDENTITY_GATE_NOT_PASS:$($ReadOnly.reason_codes -join ',')"
}
if (
    $ReadOnly.gateway_mode -ne "PAPER" -or
    $ReadOnly.paper_account_identity_gate -ne "PASS" -or
    $ReadOnly.real_ibkr_read_only_identity_gate -ne "PASS" -or
    $ReadOnly.broker_reconciliation_gate -ne "PASS"
) {
    throw "PAPER_IDENTITY_NOT_PROVEN"
}

$ExistingAuditor = Get-LocalUser -Name $AuditorUser -ErrorAction SilentlyContinue
$ExistingTargetManifest = Test-Path -LiteralPath $TargetManifest -PathType Leaf
if ($null -eq $ExistingAuditor -or -not $ExistingTargetManifest) {
    & PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ResolvedRepoRoot "AUDITOR_WINDOWS_PROVISIONING_V1.ps1") -Mode Apply -Confirm:$false
    if ($LASTEXITCODE -ne 0) { throw "AUDITOR_PROVISIONING_V1_FAILED" }
}

$User = Get-LocalUser -Name $AuditorUser -ErrorAction Stop
if ($User.SID.Value -ne $ExpectedAuditorSid) {
    throw "AUDITOR_SID_MISMATCH:ACTUAL=$($User.SID.Value):EXPECTED=$ExpectedAuditorSid"
}
if (-not $User.Enabled) {
    Enable-LocalUser -Name $AuditorUser
}

& PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ResolvedRepoRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1") -Mode Install -ConfirmRuntimeMutation
if ($LASTEXITCODE -ne 0) { throw "AUDITOR_RUNTIME_V2_INSTALL_FAILED" }

$ReviewOutput = @(& PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ResolvedRepoRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1") -Mode Review)
$ReviewJson = ($ReviewOutput -join [Environment]::NewLine) | ConvertFrom-Json
if ($ReviewJson.INSTALLED_RUNTIME_EXACT -ne $true) {
    throw "AUDITOR_RUNTIME_V2_NOT_EXACT"
}

$AuditExport = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.prerequisite_tools", "create-audit-export",
    "--readonly-report", $ReadOnlyReport,
    "--export-root", $ExportsRoot
)

if (-not (Test-Path -LiteralPath $AuditExport.bundle_path -PathType Container)) {
    throw "AUDIT_EXPORT_BUNDLE_MISSING"
}
if (-not (Test-Path -LiteralPath $AuditExport.paper_identity_receipt_path -PathType Leaf)) {
    throw "EXPORTED_PAPER_IDENTITY_RECEIPT_MISSING"
}

$DeploymentSha = Get-Sha256Lower -LiteralPath $DeploymentManifest
$PaperHash = [string]$ReadOnly.expected_account_identity_hash
if ($PaperHash -notmatch '^[0-9a-f]{64}$') {
    throw "EXPECTED_PAPER_ACCOUNT_HASH_INVALID"
}

# Ensure exact denial-probe leaf targets exist. Temporary markers are removed later.
$TemporaryProbeTargets = New-Object Collections.Generic.List[string]
$LegacyExecutionLock = Join-Path $ResolvedRepoRoot "state\ibkr_paper_30d\execution.lock"
if (-not (Test-Path -LiteralPath $LegacyExecutionLock -PathType Leaf)) {
    [IO.File]::WriteAllText($LegacyExecutionLock, '{"schema":"AUDITOR_PROBE_LOCK_TARGET_V1","order_authority":false}')
    $TemporaryProbeTargets.Add($LegacyExecutionLock)
}
$LiveInvocationDb = Join-Path $CanonicalReportRoot "real_codex_invocations.sqlite3"
if (-not (Test-Path -LiteralPath $LiveInvocationDb -PathType Leaf)) {
    $DbInit = @(& python -c "from ibkr_paper_30d.persistence import Database; db=Database.open(r'$LiveInvocationDb'); db.close(); print('OK')" 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "LIVE_INVOCATION_DB_PROBE_TARGET_CREATE_FAILED:$($DbInit -join ' | ')" }
}
$SmtpProbeTarget = Join-Path $ResolvedRepoRoot "Secrets\email_alerts.env"
if (-not (Test-Path -LiteralPath $SmtpProbeTarget -PathType Leaf)) {
    [IO.File]::WriteAllText($SmtpProbeTarget, "# temporary auditor denial probe target" + [Environment]::NewLine)
    $TemporaryProbeTargets.Add($SmtpProbeTarget)
}

# Reset only the dedicated local auditor account password. The SID is preserved.
$SecurePassword = New-RandomSecurePassword
Set-LocalUser -Name $AuditorUser -Password $SecurePassword
$Credential = New-Object Security.Management.Automation.PSCredential(
    "$env:COMPUTERNAME\$AuditorUser",
    $SecurePassword
)

$SecondaryLogon = Get-Service -Name seclogon -ErrorAction SilentlyContinue
if ($null -ne $SecondaryLogon -and $SecondaryLogon.Status -ne "Running") {
    Start-Service -Name seclogon
}

$StdoutPath = Join-Path $ReportsRoot ("probe-launch-" + [Guid]::NewGuid().ToString("N") + ".out.txt")
$StderrPath = Join-Path $ReportsRoot ("probe-launch-" + [Guid]::NewGuid().ToString("N") + ".err.txt")
$ProbeStart = [DateTime]::UtcNow

$Arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Quote-Argument $ProbePath),
    "-BundlePath", (Quote-Argument ([string]$AuditExport.bundle_path)),
    "-PaperIdentityReceiptPath", (Quote-Argument ([string]$AuditExport.paper_identity_receipt_path)),
    "-TargetManifestPath", (Quote-Argument $TargetManifest),
    "-DeploymentManifestPath", (Quote-Argument $DeploymentManifest),
    "-ExpectedDeploymentManifestSha256", $DeploymentSha,
    "-ExpectedPaperAccountHash", $PaperHash,
    "-ExpectedSid", $ExpectedAuditorSid,
    "-ReportDirectory", (Quote-Argument $ReportsRoot)
) -join " "

$Receipt = $null
try {
    $WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$Process = Start-Process -FilePath $WindowsPowerShell -ArgumentList $Arguments -Credential $Credential -UseNewEnvironment -WorkingDirectory $RuntimeRoot -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    if ($Process.ExitCode -ne 0) {
        $Err = if (Test-Path $StderrPath) { Get-Content -LiteralPath $StderrPath -Raw } else { "" }
        $Out = if (Test-Path $StdoutPath) { Get-Content -LiteralPath $StdoutPath -Raw } else { "" }
        throw "AUDITOR_GATE_V2_PROBE_FAILED:EXIT=$($Process.ExitCode):OUT=$Out:ERR=$Err"
    }

    $Receipt = Get-ChildItem -LiteralPath $ReportsRoot -Filter "auditor-gate-v2-*.json" -File |
        Where-Object { $_.LastWriteTimeUtc -ge $ProbeStart.AddSeconds(-2) } |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if ($null -eq $Receipt) {
        throw "AUDITOR_GATE_V2_RECEIPT_NOT_CREATED"
    }
    Copy-Item -LiteralPath $Receipt.FullName -Destination $CanonicalAuditorReceipt -Force
}
finally {
    foreach ($TemporaryPath in $TemporaryProbeTargets) {
        if (Test-Path -LiteralPath $TemporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $TemporaryPath -Force
        }
    }
}

$RuntimeManifestSha = Get-Sha256Lower -LiteralPath $RuntimeManifest
$DeploymentManifestSha = Get-Sha256Lower -LiteralPath $DeploymentManifest
$ProbeSha = Get-Sha256Lower -LiteralPath $ProbePath
$TargetManifestSha = Get-Sha256Lower -LiteralPath $TargetManifest

$env:AUDITOR_RUNTIME_MANIFEST_V2_SHA256 = $RuntimeManifestSha
$env:AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2_SHA256 = $DeploymentManifestSha
$env:AUDITOR_GATE_V2_PROBE_SHA256 = $ProbeSha
$env:AUDITOR_PROBE_TARGET_MANIFEST_SHA256 = $TargetManifestSha

$AuditorEvaluation = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.prerequisite_tools", "evaluate-auditor",
    "--receipt", $CanonicalAuditorReceipt,
    "--readonly-report", $ReadOnlyReport,
    "--runtime-manifest-sha256", $RuntimeManifestSha,
    "--deployment-manifest-sha256", $DeploymentManifestSha,
    "--probe-sha256", $ProbeSha,
    "--probe-manifest-sha256", $TargetManifestSha
)
if ($AuditorEvaluation.canonical_gate -ne "PASS" -or $AuditorEvaluation.compatibility_gate -ne "PASS") {
    throw "AUDITOR_GATE_V2_BLOCK:$($AuditorEvaluation.reason_codes -join ',')"
}

$AcceptanceCreated = $false
if (-not (Test-Path -LiteralPath $CanonicalAcceptance -PathType Leaf)) {
    $AuditorArtifacts = Invoke-PythonJson -Arguments @(
        "-m", "ibkr_paper_30d.cli", "write-auditor-v2-artifacts",
        "--receipt", $CanonicalAuditorReceipt
    )
    if ($AuditorArtifacts.gate -ne "PASS") {
        throw "AUDITOR_GATE_V2_ARTIFACT_BLOCK:$($AuditorArtifacts.reason_codes -join ',')"
    }
    $AcceptanceCreated = $true
}

$MarketAlreadyPass = $false
if (Test-Path -LiteralPath $MarketValidation -PathType Leaf) {
    try {
        $MarketPayload = Get-Content -LiteralPath $MarketValidation -Raw | ConvertFrom-Json
        $MarketAlreadyPass = $MarketPayload.market_data_gate -eq "PASS"
    }
    catch { $MarketAlreadyPass = $false }
}

$TaskRegistered = $false
if (-not $MarketAlreadyPass -and -not $SkipTaskRegistration) {
    $MarketScript = Join-Path $ResolvedRepoRoot "RUN_IBKR_MARKET_DATA_GATE.ps1"
    if (-not (Test-Path -LiteralPath $MarketScript -PathType Leaf)) {
        throw "MARKET_DATA_GATE_SCRIPT_MISSING"
    }

    $TaskAction = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument (
        "-NoProfile -ExecutionPolicy Bypass -File " +
        (Quote-Argument $MarketScript) +
        " -RepoRoot " + (Quote-Argument $ResolvedRepoRoot) +
        " -PythonExe " + (Quote-Argument $ResolvedPython) +
        " -Scheduled"
    )
    $TaskTrigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:35AM
    $CurrentIdentityName = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $Principal = New-ScheduledTaskPrincipal -UserId $CurrentIdentityName -LogonType Interactive -RunLevel Highest
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3)
    Register-ScheduledTask -TaskName $MarketTaskName -Action $TaskAction -Trigger $TaskTrigger -Principal $Principal -Settings $Settings -Force | Out-Null
    $TaskRegistered = $true
}

$Ready = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.prerequisite_tools", "readiness",
    "--report-root", $CanonicalReportRoot
)

[ordered]@{
    status = "AUDITOR_PASS"
    auditor_gate_v2 = "PASS"
    auditor_acceptance_created = $AcceptanceCreated
    market_data_gate = $(if ($MarketAlreadyPass) { "PASS" } else { "PENDING_REGULAR_SESSION_EVIDENCE" })
    market_data_task_registered = $TaskRegistered
    market_data_task_name = $(if ($TaskRegistered) { $MarketTaskName } else { $null })
    paper_execution_armed = $false
    autonomous_experiment_started = $false
    readiness = $Ready
} | ConvertTo-Json -Depth 8
