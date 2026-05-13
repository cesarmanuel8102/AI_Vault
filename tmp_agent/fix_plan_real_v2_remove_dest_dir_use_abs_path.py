import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 BEGIN ==="
END   = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 END ==="

i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 <= i0:
    raise SystemExit("No encuentro bloque PLAN_REAL_ENDPOINT_V2_GATED_V1 (BEGIN/END).")

block = txt[i0:i1 + len(END)]

# Reemplazar el dict del step S3 completo (robusto: desde "id": "S3" hasta el cierre "},")
pat = r'\{\s*"id"\s*:\s*"S3"[\s\S]*?\n\s*\},\s*'
m = re.search(pat, block)
if not m:
    raise SystemExit("No encontré el step S3 dentro de plan_real_v2 para reemplazar.")

# Step S3: SIN dest_dir. path ABSOLUTO bajo tmp_agent\\runs\\<room>\\real_log.txt
new_s3 = r'''{
            "id": "S3",
            "title": "Write real_log.txt (append_file) — gated SAFE",
            "status": "todo",
            "tool_name": "append_file",
            "mode": "propose",
            "kind": "new_file",
            "tool_args": {
                "path": (r"C:\AI_VAULT\tmp_agent\runs" + "\\" + str(room_id) + r"\real_log.txt"),
                "content": "REAL_V2 START\\n",
            },
        },'''

block2 = re.sub(pat, new_s3 + "\n        ", block, count=1)

txt2 = txt[:i0] + block2 + txt[i1 + len(END):]
p.write_text(txt2, encoding="utf-8")
print("OK: plan_real_v2 S3 patched -> removed dest_dir, using absolute tmp_agent\\runs\\<room>\\real_log.txt")
