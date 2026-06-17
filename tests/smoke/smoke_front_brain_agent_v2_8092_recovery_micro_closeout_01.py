"""Smoke for FRONT-BRAIN-AGENT-V2-8092-RECOVERY-MICRO-CLOSEOUT-01"""
import json, os, sys, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
EVIDENCE = os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_8092_recovery_micro_closeout_01')
PREV = os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_8092_reboot_recovery_dashboard_consolidation_01')

def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_micro_state_lock():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_lock.json'))

def test_micro_functional_reconf():
    assert os.path.exists(os.path.join(EVIDENCE, 'functional_reconfirmation.json'))

def test_micro_memory_final():
    assert os.path.exists(os.path.join(EVIDENCE, 'memory_faiss_final.json'))

def test_micro_git_incident():
    assert os.path.exists(os.path.join(EVIDENCE, 'git_incident_review.json'))

def test_prev_front_missing_evidence():
    assert os.path.exists(os.path.join(PREV, 'reboot_decision.json'))
    assert os.path.exists(os.path.join(PREV, 'post_reboot_stack_start.json'))
    assert os.path.exists(os.path.join(PREV, 'dashboard_consolidation_audit.json'))
    assert os.path.exists(os.path.join(PREV, 'memory_faiss_final.json'))
    assert os.path.exists(os.path.join(PREV, 'smoke_results.json'))
    assert os.path.exists(os.path.join(PREV, 'post_push_verification.json'))

def test_8092_agent_v2_status():
    with urllib.request.urlopen('http://127.0.0.1:8092/brain-dashboard/agent-v2/status', timeout=10) as r:
        data = json.loads(r.read().decode())
        assert data['ok'] is True
        assert data['agent_v2']['canonical_for_new_agent_runs'] is True

def test_8091_chat():
    req = urllib.request.Request('http://127.0.0.1:8091/v2/chat/agent', data=json.dumps({'message': 'Micro-closeout test', 'mode': 'read_only', 'user_id': 'micro'}).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
        assert data['ok'] is True
        run_id = data['run_id']
    with urllib.request.urlopen(f'http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace', timeout=10) as r:
        trace = json.loads(r.read().decode())
        assert trace['event_count'] > 0

def test_memory_faiss_unchanged():
    baseline = _read_json(os.path.join(EVIDENCE, 'memory_faiss_final.json'))
    import faiss
    idx = faiss.read_index(os.path.join(ROOT, 'memory/semantic/semantic_memory_faiss.index'))
    assert idx.ntotal == baseline['faiss_ntotal']
    with open(os.path.join(ROOT, 'memory/semantic/semantic_memory.jsonl'), 'rb') as f:
        lines = f.read().decode('utf-8', errors='replace').count('\n')
    assert lines == baseline['semantic_jsonl']['lines_or_bytes']

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
