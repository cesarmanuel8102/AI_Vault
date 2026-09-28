#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$ApprovedHead,
    [string]$PythonExe = "python",
    [string]$PowerShellExe = "powershell.exe",
    [string]$TaskName = "CodexIBKRMarketDataGate",
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ResolvedRepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\')
$ApprovedRepoRoot = [IO.Path]::GetFullPath("C:\AI_VAULT_IBKR").TrimEnd('\')
if ($ApprovedHead -notmatch '^[0-9a-fA-F]{40}$') {
    throw "APPROVED_HEAD_INVALID"
}
$ApprovedHead = $ApprovedHead.ToLowerInvariant()
if ($ResolvedRepoRoot -ine $ApprovedRepoRoot -and -not $ValidateOnly) {
    throw "REPO_ROOT_NOT_APPROVED:$ResolvedRepoRoot"
}
Set-Location -LiteralPath $ResolvedRepoRoot
$CurrentHead = ([string]((& git -C $ResolvedRepoRoot rev-parse HEAD 2>$null) | Select-Object -First 1)).Trim().ToLowerInvariant()
if (-not $ValidateOnly -and $CurrentHead -ne $ApprovedHead) {
    throw "APPROVED_HEAD_MISMATCH:EXPECTED=$ApprovedHead:ACTUAL=$CurrentHead"
}
$Finalizer = Join-Path $ResolvedRepoRoot "FINALIZE_IBKR_PREREQUISITES.ps1"
$LaunchAttemptId = [guid]::NewGuid().ToString("D")
$FinalizerArguments = @(
    "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Finalizer,
    "-RepoRoot", $ResolvedRepoRoot,
    "-PythonExe", $PythonExe,
    "-Stage", "Receipts",
    "-ConfirmStage",
    "-SkipTaskRegistration",
    "-LaunchAttemptId", $LaunchAttemptId
)
$PythonArguments = @(
    "-m", "ibkr_paper_30d.day1_launch",
    "--repo-root", $ResolvedRepoRoot,
    "--launch-attempt-id", $LaunchAttemptId
)

if ($ValidateOnly) {
    $TaskSnapshot = [ordered]@{
        task_name = $TaskName
        exists = $false
        enabled = $false
        execute = ""
        arguments = ""
        user_id = ""
        user_sid = ""
        logon_type = ""
        run_level = ""
        multiple_instances = ""
        working_directory = ""
        restart_count = 0
        restart_interval_minutes = 0
        weekly_days = @()
        weekly_start = ""
        logon_users = @()
        logon_user_sids = @()
    }
    try {
        $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        $Action = @($Task.Actions) | Select-Object -First 1
        $WeeklyDays = New-Object System.Collections.Generic.List[string]
        $WeeklyStart = ""
        $LogonUsers = New-Object System.Collections.Generic.List[string]
        $LogonUserSids = New-Object System.Collections.Generic.List[string]
        foreach ($Trigger in @($Task.Triggers)) {
            if ($null -ne $Trigger.PSObject.Properties["DaysOfWeek"] -and [string]$Trigger.DaysOfWeek) {
                $DayMask = 0
                if ([int]::TryParse([string]$Trigger.DaysOfWeek, [ref]$DayMask)) {
                    foreach ($DayFlag in @(
                        @{ Name = "Sunday"; Value = 1 },
                        @{ Name = "Monday"; Value = 2 },
                        @{ Name = "Tuesday"; Value = 4 },
                        @{ Name = "Wednesday"; Value = 8 },
                        @{ Name = "Thursday"; Value = 16 },
                        @{ Name = "Friday"; Value = 32 },
                        @{ Name = "Saturday"; Value = 64 }
                    )) {
                        if (($DayMask -band $DayFlag.Value) -ne 0) { $WeeklyDays.Add($DayFlag.Name) }
                    }
                }
                else {
                    foreach ($Day in ([string]$Trigger.DaysOfWeek -split ',')) {
                        $WeeklyDays.Add($Day.Trim())
                    }
                }
                if ($null -ne $Trigger.PSObject.Properties["StartBoundary"] -and [string]$Trigger.StartBoundary) {
                    try { $WeeklyStart = ([DateTime]$Trigger.StartBoundary).ToString("HH:mm") } catch { }
                }
            }
            if ($null -ne $Trigger.PSObject.Properties["UserId"] -and [string]$Trigger.UserId) {
                $TriggerUser = [string]$Trigger.UserId
                $LogonUsers.Add($TriggerUser)
                try {
                    $TriggerSid = ([Security.Principal.NTAccount]$TriggerUser).Translate(
                        [Security.Principal.SecurityIdentifier]
                    ).Value
                    $LogonUserSids.Add($TriggerSid)
                }
                catch { }
            }
        }
        $RestartMinutes = 0
        if ($null -ne $Task.Settings.PSObject.Properties["RestartInterval"] -and [string]$Task.Settings.RestartInterval) {
            try { $RestartMinutes = [int][Xml.XmlConvert]::ToTimeSpan([string]$Task.Settings.RestartInterval).TotalMinutes } catch { }
        }
        $TaskUserSid = ""
        try {
            $TaskUserSid = ([Security.Principal.NTAccount]([string]$Task.Principal.UserId)).Translate(
                [Security.Principal.SecurityIdentifier]
            ).Value
        }
        catch { }
        $TaskSnapshot = [ordered]@{
            task_name = [string]$Task.TaskName
            exists = $true
            enabled = ([string]$Task.State -ne "Disabled")
            execute = [string]$Action.Execute
            arguments = [string]$Action.Arguments
            user_id = [string]$Task.Principal.UserId
            user_sid = $TaskUserSid
            logon_type = [string]$Task.Principal.LogonType
            run_level = [string]$Task.Principal.RunLevel
            multiple_instances = [string]$Task.Settings.MultipleInstances
            working_directory = [string]$Action.WorkingDirectory
            restart_count = [int]$Task.Settings.RestartCount
            restart_interval_minutes = $RestartMinutes
            weekly_days = @($WeeklyDays)
            weekly_start = $WeeklyStart
            logon_users = @($LogonUsers)
            logon_user_sids = @($LogonUserSids)
        }
    }
    catch { }
    $TaskJson = $TaskSnapshot | ConvertTo-Json -Depth 6 -Compress
    $TaskBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($TaskJson))
    $OwnerIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $OwnerUser = $OwnerIdentity.Name
    $OwnerSid = $OwnerIdentity.User.Value
    $ValidationOutput = @(& $PythonExe -B -m ibkr_paper_30d.scheduler_validation `
        --repo-root $ResolvedRepoRoot `
        --approved-head $ApprovedHead `
        --expected-repo-root $ApprovedRepoRoot `
        --expected-owner $OwnerUser `
        --expected-owner-sid $OwnerSid `
        --task-name $TaskName `
        --task-snapshot-base64 $TaskBase64 `
        --require-frozen 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "SCHEDULER_VALIDATION_COMMAND_FAILED:$($ValidationOutput -join ' | ')"
    }
    $ValidationCandidates = @($ValidationOutput | Where-Object { ([string]$_).TrimStart().StartsWith("{") })
    if ($ValidationCandidates.Count -eq 0) {
        throw "SCHEDULER_VALIDATION_JSON_MISSING"
    }
    $SchedulerValidation = [string]$ValidationCandidates[-1] | ConvertFrom-Json
    [ordered]@{
        launch_attempt_id = $LaunchAttemptId
        finalizer_arguments = $FinalizerArguments
        python_arguments = $PythonArguments
        scheduler_validation = $SchedulerValidation
        foreground = $true
        broker_write_calls = 0
        mutations_performed = 0
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
