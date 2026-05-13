$dir = "C:\AI_VAULT\tmp_agent\state\conversations"
$all = Get-ChildItem -Path $dir -Filter *.json | Sort-Object LastWriteTime -Descending | Select-Object -First 15
Write-Host "Total files in dir: $((Get-ChildItem -Path $dir -Filter *.json).Count)"
Write-Host ""
foreach ($f in $all) {
    Write-Host ("[{0}] {1}" -f $f.LastWriteTime, $f.Name)
}
