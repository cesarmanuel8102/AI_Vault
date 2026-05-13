"""R15+R20 direct smoke - invokes tools via Python asyncio."""
import sys, asyncio, json, traceback
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")
sys.path.insert(0, "C:/AI_VAULT")

from brain_v9.agent.tools import read_file, scan_local_network, build_standard_executor

async def main():
    print("=" * 60)
    print("R15: read_file on a DIRECTORY via ToolExecutor (must be discriminated)")
    print("=" * 60)
    ex = build_standard_executor()
    # Call via executor so the loop's catch fires (but executor itself catches earlier)
    # First call directly to see the raw exception
    print("\n-- Direct call (raw) --")
    try:
        r = await read_file("C:/AI_VAULT/tmp_agent/brain_v9")
        print("RESULT:", json.dumps(r, default=str)[:500])
    except Exception as e:
        print(f"RAW EXC: {type(e).__name__}: {e}")

    print("\n-- Via executor (R15 catch should fire if exception escapes) --")
    try:
        r = await ex.execute("read_file", {"path": "C:/AI_VAULT/tmp_agent/brain_v9"})
        print("RESULT:", json.dumps(r, default=str)[:500])
    except Exception as e:
        print(f"EXEC EXC: {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print("R20: scan_local_network /24 with auto_chunk=True")
    print("=" * 60)
    try:
        import time
        t0 = time.time()
        r = await scan_local_network(cidr="192.168.1.0/24", timeout=0.2,
                                      max_hosts=64, auto_chunk=True)
        dt = time.time() - t0
        print(f"DURATION: {dt:.1f}s")
        # Trim live_hosts to keep output short
        if r.get("live_hosts"):
            r["live_hosts_sample"] = r["live_hosts"][:5]
            r["live_hosts"] = f"<{len(r['live_hosts'])} items>"
        print(json.dumps(r, indent=2, default=str))
    except Exception as e:
        print(f"EXC: {type(e).__name__}: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("R20: legacy auto_chunk=False on /24 must early-return error")
    print("=" * 60)
    try:
        r = await scan_local_network(cidr="192.168.1.0/24", timeout=0.2,
                                      max_hosts=64, auto_chunk=False)
        print(json.dumps(r, indent=2, default=str))
    except Exception as e:
        print(f"EXC: {type(e).__name__}: {e}")

asyncio.run(main())
