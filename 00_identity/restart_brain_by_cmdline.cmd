@echo off
setlocal enabledelayedexpansion

set BS=C:\AI_VAULT\00_identity\brain_server.py

echo [restart_brain] Killing python processes running brain_server.py...
for /f "tokens=2 delims== " %%p in ('wmic process where "name='python.exe' and CommandLine like '%%brain_server.py%%'" get ProcessId /value ^| findstr ProcessId') do (
  echo   - taskkill PID %%p
  taskkill /PID %%p /F >nul 2>&1
)

echo.
echo [restart_brain] Starting Brain in a NEW window (will NOT close)...
start "BRAIN-8010" cmd /k powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "python "%BS%""

echo.
echo [restart_brain] Done.
endlocal
