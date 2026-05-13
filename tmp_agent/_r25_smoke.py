"""R25 smoke: scan_local_network must accept network= alias for cidr=."""
import asyncio, sys, json
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")

async def main():
    from brain_v9.agent.tools import scan_local_network

    results = {}

    # T1: legacy cidr= still works
    r1 = await scan_local_network(cidr="127.0.0.1/32", timeout=0.2)
    results["T1_cidr_legacy"] = {"success": r1.get("success"), "scanned_cidr": r1.get("cidr"), "error": r1.get("error")}

    # T2: R25 alias network=
    r2 = await scan_local_network(network="127.0.0.1/32", timeout=0.2)
    results["T2_network_alias"] = {"success": r2.get("success"), "scanned_cidr": r2.get("cidr"), "error": r2.get("error")}

    # T3: alias target=
    r3 = await scan_local_network(target="127.0.0.1/32", timeout=0.2)
    results["T3_target_alias"] = {"success": r3.get("success"), "scanned_cidr": r3.get("cidr"), "error": r3.get("error")}

    # T4: alias subnet=
    r4 = await scan_local_network(subnet="127.0.0.1/32", timeout=0.2)
    results["T4_subnet_alias"] = {"success": r4.get("success"), "scanned_cidr": r4.get("cidr"), "error": r4.get("error")}

    # T5: no args -> autodetect (must not crash)
    r5 = await scan_local_network(max_hosts=4, max_total_hosts=4, timeout=0.1)
    results["T5_autodetect"] = {"success": r5.get("success"), "has_cidr": bool(r5.get("cidr")), "error": r5.get("error")}

    print(json.dumps(results, indent=2))

    ok = all(results[k]["success"] for k in ("T1_cidr_legacy", "T2_network_alias", "T3_target_alias", "T4_subnet_alias"))
    print("R25_VERDICT:", "PASS" if ok else "FAIL")

asyncio.run(main())
