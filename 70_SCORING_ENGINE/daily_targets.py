import os, csv, re
from datetime import datetime

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
LEADS = os.path.join(ROOT, r"60_METRICS\leads.csv")
OUTDIR = os.path.join(ROOT, r"50_LOGS\weekly_reports")

REQUIRED_COLS = [
    "lead_id","segment","channel","name","company","role",
    "email_or_handle","city","notes","status","created_at",
    "validated","source"
]

def norm(s): return re.sub(r"\s+"," ", (s or "").strip())

def ensure_columns(rows, fieldnames):
    fn = list(fieldnames or [])
    for c in REQUIRED_COLS:
        if c not in fn:
            fn.append(c)
    # backfill missing keys
    for r in rows:
        for c in REQUIRED_COLS:
            if c not in r or r[c] is None:
                r[c] = ""
    return rows, fn

def load_rows(path):
    with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
        dr = csv.DictReader(f)
        rows = [row for row in dr if any((v or "").strip() for v in row.values())]
        fieldnames = dr.fieldnames or []
    rows, fieldnames = ensure_columns(rows, fieldnames)
    return rows, fieldnames

def save_rows(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def score_row(r):
    status = (r.get("status","") or "").lower()
    if status != "new":
        return -9999.0

    val = (r.get("validated","") or "").lower()
    base = 10.0 if val == "medium" else 2.0 if val == "weak" else 0.0

    handle = (r.get("email_or_handle","") or "").lower()
    if "@" in handle: base += 2.0
    if handle.startswith("http"): base += 1.0

    src = (r.get("source","") or "").lower()
    # Slightly prefer business-friendly niches for EXP-B
    if "accountant" in src or "company" in src or "it" in src:
        base += 1.0

    return base

def pick(rows, n, filter_fn):
    cand = [r for r in rows if filter_fn(r)]
    cand.sort(key=score_row, reverse=True)
    return cand[:n]

def render_msg_exp_a(company, city):
    city = city or "tu zona"
    return (
        f"Hola, vi que muchas empresas en {city} pierden tiempo con Excel desordenado.\\n"
        f"Puedo dejarlo limpio y estandarizado (validaciones, formatos, resumen de cambios) en 24-48h.\\n"
        f"Si quieres, te hago una muestra gratis con 20 filas (sin compromiso).\\n"
        f"- Cesar"
    )

def render_msg_exp_b(company, city):
    city = city or "tu zona"
    return (
        f"Hola, si cada semana haces reportes manuales, puedo automatizarlos.\\n"
        f"Piloto 7 días: 1 dashboard + 1 reporte semanal automático desde tu Excel/CSV.\\n"
        f"Te interesa probarlo esta semana?\\n"
        f"- Cesar"
    )

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    if not os.path.exists(LEADS):
        raise SystemExit(f"Missing leads file: {LEADS}")

    rows, fieldnames = load_rows(LEADS)

    # EXP-B: 5 B2B new leads
    exp_b = pick(
        rows, 5,
        lambda r: (r.get("status","").lower()=="new") and (r.get("segment","").lower() in ("b2b",""))
    )

    used_ids = set(r.get("lead_id","") for r in exp_b)

    # EXP-A: 5 other new leads (not already used)
    exp_a = pick(
        [r for r in rows if r.get("lead_id","") not in used_ids],
        5,
        lambda r: (r.get("status","").lower()=="new")
    )

    picked = exp_b + exp_a
    if not picked:
        print("No NEW leads available. Run harvester again.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    outpath = os.path.join(OUTDIR, f"today_targets_{today}.md")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    md=[]
    md.append(f"# Today Targets  {today}")
    md.append("")
    md.append(f"Generated: {now}")
    md.append("")

    md.append("## EXP-B (OPP-014)  5 Targets")
    md.append("")
    for i,r in enumerate(exp_b, start=1):
        company = norm(r.get("company",""))
        city = norm(r.get("city",""))
        handle = norm(r.get("email_or_handle",""))
        md.append(f"### B{i}  {company}")
        md.append(f"- lead_id: {r.get('lead_id','')}")
        md.append(f"- contact: {handle}")
        md.append(f"- validated: {r.get('validated','')}")
        md.append(f"- source: {r.get('source','')}")
        md.append("")
        md.append(render_msg_exp_b(company, city))
        md.append("")

    md.append("## EXP-A (OPP-003)  5 Targets")
    md.append("")
    for i,r in enumerate(exp_a, start=1):
        company = norm(r.get("company",""))
        city = norm(r.get("city",""))
        handle = norm(r.get("email_or_handle",""))
        md.append(f"### A{i}  {company}")
        md.append(f"- lead_id: {r.get('lead_id','')}")
        md.append(f"- contact: {handle}")
        md.append(f"- validated: {r.get('validated','')}")
        md.append(f"- source: {r.get('source','')}")
        md.append("")
        md.append(render_msg_exp_a(company, city))
        md.append("")

    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    # Mark queued
    picked_ids = set(r.get("lead_id","") for r in picked)
    changed = 0
    for r in rows:
        if r.get("lead_id","") in picked_ids and (r.get("status","") or "").lower() == "new":
            r["status"] = "queued"
            changed += 1

    save_rows(LEADS, fieldnames, rows)

    print(f"OK: wrote {outpath}")
    print(f"OK: marked queued={changed} in {LEADS}")

if __name__ == "__main__":
    main()