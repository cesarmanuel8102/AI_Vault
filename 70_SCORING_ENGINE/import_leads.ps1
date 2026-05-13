$ErrorActionPreference="Stop"
$ROOT="C:\AI_VAULT"
$DEST="$ROOT\60_METRICS\leads.csv"

function Norm([string]$s){
  if([string]::IsNullOrWhiteSpace($s)){ return "" }
  $t = $s.Trim()
  $t = $t -replace "\s+"," "
  return $t
}

if(!(Test-Path $DEST)){
  Write-Host "Missing leads.csv template. Run outbound_pack first." -ForegroundColor Red
  exit 1
}

# ---------- Ask until valid ----------
do {
  $src = Read-Host "Paste FULL CSV path to import (drag & drop works)"
  $src = Norm $src
  if($src -eq ""){
    Write-Host "Path cannot be empty." -ForegroundColor Yellow
  }
  elseif(!(Test-Path $src)){
    Write-Host "File not found: $src" -ForegroundColor Yellow
    $src=""
  }
} while($src -eq "")

Write-Host "Importing from: $src" -ForegroundColor Cyan

# ---------- Load existing ----------
$existing = Import-Csv $DEST
$seen = @{}
foreach($e in $existing){
  $key = (Norm $e.email_or_handle).ToLower()
  if($key -ne ""){ $seen[$key]=$true }
}

# ---------- Load source ----------
$in = Import-Csv $src
$now = (Get-Date).ToString("s")

$added = 0

foreach($row in $in){

  $name    = $row.name
  $company = $row.company
  $email   = $row.email
  $phone   = $row.phone
  $web     = $row.website
  $city    = $row.city

  $handle = $email
  if(!$handle){ $handle = $phone }
  if(!$handle){ $handle = $web }
  if(!$handle){ $handle = $company }
  if(!$handle){ continue }

  $key = $handle.ToLower()
  if($seen.ContainsKey($key)){ continue }

  $leadId = "L-IMP-{0:0000}" -f ($added + 1)

  $obj = [pscustomobject]@{
    lead_id = $leadId
    segment = "B2B"
    channel = "email_or_dm"
    name = $(if($name){$name}else{"Lead"})
    company = $company
    role = "Owner/Manager"
    email_or_handle = $handle
    city = $city
    notes = "imported"
    status = "new"
    created_at = $now
  }

  $existing += $obj
  $seen[$key]=$true
  $added++
}

$existing | Export-Csv -NoTypeInformation -Encoding UTF8 $DEST

Write-Host "OK: Imported leads added: $added" -ForegroundColor Green
Write-Host "Updated: $DEST" -ForegroundColor Cyan