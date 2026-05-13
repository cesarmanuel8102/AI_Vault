import requests
import json

# Get recent chat metrics/history
try:
    r = requests.post('http://localhost:8090/chat',
                      json={"message": "/metrics", "session_id": "debug_review"},
                      timeout=30)
    data = r.json()
    resp = data.get("response", "")
    print("=== /metrics ===")
    print(resp[:2000])
except Exception as e:
    print(f"metrics error: {e}")

print("\n\n")

# Check if there's a way to see recent conversations
try:
    r = requests.post('http://localhost:8090/chat',
                      json={"message": "/history", "session_id": "debug_review"},
                      timeout=30)
    data = r.json()
    resp = data.get("response", "")
    print("=== /history ===")
    print(resp[:2000])
except Exception as e:
    print(f"history error: {e}")
