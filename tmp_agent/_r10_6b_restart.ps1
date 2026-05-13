$ErrorActionPreference = 'Stop'
python -m py_compile C:/AI_VAULT/tmp_agent/brain_v9/autonomy/chat_excellence_patcher.py
if ($LASTEXITCODE -ne 0) { Write-Host "[compile] FAIL" -ForegroundColor Red; exit 1 }
Write-Host "[compile] OK" -ForegroundColor Green

Write-Host "Restarting brain to load R10.6b..." -ForegroundColor Cyan
& powershell -ExecutionPolicy Bypass -File C:/AI_VAULT/tmp_agent/_kill_cim.ps1
