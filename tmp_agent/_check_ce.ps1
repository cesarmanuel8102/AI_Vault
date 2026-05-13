$st = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/brain/chat_excellence/status'
Write-Host "total_iterations: $($st.total_iterations)"
Write-Host "parsed_ratio: $($st.parsed_ratio)"
if ($st.latest) {
  Write-Host "`n--- LATEST ITERATION ---"
  $st.latest | ConvertTo-Json -Depth 4
}
Write-Host "`n--- RECENT (last 5) ---"
$st.recent | Select-Object -Last 5 | ConvertTo-Json -Depth 3
