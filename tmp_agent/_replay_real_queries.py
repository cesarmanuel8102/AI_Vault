import requests
import json

# Replay the real user queries to see current responses
queries = [
    "revisa el ultimo backtest realizado en la plataforma Quantconnect y describe que resultado obtuvo",
    "accede a QC y revisa",
    "ok, todo esta por el 8090, pero revisa lo que necesites para acceder a QC y revisar el ultimo backtest",
    "conectate a QC y obten lo solicitado y haz el analisis",
    "que herramientas necesitas para eso?",
    "instala las herramientas necesarias en tu toolkit",
]

for i, q in enumerate(queries):
    print(f"\n{'='*80}")
    print(f"QUERY {i+1}: {q[:80]}")
    print(f"{'='*80}")
    try:
        r = requests.post('http://localhost:8090/chat',
                          json={"message": q, "session_id": "review_session"},
                          timeout=120)
        data = r.json()
        resp = data.get("response", "")
        print(f"RESPONSE ({len(resp)} chars):")
        print(resp[:1500])
        if len(resp) > 1500:
            print(f"... [truncated, {len(resp)} total chars]")
    except Exception as e:
        print(f"ERROR: {e}")
    print()
