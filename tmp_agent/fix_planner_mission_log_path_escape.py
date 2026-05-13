import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

# Replace the broken path line with a safe f-string
bad_pat = r'"path":\s*"C:\\AI_VAULT\\tmp_agent\\runs\\\\" \+ str\(room_id\) \+ "\\\\mission_log\.txt",'
# But current file likely contains unescaped backslashes, so match loosely:
bad_pat2 = r'"path":\s*".*tmp_agent.*runs.*"\s*\+\s*str\(room_id\)\s*\+\s*".*mission_log\.txt",'

good = '"path": f"C:\\\\AI_VAULT\\\\tmp_agent\\\\runs\\\\{room_id}\\\\mission_log.txt",'

if re.search(bad_pat, txt):
    txt2 = re.sub(bad_pat, good, txt, count=1)
elif re.search(bad_pat2, txt):
    txt2 = re.sub(bad_pat2, good, txt, count=1)
else:
    raise SystemExit("No encontré la línea 'path' rota del mission_log.txt para reemplazar.")

p.write_text(txt2, encoding="utf-8")
print("OK: mission_log path fixed -> f-string con backslashes escapados.")
