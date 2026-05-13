$matches = Select-String -Path C:\AI_VAULT\memory\semantic\semantic_memory.jsonl -Pattern 'user_correction|USER CORRECTION' | Select-Object -Last 5
foreach ($m in $matches) {
    $line = $m.Line
    if ($line.Length -gt 400) { $line = $line.Substring(0, 400) + "..." }
    Write-Host $line
    Write-Host "---"
}
Write-Host "Total matches: $($matches.Count)"
