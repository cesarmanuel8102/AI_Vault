#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\AI_VAULT",
    [string]$AuditorUser = "CodexAuditorV1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedAuditorSid = "S-1-5-21-214160970-1890373857-4055601883-1012"
$ProgramRoot = "C:\ProgramData\CodexAuditorV1"
$RuntimeRoot = Join-Path $ProgramRoot "runtime"
$ProvisioningRoot = Join-Path $ProgramRoot "provisioning"
$ExportRoot = Join-Path $ProgramRoot "exports"
$AuditorReportRoot = Join-Path $ProgramRoot "reports"
$StateReportRoot = Join-Path $RepoRoot "state\ibkr_paper_30d\reports"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "=== $Message ===" -ForegroundColor Cyan
}

function Get-Python {
    $venv = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venv -PathType Leaf) { return $venv }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { $cmd = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $cmd) { throw "PYTHON_NOT_FOUND" }
    return $cmd.Source
}

function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "REQUIRED_FILE_MISSING:$Path"
    }
}

function Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $encoding)
}

if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    throw "REPO_ROOT_NOT_FOUND:$RepoRoot"
}
Set-Location $RepoRoot

Require-File (Join-Path $RepoRoot "AUDITOR_WINDOWS_PROVISIONING_V1.ps1")
Require-File (Join-Path $RepoRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1")
Require-File (Join-Path $RepoRoot "ibkr_paper_30d\cli.py")
Require-File (Join-Path $RepoRoot "auditor_runtime\AUDITOR_GATE_V2_PROBE.ps1")

$Python = Get-Python

Write-Step "Verify Python imports"
& $Python -c "import pydantic, defusedxml, ibapi; import ibkr_paper_30d.cli; print('PYTHON_PREFLIGHT_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "PYTHON_DEPENDENCIES_OR_IMPORT_FAILED"
}

Write-Step "Verify local IBKR Paper Gateway on 127.0.0.1:4002"
$portOpen = Test-NetConnection -ComputerName 127.0.0.1 -Port 4002 -InformationLevel Quiet
if (-not $portOpen) {
    throw "IBKR_PAPER_GATEWAY_4002_NOT_REACHABLE. Open IB Gateway/TWS PAPER, log in, and enable API port 4002."
}

if (-not (Test-Path -LiteralPath $StateReportRoot)) {
    [void](New-Item -ItemType Directory -Path $StateReportRoot -Force)
}

Write-Step "Create fresh real IBKR read-only reconciliation receipt"
& $Python -m ibkr_paper_30d.cli inspect-ibkr-readonly --host 127.0.0.1 --port 4002
if ($LASTEXITCODE -ne 0) { throw "READONLY_RECONCILIATION_COMMAND_FAILED" }

$ReadonlyPath = Join-Path $StateReportRoot "read_only_real_paper_reconciliation.json"
Require-File $ReadonlyPath
$Readonly = Get-Content -LiteralPath $ReadonlyPath -Raw | ConvertFrom-Json
if (
    $Readonly.status -ne "PASS" -or
    $Readonly.paper_account_identity_gate -ne "PASS" -or
    $Readonly.real_ibkr_read_only_identity_gate -ne "PASS" -or
    $Readonly.broker_reconciliation_gate -ne "PASS" -or
    $Readonly.gateway_mode -ne "PAPER" -or
    [int]$Readonly.port -ne 4002
) {
    throw ("READONLY_RECONCILIATION_NOT_PASS:" + (($Readonly.reason_codes | ForEach-Object { [string]$_ }) -join ","))
}

Write-Step "Provision restricted Windows auditor account and ACLs"
& PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "AUDITOR_WINDOWS_PROVISIONING_V1.ps1") -Mode Apply
if ($LASTEXITCODE -ne 0) { throw "AUDITOR_WINDOWS_PROVISIONING_FAILED" }

$Auditor = Get-LocalUser -Name $AuditorUser -ErrorAction Stop
$ActualSid = $Auditor.SID.Value
if ($ActualSid -ne $ExpectedAuditorSid) {
    throw "AUDITOR_SID_MISMATCH: actual=$ActualSid expected=$ExpectedAuditorSid"
}

Write-Step "Install exact Auditor Runtime V2"
& PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1") -Mode Install -ConfirmRuntimeMutation
if ($LASTEXITCODE -ne 0) { throw "AUDITOR_RUNTIME_V2_INSTALL_FAILED" }

$ReviewRaw = & PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1") -Mode Review
if ($LASTEXITCODE -ne 0) { throw "AUDITOR_RUNTIME_V2_REVIEW_FAILED" }
$Review = ($ReviewRaw -join [Environment]::NewLine) | ConvertFrom-Json
if (-not [bool]$Review.INSTALLED_RUNTIME_EXACT) {
    throw "AUDITOR_RUNTIME_V2_NOT_EXACT"
}

$RuntimeManifest = Join-Path $RuntimeRoot "AUDITOR_RUNTIME_MANIFEST_V2.json"
$DeploymentManifest = Join-Path $ProvisioningRoot "AUDITOR_RUNTIME_V2_DEPLOYMENT_MANIFEST.json"
$TargetManifest = Join-Path $ProvisioningRoot "AUDITOR_PROBE_TARGET_MANIFEST_V1.json"
$ProbeScript = Join-Path $RuntimeRoot "AUDITOR_GATE_V2_PROBE.ps1"
Require-File $RuntimeManifest
Require-File $DeploymentManifest
Require-File $TargetManifest
Require-File $ProbeScript

Write-Step "Create immutable audit export bundle"
if (-not (Test-Path -LiteralPath $ExportRoot)) {
    throw "AUDITOR_EXPORT_ROOT_MISSING"
}
$payloadPath = Join-Path $env:TEMP ("codex-auditor-preflight-" + [Guid]::NewGuid().ToString("N") + ".json")
$payload = [ordered]@{
    schema = "CODEX_IBKR_PREFLIGHT_AUDIT_BUNDLE_V1"
    created_at_utc = [DateTime]::UtcNow.ToString("o").Replace("+00:00","Z")
    readonly_receipt_sha256 = Sha256 $ReadonlyPath
    expected_account_identity_hash = [string]$Readonly.expected_account_identity_hash
    repository_root = $RepoRoot
}
Write-Utf8NoBom -Path $payloadPath -Text ($payload | ConvertTo-Json -Depth 5 -Compress)
$pyCode = 'import json,sys; from ibkr_paper_30d.auditor_export import AuditExporter; p=json.load(open(sys.argv[1],encoding="utf-8")); r=AuditExporter(sys.argv[2]).publish({"preflight.json":p}); print(str(r.path))'
$BundlePath = ((& $Python -c $pyCode $payloadPath $ExportRoot) | Select-Object -Last 1).Trim()
Remove-Item -LiteralPath $payloadPath -Force -ErrorAction SilentlyContinue
if (-not (Test-Path -LiteralPath $BundlePath -PathType Container)) {
    throw "AUDIT_BUNDLE_CREATION_FAILED:$BundlePath"
}

Write-Step "Copy paper identity receipt into auditor-readable immutable export area"
$AuditorReadonlyPath = Join-Path $ExportRoot "read_only_real_paper_reconciliation.json"
Copy-Item -LiteralPath $ReadonlyPath -Destination $AuditorReadonlyPath -Force
Require-File $AuditorReadonlyPath

$ExpectedPaperHash = [string]$Readonly.expected_account_identity_hash
if ($ExpectedPaperHash -notmatch '^[0-9a-f]{64}$') {
    throw "EXPECTED_PAPER_ACCOUNT_HASH_INVALID"
}
$DeploymentSha = Sha256 $DeploymentManifest

Write-Step "Run Auditor Gate V2 under restricted non-elevated account"
$SecurePassword = Read-Host -Prompt "Password for local standard account $AuditorUser" -AsSecureString
$Credential = New-Object System.Management.Automation.PSCredential("$env:COMPUTERNAME\$AuditorUser", $SecurePassword)
$nonce = [Guid]::NewGuid().ToString("N")
$StdOut = Join-Path $AuditorReportRoot "gate-v2-$nonce.stdout.txt"
$StdErr = Join-Path $AuditorReportRoot "gate-v2-$nonce.stderr.txt"
$started = Get-Date

$argLine = @(
    '-NoProfile'
    '-ExecutionPolicy Bypass'
    ('-File "{0}"' -f $ProbeScript)
    ('-BundlePath "{0}"' -f $BundlePath)
    ('-PaperIdentityReceiptPath "{0}"' -f $AuditorReadonlyPath)
    ('-TargetManifestPath "{0}"' -f $TargetManifest)
    ('-DeploymentManifestPath "{0}"' -f $DeploymentManifest)
    ('-ExpectedDeploymentManifestSha256 "{0}"' -f $DeploymentSha)
    ('-ExpectedPaperAccountHash "{0}"' -f $ExpectedPaperHash)
    ('-ExpectedSid "{0}"' -f $ActualSid)
    ('-ReportDirectory "{0}"' -f $AuditorReportRoot)
) -join ' '

$Process = Start-Process -FilePath "PowerShell.exe" -ArgumentList $argLine -Credential $Credential -LoadUserProfile -Wait -PassThru -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr
if ($Process.ExitCode -ne 0) {
    $stderrText = if (Test-Path $StdErr) { Get-Content $StdErr -Raw } else { "" }
    throw "AUDITOR_GATE_V2_PROBE_FAILED:exit=$($Process.ExitCode):$stderrText"
}

$Receipt = Get-ChildItem -LiteralPath $AuditorReportRoot -Filter "auditor-gate-v2-*.json" -File |
    Where-Object { $_.LastWriteTime -ge $started.AddSeconds(-5) } |
    Sort-Object LastWriteTime |
    Select-Object -Last 1
if ($null -eq $Receipt) { throw "AUDITOR_GATE_V2_RECEIPT_NOT_FOUND" }

$CanonicalReceiptPath = Join-Path $StateReportRoot "auditor_gate_v2_receipt.json"
Copy-Item -LiteralPath $Receipt.FullName -Destination $CanonicalReceiptPath -Force

Write-Step "Evaluate real Auditor V2 receipt and materialize PASS artifacts"
$env:AUDITOR_RUNTIME_MANIFEST_V2_SHA256 = Sha256 $RuntimeManifest
$env:AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2_SHA256 = Sha256 $DeploymentManifest
$env:AUDITOR_GATE_V2_PROBE_SHA256 = Sha256 $ProbeScript
$env:AUDITOR_PROBE_TARGET_MANIFEST_SHA256 = Sha256 $TargetManifest

$DefaultAcceptance = Join-Path $RepoRoot "AUDITOR_MONTH1_PAPER_RESIDUAL_RISK_ACCEPTANCE_V1.json"
if (Test-Path -LiteralPath $DefaultAcceptance) {
    $AcceptancePath = Join-Path $StateReportRoot ("auditor_month1_acceptance_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".json")
} else {
    $AcceptancePath = $DefaultAcceptance
}
$ArtifactOutput = & $Python -m ibkr_paper_30d.cli write-auditor-v2-artifacts --receipt $CanonicalReceiptPath --report (Join-Path $RepoRoot "AUDITOR_ISOLATION_GATE_V2_REPORT.md") --acceptance $AcceptancePath
if ($LASTEXITCODE -ne 0) { throw "AUDITOR_V2_ARTIFACT_EVALUATION_FAILED" }
$Artifact = ($ArtifactOutput -join [Environment]::NewLine) | ConvertFrom-Json
if ($Artifact.gate -ne "PASS") {
    throw ("AUDITOR_GATE_V2_NOT_PASS:" + (($Artifact.reason_codes | ForEach-Object { [string]$_ }) -join ","))
}

$statusPath = Join-Path $StateReportRoot "auditor_gate_v2_status.json"
$status = [ordered]@{
    schema = "AUDITOR_GATE_V2_STATUS_V1"
    gate = "PASS"
    completed_at_utc = [DateTime]::UtcNow.ToString("o").Replace("+00:00","Z")
    receipt_path = $CanonicalReceiptPath
    receipt_sha256 = Sha256 $CanonicalReceiptPath
    acceptance_path = $AcceptancePath
    expected_auditor_sid = $ActualSid
}
Write-Utf8NoBom -Path $statusPath -Text ($status | ConvertTo-Json -Depth 5 -Compress)

Write-Host ""
Write-Host "AUDITOR GATE V2 = PASS" -ForegroundColor Green
Write-Host "Receipt: $CanonicalReceiptPath"
Write-Host "Status : $statusPath"
Write-Host ""
Write-Host "Next prerequisite: run .\FINALIZE_IBKR_MARKET_DATA.ps1 during a regular US market session (recommended start 09:35-14:30 ET) with IBKR Paper Gateway open." -ForegroundColor Yellow
