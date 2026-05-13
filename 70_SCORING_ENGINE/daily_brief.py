import csv, os
from datetime import datetime

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
CSV_PATH = os.path.join(ROOT, r"60_METRICS\opportunity_scores.csv")
OUT_DIR  = os.path.join(ROOT, r"50_LOGS\weekly_reports")

def to_float(x, default=0.0):
    try:
        if x is None: return default
        s = str(x).strip()
        if s == "": return default
        return float(s)
    except Exception:
        return default

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    if not os.path.exists(CSV_PATH):
        raise SystemExit(f"Missing: {CSV_PATH}")

    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # Sort by score_total desc
    rows.sort(key=lambda r: to_float(r.get("score_total", 0.0), 0.0), reverse=True)

    today = datetime.now().strftime("%Y-%m-%d")
    now   = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    out_path = os.path.join(OUT_DIR, f"daily_brief_{today}.md")

    top = rows[:5]

    lines = []
    lines.append(f"# Daily Brief  {today}")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append("")
    lines.append("## Top 5 Opportunities (by score)")
    lines.append("")
    if not top:
        lines.append("_No opportunities found in CSV._")
    else:
        lines.append("| Rank | ID | Category | Score | TTD(days) | Capital | Status | Name |")
        lines.append("|---:|---|---|---:|---:|---:|---|---|")
        for i,r in enumerate(top, start=1):
            lines.append(
                f"| {i} | {r.get('opportunity_id','')} | {r.get('category','')} | {r.get('score_total','')} | "
                f"{r.get('time_to_first_dollar_days','')} | {r.get('capital_required','')} | {r.get('status','')} | "
                f"{(r.get('name','') or '').replace('|','/')} |"
            )

    lines.append("")
    lines.append("## Today Actions (auto-suggested)")
    lines.append("")
    lines.append("1) EXP-A (OPP-003): preparar oferta + demo + 10 mensajes outbound.")
    lines.append("2) EXP-B (OPP-014): preparar paquete piloto + 10 mensajes outbound.")
    lines.append("3) EXP-C: mantener pipeline (score + brief) diario y logs limpios.")

    content = "\n".join(lines) + "\n"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(content)
    print(f"OK: wrote {out_path}")

if __name__ == "__main__":
    main()