"""
Smoke test for FRONT-BRAIN-AGENT-V2-8092-REBOOT-RECOVERY-DASHBOARD-CONSOLIDATION-01
"""
import json, os, sys, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
EVIDENCE = os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_8092_reboot_recovery_dashboard_consolidation_01')

def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_evidence_dir_exists():
    assert os.path.isdir(EVIDENCE)

def test_state_lock_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_lock.json'))

def test_memory_baseline_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))

def test_pre_reboot_forensics_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'pre_reboot_8092_forensics.json'))

def test_operator_live_test_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'operator_live_test.json'))

def test_8091_health():
    with urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=10) as r:
        assert r.status == 200

def test_8091_agent_status():
    with urllib.request.urlopen('http://127.0.0.1:8091/v2/agent/status', timeout=10) as r:
        data = json.loads(r.read().decode())
        assert data['ok'] is True
        assert data['canonical_for_new_agent_runs'] is True

def test_8091_capabilities():
    with urllib.request.urlopen('http://127.0.0.1:8091/v2/agent/capabilities', timeout=10) as r:
        data = json.loads(r.read().decode())
        assert data['ok'] is True

def test_8091_chat_agent():
    req = urllib.request.Request('http://127.0.0.1:8091/v2/chat/agent', data=json.dumps({'message': 'Hello from smoke test', 'mode': 'read_only', 'user_id': 'smoke'}).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
        assert data['ok'] is True
        assert data['run_id'].startswith('agv2_')

def test_8091_trace():
    req = urllib.request.Request('http://127.0.0.1:8091/v2/chat/agent', data=json.dumps({'message': 'Smoke test', 'mode': 'read_only', 'user_id': 'smoke_trace'}).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
        run_id = data['run_id']
    trace_url = f'http://127.0.0.1:8091/v2/agent/runs/{run_id}/trace'
    with urllib.request.urlopen(trace_url, timeout=10) as r:
        trace = json.loads(r.read().decode())
        assert trace['ok'] is True
        assert trace['event_count'] > 0
        assert 'trace' in trace

def test_8092_dashboard_status():
    with urllib.request.urlopen('http://127.0.0.1:8092/brain-dashboard/status', timeout=10) as r:
        data = json.loads(r.read().decode())
        assert data['dashboard'] == 'online' or data.get('ok') is True

def test_8092_agent_v2_status():
    with urllib.request.urlopen('http://127.0.0.1:8092/brain-dashboard/agent-v2/status', timeout=10) as r:
        data = json.loads(r.read().decode())
        assert data['ok'] is True
        assert data['agent_v2']['canonical_for_new_agent_runs'] is True

def test_memory_faiss_unchanged():
    baseline = _read_json(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))
    import faiss
    idx = faiss.read_index(os.path.join(ROOT, 'memory/semantic/semantic_memory_faiss.index'))
    assert idx.ntotal == baseline['faiss_ntotal']
    with open(os.path.join(ROOT, 'memory/semantic/semantic_memory.jsonl'), 'rb') as f:
        lines = f.read().decode('utf-8', errors='replace').count('\n')
    assert lines == baseline['semantic_jsonl']['lines_or_bytes']

def test_roadmap_updated():
    data = _read_json(os.path.join(ROOT, 'ROADMAP_STATUS.json'))
    assert any('8092' in k or 'dashboard' in k for k in data.keys())

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
