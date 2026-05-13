$env:PYTHONPATH = 'C:/AI_VAULT/tmp_agent'
python -c "
from brain_v9.autonomy.chat_excellence_executor import evaluate_iteration, stats
import json

# Synthetic iter: solo core/llm.py (no sacred), low-risk language
synth = {
    'iter': 999,
    'timestamp': '2026-05-04T13:30:00',
    'parsed_ok': True,
    'weakness': 'Circuit breaker too aggressive',
    'impact_score': 8,
    'root_cause_guess': 'Threshold of 2 fails too quickly',
    'proposed_change': 'Adjust _CB_FAIL_THRESHOLD constant in core/llm.py from 2 to 4 to allow more transient failures before opening the breaker.',
    'test_plan': 'Monitor circuit_breaker.models for 1 hour',
    'expected_improvement': 'fewer false-positive breaker opens',
    'affected_files': ['core/llm.py'],
    'affected_files_invalid': [],
    'affected_files_validated': True,
    'status': 'documented',
}
r = evaluate_iteration(synth)
print(json.dumps({'status': r.get('status'), 'risk_class': r.get('risk_class'),
                  'risk_reasons': r.get('risk_reasons'),
                  'proposal_id': r.get('proposal_id')}, indent=2))
print()
print('STATS:', json.dumps(stats(), indent=2))
"
