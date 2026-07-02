import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
d = json.load(open('tmp_agent/front_brain_agent_v2_identity_guard_and_intent_floor_widen_02/live_benchmark_full_responses.json', encoding='utf-8'))
for pid in ('P3','P5','P13','P16','P17','P19'):
    for b in d['bodies']:
        if b['prompt_id'] == pid:
            r = b['response_body']
            fa = r.get('final_answer') or ''
            print(f'=== {pid} route={r.get("intent_route")} intent={r.get("intent_detected")} tools={len(r.get("tools_executed") or [])} len={len(fa)} ===')
            print(fa[:900])
            print()
            break
