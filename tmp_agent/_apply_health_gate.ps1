# R10.2c - Health Gate runner. Detached process, survives brain restart.
# Args:
#   -ProposalId <ce_prop_xxx>     proposal whose backups will be used for rollback
#   -PollSeconds 90               max time to wait for /health=healthy after restart
#   -RespawnWait 50               sleep after kill before first poll
#
# Behavior:
#   1. Reads proposal JSON, captures `backups` dict (abs_path -> .bak path)
#   2. CIM-kills brain (via _kill_cim.ps1 logic inlined)
#   3. Polls /health every 3s for up to PollSeconds
#   4. On healthy: status -> applied_active
#   5. On NOT healthy: restores all files from backups, kills brain again,
#      polls again 60s. Marks status -> rolled_back_auto (or rollback_failed)
#   6. Always writes a log to state/health_gate_logs/<ProposalId>.log

param(
    [Parameter(Mandatory=$true)] [string] $ProposalId,
    [int] $PollSeconds = 90,
    [int] $RespawnWait = 50
)

$ErrorActionPreference = 'Continue'
$ProposalsDir = 'C:/AI_VAULT/tmp_agent/state/proposed_patches'
$LogsDir      = 'C:/AI_VAULT/tmp_agent/state/health_gate_logs'
$ProposalPath = Join-Path $ProposalsDir "$ProposalId.json"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
$LogPath = Join-Path $LogsDir "$ProposalId.log"

function Write-Log($msg) {
    $line = "[$([DateTime]::Now.ToString('o'))] $msg"
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
    Write-Host $line
}

function Set-ProposalStatus($status, $extra) {
    try {
        $raw = [System.IO.File]::ReadAllText($ProposalPath, [System.Text.UTF8Encoding]::new($false))
        $rec = $raw | ConvertFrom-Json
        $rec.status = $status
        if ($extra) {
            foreach ($k in $extra.Keys) {
                if ($rec.PSObject.Properties.Name -contains $k) {
                    $rec.$k = $extra[$k]
                } else {
                    $rec | Add-Member -NotePropertyName $k -NotePropertyValue $extra[$k]
                }
            }
        }
        $json = $rec | ConvertTo-Json -Depth 20
        # Write WITHOUT BOM - default PS Set-Content adds BOM which breaks json.load()
        [System.IO.File]::WriteAllText($ProposalPath, $json, [System.Text.UTF8Encoding]::new($false))
        Write-Log "proposal status -> $status"
    } catch {
        Write-Log "ERROR persisting status=$status : $($_.Exception.Message)"
    }
}

function Kill-Brain {
    $conn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $pid_target = $conn.OwningProcess
        Write-Log "killing brain PID=$pid_target via CIM Terminate"
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pid_target" -ErrorAction SilentlyContinue
        if ($proc) {
            $r = Invoke-CimMethod -InputObject $proc -MethodName Terminate
            Write-Log "terminate ReturnValue=$($r.ReturnValue)"
        } else {
            Write-Log "CIM lookup failed"
        }
    } else {
        Write-Log "no brain on 8090 (already dead?)"
    }
}

function Wait-Healthy([int] $maxSeconds) {
    $deadline = (Get-Date).AddSeconds($maxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/health' -TimeoutSec 5
            if ($h.status -eq 'healthy') {
                $newConn = Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
                $newPid = if ($newConn) { $newConn.OwningProcess } else { 'unknown' }
                return @{ ok = $true; pid = $newPid; safe_mode = $h.safe_mode }
            }
        } catch {
            # keep polling
        }
        Start-Sleep 3
    }
    return @{ ok = $false }
}

function Cleanup-Task {
    $taskName = "BrainHealthGate_$ProposalId"
    try {
        schtasks.exe /Delete /TN $taskName /F 2>&1 | Out-Null
        Write-Log "scheduled task $taskName deleted"
    } catch {
        Write-Log "task delete failed (non-fatal): $($_.Exception.Message)"
    }
}

Write-Log "=== R10.2c health gate START proposal=$ProposalId pollSeconds=$PollSeconds ==="

if (-not (Test-Path $ProposalPath)) {
    Write-Log "ABORT: proposal file not found: $ProposalPath"
    Cleanup-Task
    exit 1
}

$rec = ([System.IO.File]::ReadAllText($ProposalPath, [System.Text.UTF8Encoding]::new($false))) | ConvertFrom-Json
$backups = @{}
if ($rec.backups) {
    $rec.backups.PSObject.Properties | ForEach-Object { $backups[$_.Name] = $_.Value }
}
Write-Log "backups: $($backups.Count) entries"
foreach ($k in $backups.Keys) { Write-Log "  $k -> $($backups[$k])" }

if ($backups.Count -eq 0) {
    Write-Log "ABORT: no backups recorded - cannot guarantee rollback"
    Set-ProposalStatus 'health_gate_aborted' @{ health_gate_error = 'no_backups' }
    Cleanup-Task
    exit 2
}

# Phase 1: kill + wait + poll
Kill-Brain
Write-Log "sleeping $RespawnWait s for watchdog initial respawn"
Start-Sleep $RespawnWait

$result = Wait-Healthy $PollSeconds
if ($result.ok) {
    Write-Log "HEALTHY after restart pid=$($result.pid) safe_mode=$($result.safe_mode)"
    Set-ProposalStatus 'applied_active' @{
        health_gate_pid = "$($result.pid)"
        health_gate_completed_at = ([DateTime]::Now).ToString('o')
    }
    Write-Log "=== R10.2c health gate SUCCESS ==="
    Cleanup-Task
    exit 0
}

# Phase 2: NOT healthy -> rollback
Write-Log "NOT healthy after $PollSeconds s -> initiating AUTO-ROLLBACK"
$restored = @()
$failed   = @()
foreach ($abs in $backups.Keys) {
    $bkp = $backups[$abs]
    if (-not (Test-Path $bkp)) {
        $failed += @{ file = $abs; reason = 'backup_missing' }
        Write-Log "ERROR backup missing: $bkp"
        continue
    }
    try {
        Copy-Item -Path $bkp -Destination $abs -Force
        $restored += $abs
        Write-Log "restored: $abs"
    } catch {
        $failed += @{ file = $abs; reason = $_.Exception.Message }
        Write-Log "ERROR restore $abs : $($_.Exception.Message)"
    }
}

# Restart brain again to pick up rollback
Write-Log "killing brain again to load rolled-back files"
Kill-Brain
Start-Sleep $RespawnWait
$post = Wait-Healthy 60

if ($post.ok) {
    Write-Log "HEALTHY after rollback pid=$($post.pid)"
    Set-ProposalStatus 'rolled_back_auto' @{
        rolled_back_at = ([DateTime]::Now).ToString('o')
        rollback_reason = "health_gate_failed after ${PollSeconds}s"
        rollback_restored = $restored
        rollback_failed   = $failed
        health_gate_post_rollback_pid = "$($post.pid)"
    }
    Write-Log "=== R10.2c health gate AUTO-ROLLBACK SUCCESS ==="
    Cleanup-Task
    exit 3
} else {
    Write-Log "CRITICAL: brain still NOT healthy after rollback"
    Set-ProposalStatus 'rollback_failed' @{
        rollback_reason = "health_gate_failed AND post-rollback restart failed"
        rollback_restored = $restored
        rollback_failed   = $failed
    }
    Write-Log "=== R10.2c health gate ROLLBACK FAILED - MANUAL INTERVENTION ==="
    Cleanup-Task
    exit 4
}
