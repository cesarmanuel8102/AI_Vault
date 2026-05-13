import os, json
from datetime import datetime
from src.ethics_kernel import decide

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def now():
    return datetime.utcnow().isoformat() + "Z"

def score(idea):
    weights = {
        "time_to_first_dollar": 0.2,
        "margin": 0.2,
        "scalability": 0.2,
        "distribution_access": 0.2,
        "confidence": 0.2
    }
    total = 0.0
    for k, w in weights.items():
        total += float(idea["scores"].get(k, 0)) * float(w)
    return round(total, 3)

def plan(ideas):
    ranked = sorted(ideas, key=lambda x: score(x), reverse=True)
    top = ranked[:2]
    result = []
    for idea in top:
        actions = [
            {
                "action":"draft_email_1to1",
                "description":"Enviar email 1:1 personalizado con opt-out",
                "channels":["email"],
                "money_move":False,
                "evidence":"contacto directo / opt-in / contacto previo"
            }
        ]
        gated = []
        for a in actions:
            gated.append({"proposal":a,"ethics":decide(a)})
        result.append({
            "idea":idea.get("id","?"),
            "score":score(idea),
            "actions":gated
        })
    return {"ts":now(),"plan":result}

if __name__ == "__main__":
    path = os.path.join(ROOT,"memory","ideas_input.json")
    with open(path, "r", encoding="utf-8-sig") as f:
        ideas = json.load(f)
    print(json.dumps(plan(ideas), indent=2, ensure_ascii=False))
