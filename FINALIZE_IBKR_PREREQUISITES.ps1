#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT_IBKR",
    [string]$PythonExe = "python",
    [switch]$SkipTaskRegistration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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
$ResolvedPython = if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
    [IO.Path]::GetFullPath($PythonExe)
} else {
    (Get-Command $PythonExe -ErrorAction Stop).Source
}
$WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

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
$ProbeFirewallRuleName = "CodexAuditorV2-Probe-PowerShell-Broker-Block"
$CanonicalAcceptance = Join-Path $ResolvedRepoRoot "AUDITOR_MONTH1_PAPER_RESIDUAL_RISK_ACCEPTANCE_V1.json"
$TrustAnchorPath = Join-Path $ResolvedRepoRoot "AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1.json"
$ExpectedTrustAnchorSha256 = "28622ab5cdb91a25f9e04115a98e1f4acb92d3b26f29f9c38abb345ff457ba23"

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
    $PriorErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 can promote redirected native stderr to a
        # terminating NativeCommandError when ErrorActionPreference is Stop.
        # Capture the complete child output first, then fail on its exit code.
        $ErrorActionPreference = "Continue"
        $Output = @(& $ResolvedPython @Arguments 2>&1)
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
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "EMPTY_ARGUMENT_VALUE" }
    $Forbidden = [char[]]@([char]34, [char]36, [char]96, [char]59, [char]38, [char]124, [char]60, [char]62, [char]13, [char]10)
    if ($Value.EndsWith('\') -or $Value.IndexOfAny($Forbidden) -ge 0) {
        throw "UNSAFE_ARGUMENT_VALUE"
    }
    return '"' + $Value + '"'
}

$RequiredProbeTargetNames = @(
    "SECRETS_READ",
    "IBKR_SECRET_READ",
    "SMTP_SECRET_READ",
    "EXECUTION_LOCK_ACCESS",
    "LIVE_DATABASE_MUTATION",
    "BROKER_WRITE_PATH_ACCESS",
    "BROKER_NETWORK_SOCKET_ACCESS",
    "TRADER_CONTEXT_ACCESS",
    "AUDIT_INPUT_MUTATION",
    "IMMUTABLE_EXPORT_READ",
    "AUDITOR_REPORT_WRITE"
)

function Test-StringSetEqualOrdinalIgnoreCase {
    param([object[]]$Left, [object[]]$Right)
    $LeftNormalized = @($Left | ForEach-Object { [string]$_ } | Sort-Object)
    $RightNormalized = @($Right | ForEach-Object { [string]$_ } | Sort-Object)
    if ($LeftNormalized.Count -ne $RightNormalized.Count) { return $false }
    for ($I = 0; $I -lt $LeftNormalized.Count; $I++) {
        if (-not [string]::Equals($LeftNormalized[$I], $RightNormalized[$I], [StringComparison]::OrdinalIgnoreCase)) {
            return $false
        }
    }
    return $true
}

function Test-AuditorTargetManifestCurrent {
    param(
        [string]$LiteralPath,
        [string]$ExpectedSid,
        [string]$RepoRoot
    )
    if (-not (Test-Path -LiteralPath $LiteralPath -PathType Leaf)) { return $false }
    try {
        $ManifestValue = Get-Content -LiteralPath $LiteralPath -Raw | ConvertFrom-Json
    }
    catch { return $false }
    if (
        $ManifestValue.schema -ne "AUDITOR_PROBE_TARGET_MANIFEST_V1" -or
        [string]$ManifestValue.expected_sid -ne $ExpectedSid -or
        $null -eq $ManifestValue.targets -or
        $null -eq $ManifestValue.approved_roots
    ) { return $false }

    $ActualTargetNames = @($ManifestValue.targets.PSObject.Properties.Name)
    if (-not (Test-StringSetEqualOrdinalIgnoreCase -Left $ActualTargetNames -Right $RequiredProbeTargetNames)) {
        return $false
    }

    $ActiveStateRoot = Join-Path $RepoRoot "state\ibkr_paper_30d"
    $ExpectedTargets = [ordered]@{
        SECRETS_READ = (Join-Path $RepoRoot "Secrets")
        IBKR_SECRET_READ = "C:\Jts"
        SMTP_SECRET_READ = (Join-Path $RepoRoot "Secrets\email_alerts.env")
        EXECUTION_LOCK_ACCESS = (Join-Path $ActiveStateRoot "execution.lock")
        LIVE_DATABASE_MUTATION = (Join-Path $ActiveStateRoot "reports\real_codex_invocations.sqlite3")
        BROKER_WRITE_PATH_ACCESS = (Join-Path $RepoRoot "ibkr_paper_30d\broker.py")
        BROKER_NETWORK_SOCKET_ACCESS = (Join-Path $RepoRoot "ibkr_paper_30d\broker.py")
        TRADER_CONTEXT_ACCESS = (Join-Path $RepoRoot "ibkr_paper_30d\trader_invocation.py")
        AUDIT_INPUT_MUTATION = $ExportsRoot
        IMMUTABLE_EXPORT_READ = $ExportsRoot
        AUDITOR_REPORT_WRITE = $ReportsRoot
    }
    foreach ($Name in $RequiredProbeTargetNames) {
        $ActualPath = [IO.Path]::GetFullPath([string]$ManifestValue.targets.$Name).TrimEnd('\')
        $ExpectedPath = [IO.Path]::GetFullPath([string]$ExpectedTargets[$Name]).TrimEnd('\')
        if (-not [string]::Equals($ActualPath, $ExpectedPath, [StringComparison]::OrdinalIgnoreCase)) {
            return $false
        }
    }

    $ExpectedApprovedRoots = @(
        $RuntimeRoot,
        $ExportsRoot,
        $ReportsRoot,
        $ProvisioningRoot,
        (Join-Path $RepoRoot "Secrets"),
        "C:\Jts",
        $ActiveStateRoot,
        (Join-Path $RepoRoot "ibkr_paper_30d\broker.py"),
        (Join-Path $RepoRoot "ibkr_paper_30d\trader_invocation.py")
    ) | ForEach-Object { [IO.Path]::GetFullPath([string]$_).TrimEnd('\') }
    $ActualApprovedRoots = @($ManifestValue.approved_roots) | ForEach-Object {
        [IO.Path]::GetFullPath([string]$_).TrimEnd('\')
    }
    return Test-StringSetEqualOrdinalIgnoreCase -Left $ActualApprovedRoots -Right $ExpectedApprovedRoots
}

Assert-Administrator

if (-not (Test-Path -LiteralPath $ResolvedRepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$ResolvedRepoRoot"
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
$TargetManifestCurrent = Test-AuditorTargetManifestCurrent -LiteralPath $TargetManifest -ExpectedSid $ExpectedAuditorSid -RepoRoot $ResolvedRepoRoot
if ($null -eq $ExistingAuditor -or -not $TargetManifestCurrent) {
    & PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ResolvedRepoRoot "AUDITOR_WINDOWS_PROVISIONING_V1.ps1") -Mode Apply -RepoRoot $ResolvedRepoRoot
    if ($LASTEXITCODE -ne 0) { throw "AUDITOR_PROVISIONING_V1_FAILED" }
}
if (-not (Test-AuditorTargetManifestCurrent -LiteralPath $TargetManifest -ExpectedSid $ExpectedAuditorSid -RepoRoot $ResolvedRepoRoot)) {
    throw "AUDITOR_TARGET_MANIFEST_STALE_AFTER_PROVISIONING"
}

$User = Get-LocalUser -Name $AuditorUser -ErrorAction Stop
if ($User.SID.Value -ne $ExpectedAuditorSid) {
    throw "AUDITOR_SID_MISMATCH:ACTUAL=$($User.SID.Value):EXPECTED=$ExpectedAuditorSid"
}
if ($User.Enabled) {
    Disable-LocalUser -Name $AuditorUser -ErrorAction Stop
}

if ((Get-Sha256Lower -LiteralPath $TrustAnchorPath) -ne $ExpectedTrustAnchorSha256) {
    throw "AUDITOR_TRUST_ANCHOR_HASH_MISMATCH"
}
$TrustAnchor = Invoke-PythonJson -Arguments @(
    "-m", "ibkr_paper_30d.prerequisite_tools", "evaluate-runtime-trust-anchor",
    "--repo-root", $ResolvedRepoRoot,
    "--anchor", $TrustAnchorPath
)
if ($TrustAnchor.source_matches_anchor -ne $true) {
    throw "AUDITOR_RUNTIME_SOURCE_DOES_NOT_MATCH_TRUST_ANCHOR"
}
if ([string]$TrustAnchor.anchor_sha256 -ne $ExpectedTrustAnchorSha256) {
    throw "AUDITOR_TRUST_ANCHOR_EVALUATION_MISMATCH"
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

$DeploymentSha = [string]$TrustAnchor.deployment_manifest_sha256
if ((Get-Sha256Lower -LiteralPath $DeploymentManifest) -ne $DeploymentSha) {
    throw "AUDITOR_DEPLOYMENT_MANIFEST_TRUST_ANCHOR_MISMATCH"
}
if ((Get-Sha256Lower -LiteralPath $RuntimeManifest) -ne [string]$TrustAnchor.runtime_manifest_sha256) {
    throw "AUDITOR_RUNTIME_MANIFEST_TRUST_ANCHOR_MISMATCH"
}
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
    $DbInit = @(& $ResolvedPython -c "from ibkr_paper_30d.persistence import Database; db=Database.open(r'$LiveInvocationDb'); db.close(); print('OK')" 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "LIVE_INVOCATION_DB_PROBE_TARGET_CREATE_FAILED:$($DbInit -join ' | ')" }
}
$SmtpProbeTarget = Join-Path $ResolvedRepoRoot "Secrets\email_alerts.env"
if (-not (Test-Path -LiteralPath $SmtpProbeTarget -PathType Leaf)) {
    [IO.File]::WriteAllText($SmtpProbeTarget, "# temporary auditor denial probe target" + [Environment]::NewLine)
    $TemporaryProbeTargets.Add($SmtpProbeTarget)
}

# Keep the account disabled until the bounded probe window starts.
$SecondaryLogon = Get-Service -Name seclogon -ErrorAction SilentlyContinue
$SecondaryLogonWasRunning = $null -ne $SecondaryLogon -and $SecondaryLogon.Status -eq "Running"
$SecondaryLogonOriginalStartType = if ($null -ne $SecondaryLogon) { [string]$SecondaryLogon.StartType } else { $null }
$Receipt = $null
$AuditorEnabledForProbe = $false
$ProbeFirewallInstalled = $false

try {
    Enable-LocalUser -Name $AuditorUser -ErrorAction Stop
    $AuditorEnabledForProbe = $true

    # Use a one-time random password only inside the bounded probe window.
    $SecurePassword = New-RandomSecurePassword
    Set-LocalUser -Name $AuditorUser -Password $SecurePassword
    $Credential = New-Object System.Management.Automation.PSCredential(
        "$env:COMPUTERNAME\$AuditorUser",
        $SecurePassword
    )

    if ($null -ne $SecondaryLogon -and -not $SecondaryLogonWasRunning) {
        if ($SecondaryLogonOriginalStartType -eq "Disabled") {
            Set-Service -Name seclogon -StartupType Manual
        }
        Start-Service -Name seclogon
    }

    Get-NetFirewallRule -Name $ProbeFirewallRuleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue

    # During the bounded auditor probe no local process needs broker API access.
    # Use an all-programs loopback block so a compromised auditor process cannot
    # bypass isolation by spawning another executable.
    try {
        $ProbeFirewallRule = New-NetFirewallRule -Name $ProbeFirewallRuleName -DisplayName $ProbeFirewallRuleName -Direction Outbound -Action Block -Protocol TCP -RemotePort 4001,4002 -RemoteAddress Any -Profile Any -Enabled True -ErrorAction Stop
    }
    catch {
        throw "AUDITOR_PROBE_FIREWALL_RULE_CREATION_FAILED:$($_.Exception.Message)"
    }
    if ($null -eq $ProbeFirewallRule) {
        throw "AUDITOR_PROBE_FIREWALL_RULE_CREATION_FAILED:NO_RULE_OBJECT"
    }
    $ProbeFirewallInstalled = $true

    $ProbePortFilter = $ProbeFirewallRule | Get-NetFirewallPortFilter
    $ProbeAddressFilter = $ProbeFirewallRule | Get-NetFirewallAddressFilter
    if ([string]$ProbeFirewallRule.Action -ne "Block" -or [string]$ProbeFirewallRule.Direction -ne "Outbound") {
        throw "AUDITOR_PROBE_FIREWALL_RULE_INVALID"
    }
    $ProbeAddresses = @($ProbeAddressFilter.RemoteAddress | ForEach-Object { [string]$_ })
    if ($ProbeAddresses -notcontains "Any") {
        throw "AUDITOR_PROBE_FIREWALL_SCOPE_INVALID"
    }
    $ProbePorts = @($ProbePortFilter.RemotePort | ForEach-Object { [string]$_ })
    if ($ProbePorts -notcontains "4001" -or $ProbePorts -notcontains "4002") {
        throw "AUDITOR_PROBE_FIREWALL_PORTS_INVALID"
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

    # The Start-Process cmdlet cannot deliver an explicit environment block to
    # a -Credential launch: the child receives a NULL environment, boots
    # without SystemRoot, and managed Windows PowerShell fails with 8009001d.
    # Launch through System.Diagnostics.ProcessStartInfo instead so the child
    # gets an explicitly cleared environment plus the minimal Windows bootstrap
    # variables required for powershell.exe to initialize and resolve whoami.exe.
    $NetworkCredential = $Credential.GetNetworkCredential()
    $ProbeStartInfo = New-Object System.Diagnostics.ProcessStartInfo
    if (
        $null -eq $ProbeStartInfo -or
        -not ($ProbeStartInfo.PSObject.Properties.Name -contains "UserName") -or
        -not ($ProbeStartInfo.PSObject.Properties.Name -contains "Password") -or
        -not ($ProbeStartInfo.PSObject.Properties.Name -contains "EnvironmentVariables")
    ) {
        throw "AUDITOR_PROBE_CLEAN_ENVIRONMENT_INJECTION_UNSUPPORTED"
    }
    $ProbeStartInfo.FileName = $WindowsPowerShell
    $ProbeStartInfo.Arguments = $Arguments
    $ProbeStartInfo.UserName = $NetworkCredential.UserName
    $ProbeStartInfo.Domain = $NetworkCredential.Domain
    $ProbeStartInfo.Password = $Credential.Password
    $ProbeStartInfo.UseShellExecute = $false
    $ProbeStartInfo.WorkingDirectory = $RuntimeRoot
    $ProbeStartInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $ProbeStartInfo.RedirectStandardOutput = $true
    $ProbeStartInfo.RedirectStandardError = $true
    $ProbeEnvironment = $ProbeStartInfo.EnvironmentVariables
    if ($null -eq $ProbeEnvironment) {
        throw "AUDITOR_PROBE_CLEAN_ENVIRONMENT_INJECTION_UNSUPPORTED"
    }
    # Clean-environment semantics: no parent variables are inherited by the
    # restricted auditor process. Only the Windows bootstrap variables needed
    # for powershell.exe initialization and in-child tool resolution are set.
    $ProbeEnvironment.Clear()
    $ProbeEnvironment["SystemRoot"] = $env:SystemRoot
    $ProbeEnvironment["WINDIR"] = $env:WINDIR
    $ProbeEnvironment["ComSpec"] = $env:ComSpec
    $ProbeEnvironment["PATH"] = [Environment]::GetEnvironmentVariable("PATH", [EnvironmentVariableTarget]::Machine)
    $ProbeEnvironment["PATHEXT"] = [Environment]::GetEnvironmentVariable("PATHEXT", [EnvironmentVariableTarget]::Machine)

    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $ProbeStartInfo
    if (-not $Process.Start()) { throw "AUDITOR_PROBE_PROCESS_START_FAILED" }
    $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
    $StderrTask = $Process.StandardError.ReadToEndAsync()
    $Process.WaitForExit()
    [IO.File]::WriteAllText($StdoutPath, $StdoutTask.Result)
    [IO.File]::WriteAllText($StderrPath, $StderrTask.Result)
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
    if ($ProbeFirewallInstalled -or (Get-NetFirewallRule -Name $ProbeFirewallRuleName -ErrorAction SilentlyContinue)) {
        Get-NetFirewallRule -Name $ProbeFirewallRuleName -ErrorAction SilentlyContinue |
            Remove-NetFirewallRule -ErrorAction SilentlyContinue
    }

    foreach ($TemporaryPath in $TemporaryProbeTargets) {
        if (Test-Path -LiteralPath $TemporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $TemporaryPath -Force
        }
    }

    if ($AuditorEnabledForProbe -or (Get-LocalUser -Name $AuditorUser -ErrorAction SilentlyContinue)) {
        try {
            $PostProbePassword = New-RandomSecurePassword
            Set-LocalUser -Name $AuditorUser -Password $PostProbePassword
        } catch { }
        try {
            Disable-LocalUser -Name $AuditorUser -ErrorAction Stop
        } catch { }
    }

    if ($null -ne $SecondaryLogon -and -not $SecondaryLogonWasRunning) {
        try { Stop-Service -Name seclogon -Force } catch { }
        if ($SecondaryLogonOriginalStartType -eq "Disabled") {
            try { Set-Service -Name seclogon -StartupType Disabled } catch { }
        }
    }
}

$RuntimeManifestSha = [string]$TrustAnchor.runtime_manifest_sha256
$DeploymentManifestSha = [string]$TrustAnchor.deployment_manifest_sha256
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
