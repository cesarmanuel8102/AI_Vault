import csv
import os
from datetime import datetime

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
IN_CSV  = os.path.join(ROOT, r"60_METRICS\opportunity_scores.csv")
OUT_CSV = IN_CSV  # in-place update (safe: we rewrite full file)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def to_float(x, default=0.0):
    try:
        if x is None: return default
        s = str(x).strip()
        if s == "": return default
        return float(s)
    except Exception:
        return default

def to_int(x, default=0):
    try:
        if x is None: return default
        s = str(x).strip()
        if s == "": return default
        return int(float(s))
    except Exception:
        return default

def score_row(r):
    """
    Minimal scoring (MVP):
    - Favor quick time-to-first-dollar
    - Favor high margin, scalability, automation
    - Penalize risk, competition, legal risk, capital required
    Score range approx: 0..100
    """
    ttd  = clamp(to_float(r.get("time_to_first_dollar_days", 14), 14.0), 0.0, 60.0)
    mrg  = clamp(to_float(r.get("expected_margin_pct", 30), 30.0), 0.0, 200.0)  # % margin
    scal = clamp(to_int(r.get("scalability_1to5", 3), 3), 1, 5)
    capr = clamp(to_float(r.get("capital_required", 0), 0.0), 0.0, 5000.0)

    risk = clamp(to_int(r.get("risk_1to5", 3), 3), 1, 5)
    comp = clamp(to_int(r.get("competition_1to5", 3), 3), 1, 5)
    lgl  = clamp(to_int(r.get("legal_risk_1to5", 2), 2), 1, 5)
    aut  = clamp(to_int(r.get("automation_1to5", 3), 3), 1, 5)

    # Normalize components
    # faster is better -> convert ttd to 0..1 where 0 days=1, 30 days~0
    speed = clamp(1.0 - (ttd / 30.0), 0.0, 1.0)

    margin = clamp(mrg / 100.0, 0.0, 2.0)   # 0..2
    scal_n = (scal - 1) / 4.0               # 0..1
    aut_n  = (aut  - 1) / 4.0               # 0..1

    risk_n = (risk - 1) / 4.0               # 0..1
    comp_n = (comp - 1) / 4.0               # 0..1
    lgl_n  = (lgl  - 1) / 4.0               # 0..1

    cap_pen = clamp(capr / 500.0, 0.0, 3.0) # 0..3

    # Weighted sum
    raw = (
        35.0 * speed +
        20.0 * clamp(margin, 0.0, 1.0) +     # cap margin contribution
        15.0 * scal_n +
        10.0 * aut_n
        -
        15.0 * risk_n -
        10.0 * comp_n -
        10.0 * lgl_n
        -
        5.0  * clamp(cap_pen, 0.0, 1.0)
    )

    return round(clamp(raw, 0.0, 100.0), 2)

def main():
    if not os.path.exists(IN_CSV):
        raise SystemExit(f"Missing file: {IN_CSV}")

    with open(IN_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if "score_total" not in fieldnames:
        fieldnames.append("score_total")
    if "updated_at" not in fieldnames:
        fieldnames.append("updated_at")
    if "status" not in fieldnames:
        fieldnames.append("status")

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for r in rows:
        s = score_row(r)
        r["score_total"] = f"{s:.2f}"
        r["updated_at"] = now
        if not (r.get("status") or "").strip():
            r["status"] = "candidate"

    # Sort by score desc (stable)
    def keyfn(r):
        return to_float(r.get("score_total", 0.0), 0.0)

    rows.sort(key=keyfn, reverse=True)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"OK: Scored {len(rows)} opportunities. Updated: {OUT_CSV}")

if __name__ == "__main__":
    main()