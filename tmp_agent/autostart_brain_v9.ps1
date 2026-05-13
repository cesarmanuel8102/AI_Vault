# autostart_brain_v9.ps1 - Auto-start + Watchdog for Brain V9
# Designed to run as a Windows Scheduled Task (at logon)
# Launches Brain V9 as a real process, monitors health, auto-restarts on failure.
# Logs to file since there's no console in scheduled task mode.
#
# KEY BEHAVIOR:
# - If Brain V9 is ALREADY healthy at startup, skips launch and enters watchdog mode
# - Only kills/restarts if health check fails
# - Uses timestamped log files to avoid file-lock conflicts
#
# Registered as: AI_VAULT_BrainV9_AutoStart

$ErrorActionPreference = "Continue"

# -- Configuration --
$BASE_DIR       = "C:\AI_VAULT\tmp_agent"
$BRAIN_PORT     = 8090
$OLLAMA_PORT    = 11434
$HEALTH_URL     = "http://127.0.0.1:$BRAIN_PORT/health"
$LOG_FILE       = "$BASE_DIR\autostart_watchdog.log"
$STARTUP_WAIT   = 30          # seconds to wait after launching (HMM + IBKR take time)
$LOOP_INTERVAL  = 30          # seconds between health checks (R3.1: faster detection)
$MAX_RESTARTS   = 10          # max consecutive restart attempts before long backoff
$BACKOFF_SLEEP  = 600         # 10 min sleep after max restarts, then retry

# DEV_MODE: relax watchdog for iterative development sessions.
# Activate with $env:BRAIN_DEV_MODE='true' before launching this script.
if ($env:BRAIN_DEV_MODE -eq 'true') {
    $MAX_RESTARTS  = 50
    $BACKOFF_SLEEP = 30
    Write-Host "[Watchdog] BRAIN_DEV_MODE=true -> max_restarts=$MAX_RESTARTS backoff=$BACKOFF_SLEEP"
}
$STARTUP_DELAY  = 45          # delay before first launch (let Windows finish booting)

# God-mode env vars: ALWAYS set them so any restart preserves dev capabilities.
# Without these, the watchdog relaunches in safe_mode (god mode lost).
$env:BRAIN_SAFE_MODE = 'false'
$env:BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS = 'true'
$env:BRAIN_CHAT_DEV_MODE = 'true'
if (-not $env:PAD_MFA_TEST_OVERRIDE) { $env:PAD_MFA_TEST_OVERRIDE = 'test_pad_2026' }

# Autonomy loops: explicitly enable so brain runs in full autonomous mode.
# Without these flags, gates `if BRAIN_START_X and not BRAIN_SAFE_MODE` evaluate to false
# even when safe_mode=false, causing misleading "[SAFE] X no iniciado" log lines.
$env:BRAIN_START_AUTONOMY = 'true'
$env:BRAIN_START_PROACTIVE = 'true'
$env:BRAIN_START_SELF_DIAGNOSTIC = 'true'
$env:BRAIN_START_QC_LIVE_MONITOR = 'true'
$env:BRAIN_WARMUP_MODEL = 'true'
$env:LLM_TIMEOUT = '240'
$env:LLM_AGENT_TIMEOUT = '300'

# R27: enable autonomous self-development (auto-install of missing tools).
# SELF_DEV_ENABLED=1 + REQUIRE_APPROVAL=0 lets capability_governor execute install_package
# without manual /approve. MAX_RISK=0.4 keeps us under P2 boundary.
$env:SELF_DEV_ENABLED = '1'
$env:SELF_DEV_REQUIRE_APPROVAL = '0'
if (-not $env:SELF_DEV_MAX_RISK) { $env:SELF_DEV_MAX_RISK = '0.4' }

# -- Functions --

function Write-Log([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$ts] $msg"
    Add-Content -Path $LOG_FILE -Value $line -ErrorAction SilentlyContinue
}

function Test-Port([int]$Port) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", $Port)
        $tcp.Close()
        return $true
    } catch {
        return $false
    }
}

function Stop-PortProcess([int]$Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        $procId = $conn.OwningProcess
        if ($procId -and $procId -ne 0) {
            Write-Log "Stopping PID $procId on port $Port"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-Ollama {
    if (Test-Port $OLLAMA_PORT) {
        Write-Log "[Ollama] Already running on port $OLLAMA_PORT"
        return
    }
    $ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaPath) {
        Write-Log "[Ollama] Not found in PATH, skipping"
        return
    }
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    if (Test-Port $OLLAMA_PORT) {
        Write-Log "[Ollama] Started successfully"
    } else {
        Write-Log "[Ollama] Started but port not yet listening"
    }
}

function Test-BrainHealth {
    try {
        # Bumped from 5s -> 20s so heavy queries don't trigger false unhealthy
        $resp = Invoke-WebRequest -Uri $HEALTH_URL -UseBasicParsing -TimeoutSec 20
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Start-BrainV9 {
    # CRITICAL: If Brain V9 is already healthy, do NOT kill it
    if (Test-BrainHealth) {
        Write-Log "[Brain V9] Already healthy on port $BRAIN_PORT - skipping launch"
        # Find the existing PID for watchdog tracking
        $conn = Get-NetTCPConnection -LocalPort $BRAIN_PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) {
            $script:brainPid = $conn.OwningProcess
            Write-Log "[Brain V9] Tracking existing PID $($script:brainPid)"
        }
        return
    }

    # Kill any zombie process on port 8090 that isn't responding to health
    if (Test-Port $BRAIN_PORT) {
        Write-Log "[Brain V9] Port $BRAIN_PORT occupied but unhealthy - killing"
        Stop-PortProcess $BRAIN_PORT
        Start-Sleep -Seconds 3
    }

    # Use timestamped log files to avoid lock conflicts
    $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
    $stderrLog = "$BASE_DIR\logs\brain_v9_stderr_$ts.log"
    $stdoutLog = "$BASE_DIR\logs\brain_v9_stdout_$ts.log"

    # Ensure logs directory exists
    New-Item -ItemType Directory -Path "$BASE_DIR\logs" -Force -ErrorAction SilentlyContinue | Out-Null

    $proc = Start-Process python `
        -ArgumentList "-m", "brain_v9.main" `
        -WorkingDirectory $BASE_DIR `
        -RedirectStandardError $stderrLog `
        -RedirectStandardOutput $stdoutLog `
        -WindowStyle Hidden `
        -PassThru

    if ($proc) {
        $script:brainPid = $proc.Id
        Write-Log "[Brain V9] Launched PID $($proc.Id), waiting $($STARTUP_WAIT) seconds"
        Write-Log "[Brain V9] Logs: stderr=$stderrLog"
    } else {
        $script:brainPid = $null
        Write-Log "[Brain V9] FAILED to launch process"
    }

    Start-Sleep -Seconds $STARTUP_WAIT
}

function Test-BrainProcessAlive {
    if (-not $script:brainPid) { return $false }
    $proc = Get-Process -Id $script:brainPid -ErrorAction SilentlyContinue
    return ($null -ne $proc)
}

# -- Main --

Write-Log "========================================="
Write-Log "AI_VAULT AutoStart Watchdog - STARTING"
Write-Log "========================================="

# Delay to let Windows finish booting (skip if Brain V9 already up)
if (Test-BrainHealth) {
    Write-Log "[Brain V9] Already healthy - skipping boot delay and launch"
    # Track existing PID
    $conn = Get-NetTCPConnection -LocalPort $BRAIN_PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $script:brainPid = $conn.OwningProcess
        Write-Log "[Brain V9] Tracking existing PID $($script:brainPid)"
    }
} else {
    Write-Log "Waiting $($STARTUP_DELAY) seconds for system boot to settle..."
    Start-Sleep -Seconds $STARTUP_DELAY

    # Start Ollama
    Start-Ollama

    # Start Brain V9
    Start-BrainV9

    # Initial health check
    if (Test-BrainHealth) {
        Write-Log "[Brain V9] HEALTHY after initial launch"
    } else {
        Write-Log "[Brain V9] Not healthy after initial launch, watchdog will retry"
    }
}

# -- Watchdog Loop --
$restartCount    = 0
$lastHealthyTime = Get-Date
$consecutiveUnhealthy = 0
$UNHEALTHY_THRESHOLD = 4  # require N consecutive failures before restarting

Write-Log "Entering watchdog loop (interval=$($LOOP_INTERVAL) sec, max_restarts=$MAX_RESTARTS, unhealthy_threshold=$UNHEALTHY_THRESHOLD)"

while ($true) {
    Start-Sleep -Seconds $LOOP_INTERVAL

    $processAlive = Test-BrainProcessAlive
    $isHealthy    = Test-BrainHealth

    if ($isHealthy) {
        $consecutiveUnhealthy = 0
        # Healthy - reset restart counter after sustained uptime (5 min)
        $uptimeSec = ((Get-Date) - $lastHealthyTime).TotalSeconds
        if ($restartCount -gt 0 -and $uptimeSec -gt 300) {
            Write-Log "[Watchdog] Healthy for 5+ min, resetting restart counter ($restartCount -> 0)"
            $restartCount = 0
        }
        $lastHealthyTime = Get-Date
        continue
    }

    # Not healthy - but tolerate transient blips (heavy queries, GC pauses)
    $consecutiveUnhealthy++
    Write-Log "[Watchdog] Health check failed ($consecutiveUnhealthy of $UNHEALTHY_THRESHOLD), process_alive=$processAlive"

    if ($processAlive -and $consecutiveUnhealthy -lt $UNHEALTHY_THRESHOLD) {
        Write-Log "[Watchdog] Process alive, likely busy with heavy query - waiting one more cycle"
        continue
    }

    # Confirmed unhealthy
    Write-Log "[Watchdog] CONFIRMED UNHEALTHY - process_alive=$processAlive, restart_count=$restartCount of $MAX_RESTARTS"
    $consecutiveUnhealthy = 0

    if ($restartCount -ge $MAX_RESTARTS) {
        Write-Log "[Watchdog] Max restarts hit. Backing off $($BACKOFF_SLEEP) seconds before retrying."
        Start-Sleep -Seconds $BACKOFF_SLEEP
        $restartCount = 0
        Write-Log "[Watchdog] Backoff complete. Retrying."
    }

    # Restart
    Write-Log "[Watchdog] Restarting Brain V9 (attempt $($restartCount + 1) of $MAX_RESTARTS)"
    Start-BrainV9

    if (Test-BrainHealth) {
        Write-Log "[Watchdog] Brain V9 recovered after restart"
        $lastHealthyTime = Get-Date
    } else {
        Write-Log "[Watchdog] Brain V9 still unhealthy after restart"
    }

    $restartCount++
}
