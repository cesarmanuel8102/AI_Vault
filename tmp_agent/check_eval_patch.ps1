$ErrorActionPreference="Stop"
$s="C:\AI_VAULT\00_identity\brain_server.py"
Select-String -Path $s -SimpleMatch -Pattern "EVALUATE_ROOM_ID_FIX_V1" -Context 0,2 |
  ForEach-Object {
    "{0}: {1}" -f $_.LineNumber, $_.Line
    $_.Context.PostContext
  }
