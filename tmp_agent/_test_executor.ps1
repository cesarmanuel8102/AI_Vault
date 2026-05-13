$env:PYTHONPATH = 'C:/AI_VAULT/tmp_agent'
python -c "
import json
from brain_v9.autonomy.chat_excellence_executor import evaluate_iteration, list_proposals, stats
h = json.load(open('C:/AI_VAULT/tmp_agent/state/chat_excellence_history.json','r',encoding='utf-8'))
it6 = [x for x in h if x.get('iter')==6][0]
print('=== Running evaluate_iteration on iter#6 ===')
r = evaluate_iteration(it6)
print(json.dumps(r, indent=2, ensure_ascii=False))
print()
print('=== Stats ===')
print(json.dumps(stats(), indent=2))
print()
print('=== List proposals ===')
for p in list_proposals(limit=5):
    print(' -', p.get('proposal_id'), 'status=', p.get('status'), 'risk=', p.get('risk_class'),
          'iter=', p.get('iter'), 'files=', p.get('affected_files'))
"
