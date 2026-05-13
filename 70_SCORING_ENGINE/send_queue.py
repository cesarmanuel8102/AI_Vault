import os, csv, re, ssl, smtplib
from email.message import EmailMessage
from datetime import datetime

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
LEADS = os.path.join(ROOT, r"60_METRICS\leads.csv")
LOGDIR = os.path.join(ROOT, r"50_LOGS\decisions")
LOG = os.path.join(LOGDIR, "outreach_actions.log")

SMTP_HOST = os.environ.get("BRAIN_SMTP_HOST","")
SMTP_PORT = int(os.environ.get("BRAIN_SMTP_PORT","0") or "0")
SMTP_USER = os.environ.get("BRAIN_SMTP_USER","")
SMTP_PASS = os.environ.get("BRAIN_SMTP_PASS","")
FROM_HDR  = os.environ.get("BRAIN_SMTP_FROM","Cesar")

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)

def norm(s): return re.sub(r"\s+"," ", (s or "").strip())
def now(): return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def log(line):
    os.makedirs(LOGDIR, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{now()}] {line}\n")

def load_rows():
    with open(LEADS, "r", newline="", encoding="utf-8", errors="ignore") as f:
        dr = csv.DictReader(f)
        rows = list(dr)
        fields = dr.fieldnames or []
    for c in ["last_update_at","last_note","subject_last","campaign"]:
        if c not in fields:
            fields.append(c)
    for r in rows:
        for c in fields:
            if c not in r or r[c] is None:
                r[c] = ""
    return rows, fields

def save_rows(fields, rows):
    with open(LEADS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def email_template(company, city):
    company = company or "tu negocio"
    city = city or "tu zona"
    subject = f"Piloto 7 días: reporte semanal automático ({city})"
    body = (
        f"Hola {company},\n\n"
        f"Si cada semana haces reportes manuales, puedo automatizarlos.\n"
        f"Piloto 7 días: 1 dashboard + 1 reporte semanal automático desde tu Excel/CSV.\n\n"
        f"Te interesa probarlo esta semana?\n\n"
        f"- Cesar\n"
        f"(Si no deseas más mensajes, responde 'STOP')\n"
    )
    return subject, body

def send_email(to_email, subject, body):
    msg = EmailMessage()
    msg["From"] = FROM_HDR
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

def main():
    if not os.path.exists(LEADS):
        raise SystemExit(f"Missing: {LEADS}")
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASS):
        raise SystemExit("Missing SMTP env vars.")
    rows, fields = load_rows()
    queued = [r for r in rows if (r.get("status","") or "").lower() == "queued"]
    if not queued:
        print("No queued leads to send.")
        return
    sent=0; needs=0; failed=0
    for r in queued:
        lead_id = norm(r.get("lead_id",""))
        handle  = norm(r.get("email_or_handle",""))
        company = norm(r.get("company",""))
        city    = norm(r.get("city",""))
        r["campaign"]="EXP-B"
        if not EMAIL_RE.match(handle):
            r["status"]="needs_enrichment"
            r["last_update_at"]=now()
            r["last_note"]="autopilot: no email (website/phone)  queued for enrichment"
            log(f"NEEDS_ENRICH lead_id={lead_id} handle={handle}")
            needs += 1
            continue
        subject, body = email_template(company, city)
        try:
            send_email(handle, subject, body)
            r["status"]="sent"
            r["last_update_at"]=now()
            r["last_note"]="autopilot: sent via gmail smtp"
            r["subject_last"]=subject
            log(f"SENT lead_id={lead_id} to={handle}")
            sent += 1
        except Exception as e:
            r["status"]="followup"
            r["last_update_at"]=now()
            r["last_note"]=f"autopilot: send_failed {e.__class__.__name__}"
            log(f"FAIL lead_id={lead_id} to={handle} err={e.__class__.__name__}")
            failed += 1
    save_rows(fields, rows)
    print(f"OK: queued={len(queued)} sent={sent} needs_enrichment={needs} failed={failed}")
    print(f"LOG: {LOG}")

if __name__ == "__main__":
    main()