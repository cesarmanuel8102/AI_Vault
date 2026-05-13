$dir = "C:\AI_VAULT\tmp_agent\state\conversations"
$files = Get-ChildItem -Path $dir -Filter *.json |
    Where-Object { $_.BaseName -notlike "r13_replay_*" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 10

foreach ($f in $files) {
    Write-Host "===== $($f.Name)  [$($f.LastWriteTime)] ====="
    try {
        $j = Get-Content $f.FullName -Raw | ConvertFrom-Json
        $msgs = $j.messages
        if ($null -eq $msgs) { $msgs = $j.history }
        if ($null -eq $msgs) {
            Write-Host "(no messages field; keys:)"
            $j.PSObject.Properties.Name | ForEach-Object { Write-Host "  - $_" }
            continue
        }
        $count = $msgs.Count
        Write-Host "msgs=$count"
        $take = [Math]::Min(6, $count)
        $start = $count - $take
        for ($i = $start; $i -lt $count; $i++) {
            $m = $msgs[$i]
            $role = $m.role
            $content = "$($m.content)"
            if ($content.Length -gt 300) { $content = $content.Substring(0, 300) + "..." }
            Write-Host "[$role] $content"
        }
    } catch {
        Write-Host "ERROR parsing: $_"
    }
    Write-Host ""
}
