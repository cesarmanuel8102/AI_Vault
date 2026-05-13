$ErrorActionPreference="Stop"
$ROOT="C:\AI_VAULT"

Write-Host "== Commit Initial Budgets ==" -ForegroundColor Cyan

# EXP-A (OPP-003)
python "$ROOT\80_CAPITAL_ENGINE\capital_allocator.py" approve EXP-A 50 "OPP-003 Excel data cleanup MVP: templates + first client proof"

# EXP-B (OPP-014)
python "$ROOT\80_CAPITAL_ENGINE\capital_allocator.py" approve EXP-B 50 "OPP-014 Weekly automated reporting B2B: pilot acquisition + recurring offer"

# EXP-C (OPP-016/018)
python "$ROOT\80_CAPITAL_ENGINE\capital_allocator.py" approve EXP-C 25 "OPP-016/018 Automation backbone: daily capture + scoring + logging"

Write-Host "`n== Run Daily Cycle ==" -ForegroundColor Cyan
powershell -NoProfile -ExecutionPolicy Bypass -File "$ROOT\80_CAPITAL_ENGINE\run_daily_cycle.ps1"

Write-Host "`n== Capital State ==" -ForegroundColor Cyan
type "$ROOT\60_METRICS\capital_state.json"

Write-Host "`nOK: budgets committed and logged." -ForegroundColor Green