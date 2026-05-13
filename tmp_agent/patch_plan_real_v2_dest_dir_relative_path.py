import re
from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

BEGIN = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 BEGIN ==="
END   = "# === PLAN_REAL_ENDPOINT_V2_GATED_V1 END ==="
i0 = txt.find(BEGIN)
i1 = txt.find(END)
if i0 < 0 or i1 < 0 or i1 < i0:
    raise SystemExit("No encuentro el bloque PLAN_REAL_ENDPOINT_V2_GATED_V1 (BEGIN/END).")

block = txt[i0:i1]

# Replace S3 dict: set dest_dir=run_dir and path="real_log.txt"
# We match the S3 object roughly and rewrite it.
pat = r'\{\s*"id"\s*:\s*"S3"[\s\S]*?\},\s*?\n'
m = re.search(pat, block)
if not m:
    raise SystemExit("No pude localizar el step S3 dentro de plan_real_v2 para reemplazar.")

new_s3 = r'''{
            "id": "S3",
            "title": "Write real_log.txt (append_file) — gated SAFE",
            "status": "todo",
            "tool_name": "append_file",
            "mode": "propose",
            "kind": "new_file",
            "dest_dir": run_dir,
            "tool_args": {
                "path": "real_log.txt",
                "content": "REAL_V2 START\n"
            },
        },
'''

block2 = re.sub(pat, new_s3, block, count=1)
txt2 = txt[:i0] + block2 + txt[i1:]
p.write_text(txt2, encoding="utf-8")
print("OK: plan_real_v2 S3 ahora usa dest_dir=run_dir y path relativo real_log.txt")
