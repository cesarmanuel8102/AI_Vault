from pathlib import Path

SERVER = r"C:\AI_VAULT\00_identity\brain_server.py"
p = Path(SERVER)
txt = p.read_text(encoding="utf-8")

old = '"content": "# PLANNER_PLACEHOLDER: fill after S2\\n",'
if old not in txt:
    # fallback (por si cambia el spacing)
    old2 = '"content": "# PLANNER_PLACEHOLDER: fill after S2\\n"'
    if old2 not in txt:
        raise SystemExit("No encuentro el placeholder literal en el planner (S3.content).")
    txt = txt.replace(old2, '"content": ""', 1)
else:
    txt = txt.replace(old, '"content": "",', 1)

p.write_text(txt, encoding="utf-8")
print("OK: Planner S3.content ya no usa PLANNER_PLACEHOLDER (ahora vacío).")
