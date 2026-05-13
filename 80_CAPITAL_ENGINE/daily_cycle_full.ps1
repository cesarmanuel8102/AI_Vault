$ErrorActionPreference="Stop"
$ROOT="C:\AI_VAULT"
$env:BRAINLAB_ROOT=$ROOT

$HARVEST_PY="$ROOT\70_SCORING_ENGINE\lead_harvester_osm.py"
$TARGETS_PY="$ROOT\70_SCORING_ENGINE\daily_targets.py"
$BRIEF_PY="$ROOT\70_SCORING_ENGINE\daily_brief.py"

$LEADS="$ROOT\60_METRICS\leads.csv"
$OUTDIR="$ROOT\50_LOGS\weekly_reports"
if(!(Test-Path $OUTDIR)){ New-Item -ItemType Directory -Path $OUTDIR | Out-Null }

$today = Get-Date -Format "yyyy-MM-dd"
$cycleLog = Join-Path $OUTDIR ("cycle_{0}.md" -f $today)

function WriteLine([string]$s){
  Add-Content -Encoding UTF8 $cycleLog $s
}

function RunStep([string]$name,[string]$cmd){
  Write-Host "`n== $name ==" -ForegroundColor Cyan
  WriteLine ""
  WriteLine "## $name"
  WriteLine ""
  WriteLine "Command: `$ $cmd"
  WriteLine ""
  $out = & powershell -NoProfile -Command $cmd 2>&1
  $outText = ($out | Out-String).TrimEnd()
  if($outText){ WriteLine "```"; WriteLine $outText; WriteLine "```" }
  return $outText
}

# ---- Start log
" # Brain Lab Daily Cycle  $today " | Set-Content -Encoding UTF8 $cycleLog
WriteLine ""
WriteLine ("Generated: {0}" -f (Get-Date -Format s))
WriteLine ""

# ---- Step 1 Harvest (retry 2x on 504)
$harvestOut = ""
for($i=1; $i -le 3; $i++){
  $harvestOut = RunStep "1) Harvest Leads (OSM/Overpass) attempt $i/3" ("python `"$HARVEST_PY`"")
  if($harvestOut -notmatch "HTTPError 504"){
    break
  }
  Start-Sleep -Seconds (3 * $i)
}

# ---- Step 2 Select targets (queued)
$targetsOut = RunStep "2) Select Today Targets (queued)" ("python `"$TARGETS_PY`"")

# ---- Step 3 Daily brief
$briefOut = RunStep "3) Daily Brief" ("python `"$BRIEF_PY`"")

# ---- Step 4 Snapshot counts from leads.csv
Write-Host "`n== 4) Snapshot ==" -ForegroundColor Cyan
WriteLine ""
WriteLine "## 4) Snapshot"
WriteLine ""

if(Test-Path $LEADS){
  $rows = Import-Csv $LEADS

  $counts = $rows | Group-Object status | Sort-Object Count -Descending |
    Select-Object Name,Count

  WriteLine "### Status counts"
  WriteLine ""
  WriteLine "| status | count |"
  WriteLine "|---|---:|"
  foreach($c in $counts){
    WriteLine ("| {0} | {1} |" -f $c.Name, $c.Count)
  }

  $topSources = $rows | Where-Object { $_.source } | Group-Object source | Sort-Object Count -Descending | Select-Object -First 10 Name,Count
  WriteLine ""
  WriteLine "### Top sources (10)"
  WriteLine ""
  WriteLine "| source | count |"
  WriteLine "|---|---:|"
  foreach($s in $topSources){
    WriteLine ("| {0} | {1} |" -f $s.Name, $s.Count)
  }

  # Show where today's targets file should be
  $targetsFile = Join-Path $OUTDIR ("today_targets_{0}.md" -f $today)
  $briefFile   = Join-Path $OUTDIR ("daily_brief_{0}.md" -f $today)

  WriteLine ""
  WriteLine "### Outputs"
  WriteLine ("- Targets: {0}" -f $targetsFile)
  WriteLine ("- Brief:   {0}" -f $briefFile)
  WriteLine ("- Cycle:   {0}" -f $cycleLog)

  Write-Host "OK: Snapshot written." -ForegroundColor Green
}else{
  WriteLine "ERR: leads.csv not found."
  Write-Host "ERR: leads.csv not found." -ForegroundColor Red
}

Write-Host "`nOK: Cycle log -> $cycleLog" -ForegroundColor Green
Write-Host "Open:" -ForegroundColor Cyan
Write-Host "notepad $cycleLog" -ForegroundColor Yellow