import os, json, csv
from datetime import datetime, date
from collections import defaultdict

ROOT = os.environ.get("BRAINLAB_ROOT", r"C:\AI_VAULT")
LEADS = os.path.join(ROOT, r"60_METRICS\leads.csv")
OUTDIR = os.path.join(ROOT, r"50_LOGS\weekly_reports")
STATE = os.path.join(ROOT, r"60_METRICS\brain_state.json")

PRIOR_A = 1.0
PRIOR_B = 9.0

VALID_REPLY = {"replied", "won"}
VALID_SENT  = {"sent"}
VALID_NEG   = {"no_reply", "lost"}

def now_s(): return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
def today_s(): return date.today().strftime("%Y-%m-%d")

def load_csv_rows(path):
    with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
        dr = csv.DictReader(f)
        return list(dr)

def load_state():
    if not os.path.exists(STATE):
        return {
            "version": "bayes_v1",
            "created_at": now_s(),
            "updated_at": now_s(),
            "priors": {"a": PRIOR_A, "b": PRIOR_B},
            "segments": {},
            "campaigns": {},
            "global": {"a": PRIOR_A, "b": PRIOR_B, "n_sent": 0, "n_pos": 0, "n_neg": 0},
            "notes": "Bayesian reply learning. Updates use explicit negatives only."
        }
    with open(STATE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    state["updated_at"] = now_s()
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def mean_beta(a,b):
    return a/(a+b) if (a+b)>0 else 0.0

def update_beta(obj, sent, pos, neg):
    obj["n_sent"] = obj.get("n_sent", 0) + sent
    obj["n_pos"]  = obj.get("n_pos", 0) + pos
    obj["n_neg"]  = obj.get("n_neg", 0) + neg
    obj["a"] = obj.get("a", PRIOR_A) + pos
    obj["b"] = obj.get("b", PRIOR_B) + neg
    return obj

def seg_key(row):
    city = (row.get("city") or "").strip() or "NA"
    src  = (row.get("source") or "").strip() or "NA"
    return f"{src}__{city}"

def camp_key(row):
    c = (row.get("campaign") or "NA").strip()
    return c if c else "NA"

def report_table(items, top=12):
    items_sorted = sorted(items, key=lambda kv: mean_beta(kv[1]["a"], kv[1]["b"]), reverse=True)
    lines = []
    lines.append("| Rank | Key | E[p(reply)] | a | b | sent | pos | neg |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|")
    for i,(k,s) in enumerate(items_sorted[:top], start=1):
        mu = mean_beta(s["a"], s["b"])
        lines.append(f"| {i} | {k} | {mu:.3f} | {s['a']:.1f} | {s['b']:.1f} | {s.get('n_sent',0)} | {s.get('n_pos',0)} | {s.get('n_neg',0)} |")
    return "\n".join(lines)

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    if not os.path.exists(LEADS):
        raise SystemExit(f"Missing: {LEADS}")

    rows = load_csv_rows(LEADS)
    state = load_state()

    global_sent = 0
    global_pos = 0
    global_neg = 0

    seg_obs = defaultdict(lambda: {"sent":0,"pos":0,"neg":0})
    camp_obs = defaultdict(lambda: {"sent":0,"pos":0,"neg":0})

    for r in rows:
        st = (r.get("status") or "").strip().lower()
        seg = seg_key(r)
        camp = camp_key(r)

        if st in VALID_SENT:
            global_sent += 1
            seg_obs[seg]["sent"] += 1
            camp_obs[camp]["sent"] += 1
        elif st in VALID_REPLY:
            global_pos += 1
            seg_obs[seg]["pos"] += 1
            camp_obs[camp]["pos"] += 1
        elif st in VALID_NEG:
            global_neg += 1
            seg_obs[seg]["neg"] += 1
            camp_obs[camp]["neg"] += 1

    state["global"] = update_beta(state.get("global", {"a":PRIOR_A,"b":PRIOR_B}), global_sent, global_pos, global_neg)

    state.setdefault("segments", {})
    for seg, o in seg_obs.items():
        cur = state["segments"].get(seg, {"a":PRIOR_A,"b":PRIOR_B,"n_sent":0,"n_pos":0,"n_neg":0})
        state["segments"][seg] = update_beta(cur, o["sent"], o["pos"], o["neg"])

    state.setdefault("campaigns", {})
    for camp, o in camp_obs.items():
        cur = state["campaigns"].get(camp, {"a":PRIOR_A,"b":PRIOR_B,"n_sent":0,"n_pos":0,"n_neg":0})
        state["campaigns"][camp] = update_beta(cur, o["sent"], o["pos"], o["neg"])

    save_state(state)

    g = state["global"]
    mu_g = mean_beta(g["a"], g["b"])

    rep_path = os.path.join(OUTDIR, f"brain_growth_report_{today_s()}.md")
    lines = []
    lines.append(f"# Brain Growth Report  {today_s()}\\n")
    lines.append(f"Generated: {now_s()}\\n")
    lines.append("## 1) Global Bayesian Belief: p(reply)\\n")
    lines.append(f"- Prior: Beta({PRIOR_A},{PRIOR_B})  (mean{mean_beta(PRIOR_A,PRIOR_B):.3f})")
    lines.append(f"- Posterior: Beta({g['a']:.1f},{g['b']:.1f})  (E[p]{mu_g:.3f})")
    lines.append(f"- Observations (explicit): pos={g.get('n_pos',0)} neg={g.get('n_neg',0)} sent={g.get('n_sent',0)}\\n")
    lines.append("## 2) Top Segments (source__city)\\n")
    lines.append(report_table(list(state["segments"].items()), top=12) + "\\n")
    lines.append("## 3) Campaigns\\n")
    lines.append(report_table(list(state["campaigns"].items()), top=12) + "\\n")

    with open(rep_path, "w", encoding="utf-8") as f:
        f.write("\\n".join(lines))

    print("OK: brain_evaluator executed")
    print("OK: Report:", rep_path)
    print(f"GLOBAL_E_p_reply={mu_g:.3f}")

if __name__ == "__main__":
    main()