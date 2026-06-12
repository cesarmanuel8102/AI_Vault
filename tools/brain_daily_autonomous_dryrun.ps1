param(
    [int]$Cycles = 3
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
    $env:PYTHONPATH = "$root;$root\tmp_agent"
    python -m tmp_agent.brain_v9.operations.daily_autonomy_dryrun
} finally {
    Pop-Location
}
