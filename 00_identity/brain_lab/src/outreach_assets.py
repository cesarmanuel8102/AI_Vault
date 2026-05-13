import os, json
from datetime import datetime

ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM   = os.path.join(ROOT, "memory")
OUT   = os.path.join(MEM, "outreach")
READY = os.path.join(OUT, "ready")

def _w(path, txt):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)

def generate_assets():
    os.makedirs(OUT, exist_ok=True)

    # --- IDEA 10 ---
    idea10 = [
("IDEA_10_email_01.txt","SUBJECT: Te ayudo a recuperar rendimiento en Windows en 48h?\n\nHola {name},\n\nEn oficinas pequeñas suele pasar: PCs lentas con el tiempo, archivos caóticos y tareas repetitivas.\nYo hago un paquete rápido (4872h) para dejar Windows estable + 3 automatizaciones en PowerShell.\n\nIncluye:\n- Diagnóstico (disco/RAM/startup)\n- Limpieza + recomendaciones\n- 3 scripts personalizados (backup/limpieza/orden)\n- Checklist mensual (10 min)\n\nPrecio fijo: $149. Si no notas mejora o no te queda una automatización útil, devuelvo 100%.\n\nTienes 10 min esta semana?\n\nSi no te interesa, dime no y cierro.\n{sender}\n"),
("IDEA_10_email_02.txt","SUBJECT: Arreglo rápido: PC lenta + archivos caóticos (sin cambiar hardware)\n\nHola {name},\n\nTienen alguna PC que se pone lenta con el tiempo? Tengo un paquete corto para optimizar Windows y automatizar lo básico con PowerShell.\n\nTe interesa 10 min para decirte si aplica? (Si no, dime no y listo.)\n{sender}\n"),
("IDEA_10_email_03.txt","SUBJECT: 3 automatizaciones simples para tu oficina (Windows)\n\nHola {name},\n\nTrabajo con oficinas pequeñas que pierden tiempo en backups manuales, limpieza y buscar archivos.\nLo convierto en apretar un botón con 3 scripts y un mantenimiento base.\n\n$149, entrega 4872h.\nTe paso un 1-pager?\n{sender}\n"),
("IDEA_10_email_04.txt","SUBJECT: Optimización Windows sin interrupciones\n\nHola {name},\n\nSi usas Windows, casi siempre hay ganancias rápidas:\n- quitar procesos que frenan\n- automatizar backups\n- ordenar por proyecto\n\nLo hago como paquete fijo con garantía.\n10 min para ver si vale la pena en tu caso?\n{sender}\n"),
("IDEA_10_email_05.txt","SUBJECT: Mantenimiento + automatización (paquete fijo)\n\nHola {name},\n\nTe escribo 1:1 (no lista). Ofrezco un paquete pequeño: optimización Windows + automatización PowerShell.\nNo toco data sensible sin permiso y dejo todo documentado.\n\n10 min esta semana? Si no, dime no y cierro.\n{sender}\n")
    ]

    # --- IDEA 06 ---
    idea06 = [
("IDEA_06_email_01.txt","SUBJECT: Kit de SOPs + checklists para reducir errores en 14 días\n\nHola {name},\n\nEn equipos pequeños suele pasar: procesos inconsistentes y errores repetidos.\nYo preparo un Kit de SOPs + checklists (5 días) sin burocracia:\n- 8 SOPs base\n- 10 checklists\n- plantillas de seguimiento\n- sesión 45 min implementación\n\n$499. Si en 14 días no mejora tiempo/errores (según KPI), ajusto sin costo.\n\n10 min para ver si aplica?\nSi no, dime no y cierro.\n{sender}\n"),
("IDEA_06_email_02.txt","SUBJECT: Estandarizar sin burocracia\n\nHola {name},\n\nTienes procesos que dependen de la memoria de alguien?\nCreo SOPs cortos + checklists para que el equipo ejecute igual siempre.\n\nEntrega 5 días, $499.\nHablamos 10 min?\n{sender}\n"),
("IDEA_06_email_03.txt","SUBJECT: Checklists simples para equipos pequeños\n\nHola {name},\n\nEstoy probando un kit SOP + checklists + plantillas.\nMeta: bajar errores repetidos y tiempo perdido en 14 días.\n\nTe paso un ejemplo y si te sirve hablamos 10 min?\n{sender}\n"),
("IDEA_06_email_04.txt","SUBJECT: Menos errores repetidos\n\nHola {name},\n\nSi tienes gente nueva o rotación, SOPs ligeros ahorran tiempo.\nYo los dejo listos + sesión breve.\n\n10 min para ver tu caso?\n{sender}\n"),
("IDEA_06_email_05.txt","SUBJECT: SOPs + plantillas + control semanal\n\nHola {name},\n\nTe escribo 1:1 (no spam). Tengo un kit SOP + checklists para estandarizar sin volverse lento.\nSi no te interesa, dime no y listo.\n\n10 min esta semana?\n{sender}\n")
    ]

    followups = [
("followup_d2.txt","Hola {name},\n\nSolo confirmo si viste mi mensaje anterior.\nSi no es prioridad ahora, perfectodime no y cierro.\n\n{sender}\n"),
("followup_d5.txt","Hola {name},\n\nÚltimo intento por aquí.\nSi te interesa, te envío un 1-pager con alcance/precio.\nSi no, dime no y no vuelvo a escribir.\n\n{sender}\n"),
("followup_d9.txt","Hola {name},\n\nCierro el hilo para no molestar.\nSi en el futuro lo necesitas, con gusto.\n\n{sender}\n")
    ]

    call_script = """GUION LLAMADA 10 MIN (validación)
1) Contexto (30s)
   "Gracias. Solo quiero entender si esto te ahorra tiempo/dinero. Si no aplica, lo dejamos."

2) Diagnóstico (3 min)
   - Cuál es el problema más molesto hoy?
   - Con qué frecuencia ocurre?
   - Cuánto tiempo cuesta por semana?
   - Quién se ve afectado?

3) Criterio de decisión (2 min)
   - Si se arregla, qué cambia?
   - Qué presupuesto usan para resolverlo?
   - Quién decide?

4) Oferta mínima (2 min)
   - Resumo alcance + garantía
   - Precio fijo
   - Próximo paso: 1-pager + agendar implementación

5) Cierre (30s)
   - "Te lo mando por email y agendamos?"
"""

    for fn, txt in idea10 + idea06 + followups:
        _w(os.path.join(OUT, fn), txt)
    _w(os.path.join(OUT, "call_script_10min.txt"), call_script)

def personalize_from_leads(sender="Cesar"):
    os.makedirs(READY, exist_ok=True)
    leads_path = os.path.join(MEM, "leads_day1.json")
    if not os.path.exists(leads_path):
        return {"ok": False, "error": f"missing {leads_path}"}

    with open(leads_path, "r", encoding="utf-8-sig") as f:
        leads = json.load(f)

    # pick default template (IDEA_10 email 01) for now
    base_path = os.path.join(OUT, "IDEA_10_email_01.txt")
    with open(base_path, "r", encoding="utf-8-sig") as f:
        base = f.read()

    created = 0
    for lead in leads:
        email = (lead.get("email") or "").strip()
        name  = (lead.get("contact_name") or lead.get("business_name") or "hola").strip()
        if not email:
            continue
        msg = base.replace("{name}", name).replace("{sender}", sender)
        outp = os.path.join(READY, f"{lead.get('id','LEAD')}_email.txt")
        _w(outp, msg)
        created += 1

    return {"ok": True, "created": created, "ready_dir": READY}

if __name__ == "__main__":
    generate_assets()
    print("OK assets generated:", OUT)
