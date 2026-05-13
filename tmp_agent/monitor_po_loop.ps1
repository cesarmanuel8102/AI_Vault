for ($i=1; $i -le 5; $i++) {
    Write-Host "--- Check $i at $(Get-Date -Format 'HH:mm:ss') ---"
    python C:/AI_VAULT/tmp_agent/check_po_pipeline.py
    if ($i -lt 5) { Start-Sleep -Seconds 180 }
}
