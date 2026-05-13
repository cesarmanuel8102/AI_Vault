import os, csv, re
from datetime import datetime

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
LEADS = os.path.join(ROOT, r"60_METRICS\leads.csv")
LOGDIR = os.path.join(ROOT, r"50_LOGS\decisions")
LOG = os.path.join(LOGDIR, "leads_actions.log")

ALLOWED = {"new","queued","sent","replied","won","lost","dead","no_reply","followup"}

def norm(s): return re.sub(r"\s+"," ", (s or "").strip())

def load_rows(path):
    with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
        dr = csv.DictReader(f)
        rows = list(dr)
        fields = dr.fieldnames or []
    return rows, fields

def save_rows(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def main():
    import sys
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python mark_lead.py <LEAD_ID> <STATUS> [NOTE]")

    lead_id = norm(sys.argv[1])
    status = norm(sys.argv[2]).lower()
    note = norm(" ".join(sys.argv[3:])) if len(sys.argv) > 3 else ""

    if status not in ALLOWED:
        raise SystemExit(f"Invalid status '{status}'. Allowed: {sorted(ALLOWED)}")

    if not os.path.exists(LEADS):
        raise SystemExit(f"Missing leads file: {LEADS}")

    os.makedirs(LOGDIR, exist_ok=True)

    rows, fields = load_rows(LEADS)
    if "last_update_at" not in fields:
        fields.append("last_update_at")
    if "last_note" not in fields:
        fields.append("last_note")

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    found = 0
    for r in rows:
        if norm(r.get("lead_id","")) == lead_id:
            old = (r.get("status","") or "").lower()
            r["status"] = status
            r["last_update_at"] = now
            if note:
                r["last_note"] = note
            found = 1
            # log
            with open(LOG, "a", encoding="utf-8") as lf:
                lf.write(f"[{now}] LEAD_STATUS lead_id={lead_id} {old}->{status} note={note}\n")
            break

    if not found:
        raise SystemExit(f"Lead not found: {lead_id}")

    save_rows(LEADS, fields, rows)
    print(f"OK: {lead_id} status={status} saved")
    print(f"LEADS: {LEADS}")
    print(f"LOG:   {LOG}")

if __name__ == "__main__":
    main()