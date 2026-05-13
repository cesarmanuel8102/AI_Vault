import json, sys
p = r"C:\AI_VAULT\tmp_agent\state\memory\default\short_term.json"
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
msgs = data.get("messages", [])
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
print(f"Total messages: {len(msgs)}; showing last {N}")
print("=" * 80)
for m in msgs[-N:]:
    role = m.get("role", "?")
    ts = m.get("timestamp", "")
    content = m.get("content", "")
    print(f"\n--- [{role}] {ts} ---")
    print(content[:2500])
