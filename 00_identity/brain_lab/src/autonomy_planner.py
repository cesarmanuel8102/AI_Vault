import os, json, math
from datetime import datetime, timedelta
from src.ethics_kernel import decide

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOV  = os.path.join(ROOT, "governance")
MEM  = os.path.join(ROOT, "memory")
LOGS = os.path.join(ROOT, "logs")
KPI  = os.path.join(ROOT, "kpi")

def now():
    return datetime.utcnow().isoformat() + "Z"

def _load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def generate_ideas():
    """
    Heurístico (sin internet). Genera 10 ideas B2B de alto margen, rápidas de validar.
    NOTA: En la siguiente fase, esto se conecta a investigación real.
    """
    ideas = [
        {"id":"IDEA_01","name":"Reporte diario automatizado (fotos+geo+resumen)","who":"pymes construcción","pain":"reportes manuales + fotos caóticas","solution":"plantilla + pipeline + PDF diario","price_usd":399},
        {"id":"IDEA_02","name":"Dashboard QA/QC simple","who":"contratistas/CEI","pain":"ensayos/tickets dispersos","solution":"tablero + checklist + archivos","price_usd":599},
        {"id":"IDEA_03","name":"Generador de propuestas 1-click","who":"servicios técnicos","pain":"cotizaciones lentas","solution":"plantillas + cálculo + PDF","price_usd":299},
        {"id":"IDEA_04","name":"Sistema de organización de fotos por proyecto","who":"empresas campo","pain":"evidencia pierde valor","solution":"naming + tags + export","price_usd":249},
        {"id":"IDEA_05","name":"Automatización de reportes semanales","who":"pequeñas firmas","pain":"reportes tardan horas","solution":"resumen + KPI + PDF","price_usd":349},
        {"id":"IDEA_06","name":"Kit de SOPs + checklists operativos","who":"equipos pequeños","pain":"procesos inconsistentes","solution":"SOP pack + entrenamiento","price_usd":499},
        {"id":"IDEA_07","name":"Asistente local para documentación (offline)","who":"profesionales campo","pain":"redacción lenta","solution":"plantillas + prompts + QA","price_usd":299},
        {"id":"IDEA_08","name":"Control de cambios y evidencias","who":"proyectos con auditoría","pain":"pérdida de trazabilidad","solution":"registro + hash + logs","price_usd":699},
        {"id":"IDEA_09","name":"Conversión de Excel sucio a sistema limpio","who":"pymes admin","pain":"datos inconsistentes","solution":"normalización + validación","price_usd":199},
        {"id":"IDEA_10","name":"Paquete de automatización PowerShell/Windows","who":"oficinas pequeñas","pain":"PC lenta/archivos caóticos","solution":"scripts + mantenimiento","price_usd":149},
    ]
    return ideas

def score_idea(idea):
    """
    Scoring heurístico inicial (0-10).
    Luego se recalibra por resultados reales.
    """
    # Priorizamos: time_to_first_dollar, margin, scalability, distribution_access, confidence, legal_tos_safety
    # Asignaciones heurísticas por tipo
    base = {
        "time_to_first_dollar": 7,
        "margin": 7,
        "scalability": 6,
        "distribution_access": 6,
        "confidence": 6,
        "legal_tos_safety": 9
    }

    name = (idea.get("name","").lower())
    if "automat" in name or "generador" in name:
        base["scalability"] += 1
    if "dashboard" in name or "control" in name:
        base["price_power"] = 7
    if "paquete" in name or "kit" in name:
        base["time_to_first_dollar"] += 1
    if idea.get("price_usd",0) >= 599:
        base["margin"] += 1

    # clamp 0..10
    for k in list(base.keys()):
        if isinstance(base[k], (int,float)):
            base[k] = max(0, min(10, base[k]))

    # Weighted total
    weights = {
        "time_to_first_dollar": 0.22,
        "margin": 0.18,
        "scalability": 0.16,
        "distribution_access": 0.16,
        "confidence": 0.12,
        "legal_tos_safety": 0.16
    }
    total = 0.0
    for k,w in weights.items():
        total += float(base.get(k,0))*float(w)

    return base, round(total, 4)

def propose_actions_week1(idea):
    # acciones de validación real (sin spam), 1:1
    return [
        {
            "action":"research",
            "description":f"Construir lista de 20 prospectos de {idea['who']} (1:1), con criterio y fuente pública.",
            "money_move":False,
            "evidence":"manual list build / public sources / no scraping ilegal"
        },
        {
            "action":"build_asset",
            "description":f"Crear 1-pager de oferta '{idea['name']}' con entregable, precio ${idea['price_usd']} y garantía/alcance.",
            "money_move":False,
            "evidence":"documento interno"
        },
        {
            "action":"draft_email_1to1",
            "description":"Redactar email 1:1 personalizado con opt-out para solicitar llamada de 10 min.",
            "channels":["email"],
            "money_move":False,
            "evidence":"contacto directo / opt-in / contacto previo"
        }
    ]

def build_plan_14d(top2):
    start = datetime.utcnow().date()
    plan = []
    for i, idea in enumerate(top2, start=1):
        actions = propose_actions_week1(idea)
        gated = []
        for a in actions:
            gated.append({"proposal":a, "ethics":decide(a)})
        # plan 14d simple: 1-2 acciones diarias
        days = []
        for d in range(1, 15):
            day_date = start + timedelta(days=d-1)
            if d == 1:
                day_actions = ["research: obtener 20 leads 1:1"]
            elif d == 2:
                day_actions = ["build_asset: 1-pager oferta + pricing"]
            elif d == 3:
                day_actions = ["draft_email_1to1: plantilla base + 5 variantes"]
            elif 4 <= d <= 10:
                day_actions = [f"outreach_1to1: enviar 3-5 mensajes personalizados (no spam)"]
            elif d == 11:
                day_actions = ["followup_1to1: seguimiento respetuoso + opt-out"]
            elif d == 12:
                day_actions = ["proposal: preparar 1 propuesta real si hay interés"]
            elif d == 13:
                day_actions = ["close: agendar llamada / cierre inicial"]
            else:
                day_actions = ["review: métricas + post-mortem + ajustes"]

            days.append({
                "day": d,
                "date": str(day_date),
                "actions": day_actions,
                "kpi_target": {
                    "outreach_sent": 5 if 4 <= d <= 10 else 0,
                    "responses": 1 if d in (5,7,9,11,14) else 0,
                    "calls_booked": 1 if d in (8,12,13,14) else 0,
                    "proposals_sent": 1 if d in (12,13,14) else 0
                }
            })

        plan.append({
            "rank": i,
            "idea": idea,
            "week1_actions_gated": gated,
            "plan_14d": days
        })
    return {"ts": now(), "top2_plan": plan}

def main():
    ideas = generate_ideas()
    ranked = []
    for idea in ideas:
        scores, total = score_idea(idea)
        ranked.append({**idea, "scores": scores, "total": total})

    ranked.sort(key=lambda x: x["total"], reverse=True)
    top2 = ranked[:2]

    out = {
        "ts": now(),
        "ranked": ranked,
        "top2": top2,
        "plan14d": build_plan_14d(top2)
    }

    _save_json(os.path.join(MEM, "ranked_ideas.json"), out)
    _append_jsonl(os.path.join(LOGS, "planner_runs.jsonl"), {"ts": now(), "top2":[t["id"] for t in top2]})
    print(json.dumps(out["plan14d"], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
