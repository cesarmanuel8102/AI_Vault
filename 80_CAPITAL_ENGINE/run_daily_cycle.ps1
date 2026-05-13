$ErrorActionPreference="Stop"
$ROOT="C:\AI_VAULT"
$env:BRAINLAB_ROOT=$ROOT

Write-Host "== Brain Lab Daily Cycle ==" -ForegroundColor Cyan
Write-Host "1) Scoring opportunities..." -ForegroundColor Yellow
python "$ROOT\70_SCORING_ENGINE\opportunity_scoring.py"

Write-Host "2) Show Top 10 opportunities (by score_total)..." -ForegroundColor Yellow
$csv = Import-Csv "$ROOT\60_METRICS\opportunity_scores.csv"
$top = $csv | Sort-Object {[double]$_.score_total} -Descending | Select-Object -First 10 opportunity_id,name,category,score_total,status,time_to_first_dollar_days,capital_required
$top | Format-Table -AutoSize

Write-Host "`nNext:" -ForegroundColor Green
Write-Host " - Add 5-20 opportunities into the CSV (candidate), then rerun this." -ForegroundColor Green
Write-Host " - To commit budget to an experiment: python $ROOT\80_CAPITAL_ENGINE\capital_allocator.py approve EXP-001 50 `"reason`"" -ForegroundColor Green