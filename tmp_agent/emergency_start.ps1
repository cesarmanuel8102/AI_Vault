# emergency_start.ps1 — Canonical AI_VAULT startup script
# Starts: Ollama (LLM backend) + Brain V9 (API + Dashboard at :8090/ui)
#
# Usage:  Right-click → Run with PowerShell   (or:  powershell -File emergency_start.ps1)
# Stop:   Ctrl+C  (or close this window)
#
# The dashboard is built into Brain V9 at http://127.0.0.1:8090/ui
# There is NO separate dashboard process — port 8070 is retired.

$ErrorActionPreference = "Continue"

# ── Configuration ──────────────────────────────────────────────
$BASE_DIR       = "C:\AI_VAULT\tmp_agent"
$BRAIN_PORT     = 8090
$OLLAMA_PORT    = 11434
$HEALTH_URL     = "http://127.0.0.1:${BRAIN_PORT}/health"
$OLLAMA_URL     = "http://127.0.0.1:${OLLAMA_PORT}/api/tags"
$STARTUP_WAIT   = 12          # seconds to wait after launching Brain V9
$LOOP_INTERVAL  = 30          # seconds between health checks
$MAX_RESTARTS   = 5           # max consecutive restart attempts before giving up
$RESTART_WINDOW = 300         # reset restart counter after this many seconds of healthy uptime

# ── Functions ──────────────────────────────────────────────────

function Write-Banner {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "   AI_VAULT — Emergency Start" -ForegroundColor Cyan
    Write-Host "   $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
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
    # Kill processes listening on a specific port (surgical, not all python)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        $pid = $conn.OwningProcess
        if ($pid -and $pid -ne 0) {
            Write-Host "  Stopping PID $pid on port $Port" -ForegroundColor Gray
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-Ollama {
    Write-Host "[Ollama] Checking..." -ForegroundColor Yellow
    if (Test-Port $OLLAMA_PORT) {
        Write-Host "[Ollama] Already running on port $OLLAMA_PORT" -ForegroundColor Green
        return
    }
    # Try to find ollama in PATH
    $ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaPath) {
        Write-Host "[Ollama] Not found in PATH — skipping (Brain V9 will retry on demand)" -ForegroundColor DarkYellow
        return
    }
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Minimized -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    if (Test-Port $OLLAMA_PORT) {
        Write-Host "[Ollama] Started on port $OLLAMA_PORT" -ForegroundColor Green
    } else {
        Write-Host "[Ollama] Started but port not yet listening (may need more time)" -ForegroundColor DarkYellow
    }
}

function Start-BrainV9 {
    Write-Host "[Brain V9] Launching..." -ForegroundColor Yellow

    # Clean up any leftover process on port 8090
    if (Test-Port $BRAIN_PORT) {
        Write-Host "[Brain V9] Port $BRAIN_PORT in use — stopping old process" -ForegroundColor DarkYellow
        Stop-PortProcess $BRAIN_PORT
        Start-Sleep -Seconds 2
    }

    $script:brainJob = Start-Job -ScriptBlock {
        param($dir)
        Set-Location $dir
        $env:PYTHONPATH = $dir
        python -m brain_v9.main 2>&1
    } -ArgumentList $BASE_DIR

    Write-Host "[Brain V9] Job started (ID: $($script:brainJob.Id)) — waiting ${STARTUP_WAIT}s..." -ForegroundColor Gray
    Start-Sleep -Seconds $STARTUP_WAIT
}

function Test-BrainHealth {
    try {
        $resp = Invoke-RestMethod -Uri $HEALTH_URL -Method GET -TimeoutSec 5
        return $true
    } catch {
        return $false
    }
}

# ── Main ───────────────────────────────────────────────────────

Write-Banner

# Step 1: Ollama
Start-Ollama
Write-Host ""

# Step 2: Brain V9
Start-BrainV9

# Step 3: Verify
Write-Host ""
Write-Host "[Verify] Checking services..." -ForegroundColor Yellow

if (Test-BrainHealth) {
    Write-Host "[Brain V9] HEALTHY on http://127.0.0.1:${BRAIN_PORT}" -ForegroundColor Green
    Write-Host "[Dashboard] Available at http://127.0.0.1:${BRAIN_PORT}/ui" -ForegroundColor Green
} else {
    Write-Host "[Brain V9] NOT RESPONDING — will retry in monitoring loop" -ForegroundColor Red
}

if (Test-Port $OLLAMA_PORT) {
    Write-Host "[Ollama] RUNNING on http://127.0.0.1:${OLLAMA_PORT}" -ForegroundColor Green
} else {
    Write-Host "[Ollama] Not confirmed (non-critical)" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Monitoring active — Ctrl+C to stop" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 4: Health-check loop with auto-restart
$restartCount   = 0
$lastHealthy    = Get-Date

while ($true) {
    Start-Sleep -Seconds $LOOP_INTERVAL

    $ts = Get-Date -Format 'HH:mm:ss'

    # Check Brain V9 job state
    $jobState = (Get-Job -Id $script:brainJob.Id -ErrorAction SilentlyContinue).State

    if ($jobState -eq "Completed" -or $jobState -eq "Failed" -or $jobState -eq "Stopped") {
        Write-Host "[$ts] Brain V9 job $jobState — attempting restart ($restartCount/$MAX_RESTARTS)" -ForegroundColor Red

        if ($restartCount -ge $MAX_RESTARTS) {
            Write-Host "[$ts] Max restarts reached. Manual intervention required." -ForegroundColor Red
            Write-Host "       Check logs:  Receive-Job -Id $($script:brainJob.Id)" -ForegroundColor Gray
            break
        }

        # Dump last output for diagnostics
        $output = Receive-Job -Id $script:brainJob.Id -ErrorAction SilentlyContinue
        if ($output) {
            Write-Host "[$ts] Last output:" -ForegroundColor Gray
            $output | Select-Object -Last 5 | ForEach-Object { Write-Host "       $_" -ForegroundColor Gray }
        }

        Remove-Job -Id $script:brainJob.Id -Force -ErrorAction SilentlyContinue
        Start-BrainV9
        $restartCount++
        continue
    }

    # Health endpoint check
    if (Test-BrainHealth) {
        # Reset restart counter after sustained healthy uptime
        $elapsed = (Get-Date) - $lastHealthy
        if ($elapsed.TotalSeconds -lt $LOOP_INTERVAL * 2) {
            # Consecutive healthy check
            if ($restartCount -gt 0 -and ((Get-Date) - $lastHealthy).TotalSeconds -gt $RESTART_WINDOW) {
                $restartCount = 0
            }
        }
        $lastHealthy = Get-Date
    } else {
        Write-Host "[$ts] Health check failed (job state: $jobState)" -ForegroundColor DarkYellow
    }
}
