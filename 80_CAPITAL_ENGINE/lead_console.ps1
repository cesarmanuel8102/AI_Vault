param()
$ErrorActionPreference="Stop"
$ROOT="C:\AI_VAULT"
$env:BRAINLAB_ROOT=$ROOT

$LEADS="$ROOT\60_METRICS\leads.csv"
$MARK="$ROOT\70_SCORING_ENGINE\mark_lead.py"
$OUTDIR="$ROOT\50_LOGS\weekly_reports"
$today = Get-Date -Format "yyyy-MM-dd"
$targets = Join-Path $OUTDIR ("today_targets_{0}.md" -f $today)

if(!(Test-Path $LEADS)){ Write-Host "Missing: $LEADS" -ForegroundColor Red; exit 1 }
if(!(Test-Path $MARK)){ Write-Host "Missing: $MARK" -ForegroundColor Red; exit 2 }

Write-Host "== Lead Console ==" -ForegroundColor Cyan
Write-Host "Leads:   $LEADS" -ForegroundColor DarkGray
Write-Host "Targets: $targets" -ForegroundColor DarkGray
Write-Host ""

if(Test-Path $targets){
  Write-Host "Opening targets file..." -ForegroundColor Yellow
  Start-Process notepad $targets | Out-Null
}else{
  Write-Host "Targets file not found for today. Run daily_targets.py first." -ForegroundColor Yellow
}

function Show-Queued {
  $rows = Import-Csv $LEADS
  $q = $rows | Where-Object { $_.status -eq "queued" } |
    Select-Object -First 20 lead_id,company,city,email_or_handle,validated,source,status
  if($q){
    Write-Host "`nQueued (top 20):" -ForegroundColor Cyan
    $q | Format-Table -AutoSize
  }else{
    Write-Host "`nNo queued leads right now." -ForegroundColor Yellow
  }
}

function Summary {
  $rows = Import-Csv $LEADS
  $rows | Group-Object status | Sort-Object Count -Descending |
    Select-Object Name,Count | Format-Table -AutoSize
}

Show-Queued
Write-Host "`nAllowed statuses: new queued sent replied won lost dead no_reply followup" -ForegroundColor DarkGray
Write-Host "Tip: Press Enter with empty LeadId to exit." -ForegroundColor DarkGray

while($true){
  $lead = Read-Host "`nLeadId"
  if([string]::IsNullOrWhiteSpace($lead)){ break }

  $status = Read-Host "Status"
  if([string]::IsNullOrWhiteSpace($status)){ $status="sent" }

  $note = Read-Host "Note (optional)"
  if($null -eq $note){ $note="" }

  try{
    python $MARK $lead $status $note
    Write-Host "OK marked." -ForegroundColor Green
  }catch{
    Write-Host "ERR: $($_.Exception.Message)" -ForegroundColor Red
  }

  Show-Queued
}

Write-Host "`n== Status Summary ==" -ForegroundColor Cyan
Summary
Write-Host "`nDone." -ForegroundColor Green