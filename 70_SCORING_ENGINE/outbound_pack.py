import csv, os
from datetime import datetime

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
OUT_DIR = os.path.join(ROOT, r"50_LOGS\weekly_reports")
METRICS_DIR = os.path.join(ROOT, r"60_METRICS")

LEADS_CSV = os.path.join(METRICS_DIR, "leads.csv")

def ensure_dirs():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(METRICS_DIR, exist_ok=True)

def write_leads_template():
    if os.path.exists(LEADS_CSV):
        return False
    headers = ["lead_id","segment","channel","name","company","role","email_or_handle","city","notes","status","created_at"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    # 25 B2B local targets (placeholders)
    for i in range(1, 26):
        rows.append({
            "lead_id": f"L-B2B-{i:03d}",
            "segment":"B2B",
            "channel":"email_or_dm",
            "name": f"Name{i}",
            "company": f"Company{i}",
            "role":"Owner/Manager",
            "email_or_handle": f"lead{i}@example.com",
            "city":"Miami",
            "notes":"replace with real",
            "status":"new",
            "created_at": now
        })
    # 25 platform targets (Upwork/Fiverr style)
    for i in range(1, 26):
        rows.append({
            "lead_id": f"L-PLAT-{i:03d}",
            "segment":"PLATFORM",
            "channel":"platform_dm",
            "name": f"Client{i}",
            "company": "",
            "role":"Buyer",
            "email_or_handle": f"platform_profile_{i}",
            "city":"",
            "notes":"replace with real job post link",
            "status":"new",
            "created_at": now
        })
    with open(LEADS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    return True

def offer_docs(today):
    offers_path = os.path.join(OUT_DIR, f"offers_{today}.md")
    content = []
    content.append(f"# Offers  {today}")
    content.append("")
    content.append("## EXP-A (OPP-003)  Excel Data Cleanup (Express)")
    content.append("- Deliverable: archivo limpio + formatos + validaciones + resumen de cambios")
    content.append("- Turnaround: 24-48h (según tamaño)")
    content.append("- Pricing MVP: $49 (pequeño) / $99 (mediano) / $199 (grande)")
    content.append("- Guarantee: si no mejora claridad/uso, refund parcial negociable")
    content.append("")
    content.append("## EXP-B (OPP-014)  Reporte Semanal Automatizado (B2B Piloto)")
    content.append("- Piloto 7 días: 1 dashboard + 1 reporte semanal automático")
    content.append("- Requiere: fuente de datos (Excel/CSV/Google Sheet) o export")
    content.append("- Pricing MVP: Piloto $99; luego $149-$399/mes según complejidad")
    content.append("- Objetivo: ahorro de tiempo + decisiones más rápidas")
    content.append("")
    content.append("## Control y prueba (evidencia)")
    content.append("- EXP-A: pago recibido + deliverable final")
    content.append("- EXP-B: 5 conversaciones + 1 piloto acordado por escrito")
    with open(offers_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content) + "\n")
    return offers_path

def build_messages(today):
    outbound_path = os.path.join(OUT_DIR, f"outbound_{today}.md")

    msgA = []
    msgB = []

    # EXP-A: Excel cleanup (10 variants)
    for i in range(1, 11):
        msgA.append(
            f"### EXP-A Message {i}\n"
            f"Hola {{NAME}}, vi que muchas empresas pierden tiempo con Excel desordenado.\n"
            f"Yo lo dejo limpio y estandarizado (validaciones, formatos, resumen de cambios) en 24-48h.\n"
            f"Quieres que te haga una muestra gratis con 20 filas (sin compromiso)?\n"
            f"- Cesar\n"
        )

    # EXP-B: Weekly reporting automation (10 variants)
    for i in range(1, 11):
        msgB.append(
            f"### EXP-B Message {i}\n"
            f"Hola {{NAME}}, si cada semana haces reportes manuales, puedo automatizarlos.\n"
            f"Piloto 7 días: 1 dashboard + 1 reporte semanal automático desde tu Excel/CSV.\n"
            f"Te interesa que lo probemos con tus datos esta semana?\n"
            f"- Cesar\n"
        )

    content = []
    content.append(f"# Outbound Pack  {today}")
    content.append("")
    content.append("## Instructions")
    content.append("- Replace {NAME} and tailor 1 line with the lead context.")
    content.append("- Send 10 messages for EXP-A and 10 for EXP-B today.")
    content.append("- Log responses manually into leads.csv status column.")
    content.append("")
    content.append("## EXP-A (OPP-003)  10 Messages")
    content.append("")
    content.extend(msgA)
    content.append("")
    content.append("## EXP-B (OPP-014)  10 Messages")
    content.append("")
    content.extend(msgB)

    with open(outbound_path, "w", encoding="utf-8") as f:
        f.write("\n".join(content) + "\n")

    return outbound_path

def main():
    ensure_dirs()
    today = datetime.now().strftime("%Y-%m-%d")

    created = write_leads_template()
    offers_path = offer_docs(today)
    outbound_path = build_messages(today)

    print(f"OK: offers -> {offers_path}")
    print(f"OK: outbound -> {outbound_path}")
    if created:
        print(f"OK: leads template created -> {LEADS_CSV}")
    else:
        print(f"OK: leads already exists -> {LEADS_CSV}")

if __name__ == "__main__":
    main()