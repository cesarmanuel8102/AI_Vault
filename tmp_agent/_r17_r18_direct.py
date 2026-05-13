"""R17 + R18 direct smoke."""
import sys, asyncio, json, time
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")
sys.path.insert(0, "C:/AI_VAULT")

from brain_v9.agent.tools import _run_internal_command, run_powershell, run_command

async def main():
    print("=" * 60)
    print("R17a: PowerShell -Command with $ should be REJECTED with hint")
    print("=" * 60)
    r = await _run_internal_command('powershell -Command "Write-Host $env:USERNAME"')
    print(json.dumps(r, indent=2)[:600])

    print("\n" + "=" * 60)
    print("R17b: run_powershell via inline script (ASCII)")
    print("=" * 60)
    r = await run_powershell(script='Write-Host "hello from R17"; $env:COMPUTERNAME')
    print(json.dumps(r, indent=2)[:600])

    print("\n" + "=" * 60)
    print("R17c: run_powershell via .ps1 file (existing _health.ps1)")
    print("=" * 60)
    r = await run_powershell(file_path="C:/AI_VAULT/tmp_agent/_health.ps1")
    print(json.dumps(r, indent=2)[:600])

    print("\n" + "=" * 60)
    print("R17d: regression - normal cmd still works")
    print("=" * 60)
    r = await _run_internal_command('echo regression_ok')
    print(json.dumps(r, indent=2)[:300])

    print("\n" + "=" * 60)
    print("R18: tail event_log for chat.completed (after we hit chat)")
    print("=" * 60)

asyncio.run(main())
