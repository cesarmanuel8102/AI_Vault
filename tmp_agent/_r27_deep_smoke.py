"""R27 deep smoke v2: directly exercise governor.remediate_tool_gap for nmap."""
import asyncio
import sys
sys.path.insert(0, "C:/AI_VAULT")
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")

async def main():
    from brain.capability_governor import get_capability_governor
    g = get_capability_governor()

    # First confirm the stderr parser
    err = "returncode=1 | stderr='nmap' is not recognized as an internal or external command"
    bins = g._extract_missing_binaries(err)
    print(f"[parser] _extract_missing_binaries -> {bins}")
    assert "nmap" in bins, "FAIL: nmap not extracted"

    cands = g._infer_install_candidates("run_command", err)
    print(f"[parser] _infer_install_candidates -> {cands}")
    assert any("nmap" in c.lower() for c in cands), "FAIL: no nmap install command"

    # Now trigger remediate (allow_install=False to avoid actual install)
    print("\n[remediate_tool_gap] requested='nmap', allow_install=False")
    res = await g.remediate_tool_gap("nmap", executor=None, allow_install=False, god_override=False)
    print(f"  status: {res.get('status')}")
    print(f"  install_candidates: {res.get('install_candidates')}")
    print(f"  os_packages: {res.get('os_packages')}")
    print(f"  policy: {res.get('policy')}")

    # And test other binaries to verify generality
    print("\n[parser] generality test:")
    for sample in (
        "git: command not found",
        "command not found: curl",
        "'wget' is not recognized as an internal or external command",
        '"docker" is not recognized',
    ):
        print(f"  {sample!r:60} -> {g._extract_missing_binaries(sample)}")

asyncio.run(main())
print("\n=== R27 deep smoke OK ===")
