$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:8010"
$room = ("room_minreal_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$hdr  = @{ "x-room-id" = $room; "Content-Type" = "application/json" }

# 1) runtime snapshot set
$setBody = @{
  path  = "mission_state.json"
  value = @{
    ts      = (Get-Date).ToString("o")
    room_id = $room
    goal    = "MIN_REAL_PLAN"
    stage   = "planned"
  }
} | ConvertTo-Json -Depth 10

Invoke-WebRequest -UseBasicParsing -Method Post `
  -Uri ($base + "/v1/agent/runtime/snapshot/set") `
  -Headers $hdr -Body $setBody -ContentType "application/json" | Out-Null

# 2) execute list_dir
$execBody = @{
  tool_name = "list_dir"
  tool_args = @{ path = "C:\AI_VAULT\tmp_agent\workspace" }
  mode      = "read"
} | ConvertTo-Json -Depth 10

$obs = Invoke-RestMethod -Method Post `
  -Uri ($base + "/v1/agent/execute") `
  -Headers $hdr -Body $execBody -ContentType "application/json"

# 3) evaluate
$evalBody = @{
  room_id = $room
  observation = @{
    ok             = $true
    room_id        = $room
    note           = "min-real eval"
    workspace_list = $obs.result
  }
} | ConvertTo-Json -Depth 25

$ev = Invoke-RestMethod -Method Post `
  -Uri ($base + "/v1/agent/evaluate") `
  -Headers $hdr -Body $evalBody -ContentType "application/json"

Write-Host ("ROOM=" + $room) -ForegroundColor Yellow
$ev | ConvertTo-Json -Depth 40

