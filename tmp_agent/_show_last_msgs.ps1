$json = Get-Content C:/AI_VAULT/tmp_agent/state/memory/default/short_term.json -Raw | ConvertFrom-Json
$json.messages | Select-Object -Last 6 | ForEach-Object {
  Write-Host "---"
  Write-Host ("TS:      " + $_.timestamp)
  Write-Host ("ROLE:    " + $_.role)
  $c = [string]$_.content
  if ($c.Length -gt 600) { $c = $c.Substring(0,600) + "...[trunc]" }
  Write-Host ("CONTENT: " + $c)
}
