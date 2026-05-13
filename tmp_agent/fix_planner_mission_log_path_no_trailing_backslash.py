import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Replace ONLY the broken path expression that ends with runs\"
# We set: "path": r"C:\AI_VAULT\tmp_agent\runs" + "\\" + str(room_id) + r"\mission_log.txt",
pat = r'"path"\s*:\s*r"C:\\AI_VAULT\\tmp_agent\\runs\\\"\s*\+\s*str\(room_id\)\s*\+\s*r"\\mission_log\.txt"\s*,'
rep = r'"path": r"C:\\AI_VAULT\\tmp_agent\\runs" + "\\" + str(room_id) + r"\\mission_log.txt",'

if not re.search(pat, txt):
    # fallback: looser match around tmp_agent\runs\  (handles tabs/backslashes that already got normalized)
    pat2 = r'"path"\s*:\s*r".*tmp_agent.*runs\\\"\s*\+\s*str\(room_id\)\s*\+\s*r"\\mission_log\.txt"\s*,'
    if not re.search(pat2, txt):
        raise SystemExit("No encontré la línea rota del path (runs\\\" ...) para reemplazar.")
    txt2 = re.sub(pat2, rep, txt, count=1)
else:
    txt2 = re.sub(pat, rep, txt, count=1)

p.write_text(txt2, encoding="utf-8")
print("OK: mission_log path fixed (no raw string ending with backslash).")
