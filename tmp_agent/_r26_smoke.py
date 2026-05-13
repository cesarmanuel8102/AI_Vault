"""R26 smoke: run_command nmap -> auto-fallback scan_local_network."""
import asyncio, sys, json
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")

async def main():
    from brain_v9.agent.tools import run_command, _detect_missing_binary, _extract_cidr_from_cmd

    results = {}

    # T1: detect missing binary regex
    err1 = "'nmap' is not recognized as an internal or external command"
    results["T1_detect_nmap"] = _detect_missing_binary("nmap -sn 192.168.1.0/24", err1)
    err2 = "bash: curl: command not found"
    results["T2_detect_curl"] = _detect_missing_binary("curl https://x", err2)

    # T3: cidr extraction
    results["T3_cidr_full"]  = _extract_cidr_from_cmd("nmap -sn 192.168.1.0/24 -oG -")
    results["T4_cidr_ip"]    = _extract_cidr_from_cmd("ping 8.8.8.8")

    # T5: actual run_command -> nmap (will fail, should auto-fallback)
    r5 = await run_command("nmap -sn 127.0.0.1/32", timeout=10)
    results["T5_nmap_auto_fallback"] = {
        "success": r5.get("success"),
        "missing_binary": r5.get("missing_binary"),
        "native_alternative": r5.get("native_alternative"),
        "auto_fallback_used": r5.get("auto_fallback_used"),
        "fallback_summary": r5.get("fallback_summary"),
        "fallback_cidr": (r5.get("auto_fallback_result") or {}).get("cidr"),
    }

    # T6: wget missing (typically not on Windows) -> only suggestion (no auto)
    r6 = await run_command("wget https://example.com", timeout=10)
    results["T6_wget_suggestion"] = {
        "missing_binary": r6.get("missing_binary"),
        "native_alternative": r6.get("native_alternative"),
        "auto_fallback_used": r6.get("auto_fallback_used"),  # should be None
    }

    # T7: command that exists -> no fallback fields
    r7 = await run_command("echo hello", timeout=5)
    results["T7_normal_no_fallback"] = {
        "success": r7.get("success"),
        "stdout_head": (r7.get("stdout") or "")[:30],
        "missing_binary": r7.get("missing_binary"),  # should be None
    }

    print(json.dumps(results, indent=2, default=str))

    ok = (
        results["T1_detect_nmap"] == "nmap"
        and results["T2_detect_curl"] == "curl"
        and results["T3_cidr_full"] == "192.168.1.0/24"
        and results["T5_nmap_auto_fallback"]["auto_fallback_used"] == "scan_local_network"
        and results["T6_wget_suggestion"]["native_alternative"] == "check_http_service"
        and results["T6_wget_suggestion"]["auto_fallback_used"] is None
        and results["T7_normal_no_fallback"]["missing_binary"] is None
    )
    print("R26_VERDICT:", "PASS" if ok else "FAIL")

asyncio.run(main())
