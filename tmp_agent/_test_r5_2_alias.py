"""R5.2 / R4.2 validation: alias + fuzzy match firing."""
import sys
import asyncio
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")

from brain_v9.agent.loop import ToolExecutor
from brain_v9.core import validator_metrics as vm

vm.reset()

async def fake_tool(**kwargs):
    return {"success": True, "result": "ok"}

ex = ToolExecutor()
ex.register("list_directory", fake_tool, "lists dir", "fs")
ex.register("install_package", fake_tool, "installs pkg", "system")

async def main():
    # alias hit: "ls" -> "list_directory"
    r1 = await ex.execute("ls", path=".")
    print(f"alias 'ls' -> success={r1.get('success')}")

    # alias hit: "pip_install" -> "install_package"
    r2 = await ex.execute("pip_install", package="rich")
    print(f"alias 'pip_install' -> success={r2.get('success')}")

    # fuzzy hit: "list_directry" (typo) -> "list_directory"
    r3 = await ex.execute("list_directry", path=".")
    print(f"fuzzy 'list_directry' -> success={r3.get('success')}")

    # fuzzy hit: "instal_packge" -> "install_package"
    r4 = await ex.execute("instal_packge", package="x")
    print(f"fuzzy 'instal_packge' -> success={r4.get('success')}")

    # unknown: should NOT fire counter
    r5 = await ex.execute("totally_made_up_xyz123")
    print(f"unknown -> success={r5.get('success')}")

asyncio.run(main())

snap = vm.snapshot()
print(f"\n=== validator_metrics snapshot ===")
print(snap)
expected = 4
got = snap.get("tool_name_corrected", 0)
print(f"\ntool_name_corrected: expected={expected} got={got}")
print("PASS" if got == expected else "FAIL")
