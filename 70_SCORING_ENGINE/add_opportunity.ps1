$ROOT="C:\AI_VAULT"
$CSV="$ROOT\60_METRICS\opportunity_scores.csv"

if(!(Test-Path $CSV)){
    Write-Host "Missing CSV: $CSV" -ForegroundColor Red
    exit 1
}

function Prompt([string]$q, [string]$def=""){
    $suffix = ""
    if(-not [string]::IsNullOrWhiteSpace($def)){
        $suffix = " [$def]"
    }
    $x = Read-Host ($q + $suffix)
    if([string]::IsNullOrWhiteSpace($x)){ return $def }
    return $x
}

Write-Host "=== Add Opportunities (Ctrl+C to stop) ===" -ForegroundColor Cyan

while($true){
    $id  = Prompt "opportunity_id (e.g., OPP-001)"
    if([string]::IsNullOrWhiteSpace($id)){ continue }

    $name = Prompt "name"
    $cat  = Prompt "category" "services"

    $ttd  = Prompt "time_to_first_dollar_days" "14"
    $mrg  = Prompt "expected_margin_pct" "50"
    $scal = Prompt "scalability_1to5" "3"
    $capr = Prompt "capital_required" "0"
    $risk = Prompt "risk_1to5" "3"
    $comp = Prompt "competition_1to5" "3"
    $lgl  = Prompt "legal_risk_1to5" "2"
    $aut  = Prompt "automation_1to5" "3"

    $evid = Prompt "evidence_note" "note"
    $status="candidate"
    $now = (Get-Date).ToString("s")

    # IMPORTANT: No commas allowed in free text fields (CSV). If you need commas, use semicolons.
    $name = $name -replace ",",";"
    $evid = $evid -replace ",",";"

    $line = @(
        $id,$name,$cat,$ttd,$mrg,$scal,$capr,$risk,$comp,$lgl,$aut,$evid,"",$status,$now,$now
    ) -join ","

    Add-Content -Encoding UTF8 $CSV $line
    Write-Host "OK added: $id" -ForegroundColor Green
}