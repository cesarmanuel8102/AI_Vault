"""Full test battery for Brain V9 chat response quality."""
import requests
import json
import time
import sys

BASE = "http://127.0.0.1:8090"

tests = [
    # (description, message, expected_keywords, bad_keywords)
    ("Greeting", "hola", ["Brain V9", "operativo"], ["`", "```", "error"]),
    ("Status", "estado del sistema", ["Utility", "Fase", "Edge", "Blockers"], ["**", "`", "```"]),
    ("Autonomy", "estado de autonomia", ["Utility", "veredicto"], ["**", "`", "```"]),
    ("Trading analysis", "analiza el estado actual del trading", ["trading", "estrategia"], ["**", "`", "```"]),
    ("Disk space", "que espacio libre tengo en disco", ["GB", "total", "libre"], ["```", "raw"]),
    ("Single port", "que proceso usa el puerto 8090", ["8090", "python"], ["port:", "status:", "en_uso"]),
    ("Multi port", "verifica los puertos 8090, 4002, 11434 y 8765", ["Puerto 8090", "Puerto 4002", "Puerto 11434", "Puerto 8765"], ["port:", "status:", "en_uso"]),
    ("All services", "revisa el estado general de todos los servicios", ["servicios", "operativo"], ["overall_status", "critical_services_down", "```"]),
    ("Control", "/control", ["Control", "cambios"], ["**", "`control`"]),
    ("Risk", "/risk", ["Riesgo", "ejecucion"], ["**", "`risk`"]),
    ("Governance", "/governance", ["gobernanza", "Modo"], ["**", "`governance`"]),
]

print(f"{'Test':<20} {'Status':<10} {'Time':>6} Response preview")
print("=" * 100)

passed = 0
failed = 0

for desc, msg, good_kw, bad_kw in tests:
    t0 = time.time()
    try:
        r = requests.post(f"{BASE}/chat",
                          json={"message": msg, "session_id": f"test_{desc.lower().replace(' ','_')}"},
                          timeout=180)
        elapsed = time.time() - t0
        resp = r.json().get("response", "")

        # Check for expected keywords (case-insensitive)
        missing = [kw for kw in good_kw if kw.lower() not in resp.lower()]
        # Check for bad keywords (case-sensitive — backticks, raw keys)
        found_bad = [kw for kw in bad_kw if kw in resp]

        if not missing and not found_bad:
            status = "PASS"
            passed += 1
        else:
            status = "FAIL"
            failed += 1

        # Encode-safe print
        preview = resp[:80].encode('ascii', errors='replace').decode('ascii')
        print(f"{desc:<20} {status:<10} {elapsed:>5.1f}s {preview}")
        if missing:
            print(f"  MISSING: {missing}")
        if found_bad:
            print(f"  BAD: {found_bad}")
    except Exception as e:
        failed += 1
        elapsed = time.time() - t0
        print(f"{desc:<20} {'ERROR':<10} {elapsed:>5.1f}s {e}")

print("=" * 100)
print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
sys.exit(0 if failed == 0 else 1)
