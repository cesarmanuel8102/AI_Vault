$env:BRAIN_SAFE_MODE = 'false'
$env:BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS = 'true'
$env:PAD_MFA_TEST_OVERRIDE = 'test_pad_2026'
Start-Process python -ArgumentList 'C:/AI_VAULT/tmp_agent/brain_v9/main.py' -WindowStyle Hidden -RedirectStandardOutput C:/AI_VAULT/50_LOGS/brain_stdout.log -RedirectStandardError C:/AI_VAULT/50_LOGS/brain_stderr.log
Write-Host "Brain launched with godmode env vars"
