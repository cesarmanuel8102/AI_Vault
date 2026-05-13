$ErrorActionPreference="Stop"
$base="http://127.0.0.1:8010"
function New-Room($p){ "{0}_{1}" -f $p,(Get-Date -Format "yyyyMMdd_HHmmss") }

(Invoke-WebRequest -UseBasicParsing -Uri ($base + "/openapi.json")).StatusCode | Out-Null

$rA = New-Room "room_eval_A"
$rB = New-Room "room_eval_B"

function Post-Eval($room,$note){
  $hdr=@{ "x-room-id"=$room; "Content-Type"="application/json" }
  $body=@{ observation=@{ ok=$true; room_id=$room; note=$note } } | ConvertTo-Json -Depth 10
  Invoke-RestMethod -Method Post -Uri "$base/v1/agent/evaluate" -Headers $hdr -Body $body -ContentType "application/json" | Out-Null
}

function Get-LastEval($room){
  $hdr=@{ "x-room-id"=$room }
  $p = Invoke-RestMethod -Method Get -Uri "$base/v1/agent/plan" -Headers $hdr
  [pscustomobject]@{
    room = $room
    plan_room_id = $p.plan.room_id
    last_room_id = $p.plan.last_eval.room_id
    last_note    = $p.plan.last_eval.observation.note
  }
}

Post-Eval $rA "EVAL_A"
Post-Eval $rB "EVAL_B"

Get-LastEval $rA | Format-List
Get-LastEval $rB | Format-List
