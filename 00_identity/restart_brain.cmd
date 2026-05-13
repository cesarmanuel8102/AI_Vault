@echo off
setlocal enabledelayedexpansion

set PORT=8010
set BS=C:\AI_VAULT\00_identity\brain_server.py

echo [restart_brain] Killing listener on port %PORT% (if any)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do (
  echo   - taskkill PID %%p
  taskkill /PID %%p /F >nul 2>&1
)

echo.
echo [restart_brain] Starting Brain in a NEW window (will NOT close)...
start "BRAIN-8010" cmd /k powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "python "%BS%""

echo.
echo [restart_brain] Done. Check the new window titled BRAIN-8010.
endlocal
