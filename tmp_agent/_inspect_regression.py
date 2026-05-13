import json, glob, os
files = glob.glob(r"C:\AI_VAULT\tmp_agent\state\r13_replay\report_*.json")
latest = max(files, key=os.path.getmtime)
print("Report:", latest)
with open(latest, "r", encoding="utf-8") as f:
    data = json.load(f)
for entry in data.get("results", []):
    if entry.get("verdict") == "regressed":
        print("=" * 60)
        print("Q:", entry.get("user_msg"))
        print("\nOLD PREVIEW:")
        print(entry.get("old_resp_preview", ""))
        print("\nNEW PREVIEW:")
        print(entry.get("new_resp_preview", ""))
