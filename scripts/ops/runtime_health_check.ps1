# Runtime Health Check for Brain Lab
# FRONT-RUNTIME-RECOVERY-REAL-EXECUTION-GATE-01
# Usage: .\scripts\ops\runtime_health_check.ps1
# Non-destructive diagnostic only.

param(
    [int]$BrainPort = 8090,
    [int]$DashboardPort = 3000,
    [int]$OllamaPort = 11434,
    [int]$TimeoutSeconds = 5
)

$results = @{}
$all_ok = $true

function Test-Endpoint($name, $url) {
    try {
        $response = Invoke-WebRequest -Uri $url -Method GET -TimeoutSec $TimeoutSeconds -UseBasicParsing -ErrorAction Stop
        $status = $response.StatusCode
        if ($status -eq 200) {
            Write-Host "[OK] $name -> $url (HTTP $status)" -ForegroundColor Green
            return $true
        } else {
            Write-Host "[WARN] $name -> $url (HTTP $status)" -ForegroundColor Yellow
            return $false
        }
    } catch {
        Write-Host "[FAIL] $name -> $url ($($_.Exception.Message))" -ForegroundColor Red
        return $false
    }
}

Write-Host "=== Brain Lab Runtime Health Check ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format o)"
Write-Host ""

# Ollama
$results["ollama"] = Test-Endpoint "Ollama API" "http://127.0.0.1:$OllamaPort/api/tags"

# Brain V9 Server
$results["brain_server_health"] = Test-Endpoint "Brain Server Health" "http://127.0.0.1:$BrainPort/health"
$results["brain_server_dashboard"] = Test-Endpoint "Brain Server Dashboard" "http://127.0.0.1:$BrainPort/dashboard"

# Open WebUI / Dashboard
$results["dashboard"] = Test-Endpoint "Open WebUI / Dashboard" "http://127.0.0.1:$DashboardPort"

# Git checks
Write-Host ""
Write-Host "=== Git Checks ===" -ForegroundColor Cyan

$gitStatus = git status --short 2>$null
if ($LASTEXITCODE -eq 0 -and [string]::IsNullOrWhiteSpace($gitStatus)) {
    Write-Host "[OK] Git working tree clean" -ForegroundColor Green
    $results["git_clean"] = $true
} else {
    Write-Host "[WARN] Git working tree has changes" -ForegroundColor Yellow
    Write-Host $gitStatus
    $results["git_clean"] = $false
}

# ROADMAP validation
Write-Host ""
Write-Host "=== ROADMAP Validation ===" -ForegroundColor Cyan
try {
    $roadmap = Get-Content "ROADMAP_STATUS.json" -Raw | ConvertFrom-Json -ErrorAction Stop
    Write-Host "[OK] ROADMAP_STATUS.json valid JSON" -ForegroundColor Green
    $results["roadmap_valid"] = $true
} catch {
    Write-Host "[FAIL] ROADMAP_STATUS.json invalid JSON: $($_.Exception.Message)" -ForegroundColor Red
    $results["roadmap_valid"] = $false
}

# Summary
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
foreach ($key in $results.Keys) {
    if ($results[$key] -eq $false) {
        $all_ok = $false
        Write-Host "  $key : FAIL" -ForegroundColor Red
    } else {
        Write-Host "  $key : OK" -ForegroundColor Green
    }
}

Write-Host ""
if ($all_ok) {
    Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "SOME CHECKS FAILED" -ForegroundColor Red
    exit 1
}
