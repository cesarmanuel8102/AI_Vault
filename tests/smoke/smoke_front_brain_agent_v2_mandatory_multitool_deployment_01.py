"""Smoke test for FRONT-BRAIN-AGENT-V2-MANDATORY-MULTITOOL-DEPLOYMENT-01"""
import json, os, sys, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
EVIDENCE = os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_mandatory_multitool_deployment_01')

def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_evidence_dir_exists():
    assert os.path.isdir(EVIDENCE)

def test_state_lock():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_lock.json'))

def test_memory_baseline():
    assert os.path.exists(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))

def test_operator_presets():
    assert os.path.exists(os.path.join(EVIDENCE, 'operator_presets.json'))
    data = _read_json(os.path.join(EVIDENCE, 'operator_presets.json'))
    assert data['presets_defined'] >= 8

def test_preset_registry_code_exists():
    assert os.path.exists(os.path.join(ROOT, 'tmp_agent/brain_v9/core/agent_kernel_v2/operator_presets.py'))

def test_preset_route_code_exists():
    with open(os.path.join(ROOT, 'tmp_agent/brain_v9/core/agent_kernel_v2/api_adapter.py'), 'r') as f:
        assert '/operator-presets' in f.read()

def test_live_preset_results():
    assert os.path.exists(os.path.join(EVIDENCE, 'live_preset_execution_results.json'))
    data = _read_json(os.path.join(EVIDENCE, 'live_preset_execution_results.json'))
    assert len(data['results']) >= 8
    passed = sum(1 for r in data['results'] if r['status'] == 'passed')
    assert passed >= 8
    kimi_runs = sum(1 for r in data['results'] if 'kimi' in (r.get('model_used') or ''))
    assert kimi_runs >= 1

def test_mandatory_selftest_classification():
    data = _read_json(os.path.join(EVIDENCE, 'live_preset_execution_results.json'))
    mt = [r for r in data['results'] if r['preset'] == 'mandatory_multitool_selftest'][0]
    assert mt['classification'] == 'mandatory_multitool'

def test_governance_block_test():
    data = _read_json(os.path.join(EVIDENCE, 'live_preset_execution_results.json'))
    gt = [r for r in data['results'] if r['preset'] == 'governance_block_test'][0]
    assert gt['status'] == 'passed'
    assert gt['trace_event_count'] > 0

def test_operator_usage_check():
    assert os.path.exists(os.path.join(EVIDENCE, 'operator_usage_check.json'))

def test_governance_safety_audit():
    assert os.path.exists(os.path.join(EVIDENCE, 'governance_safety_audit.json'))
    data = _read_json(os.path.join(EVIDENCE, 'governance_safety_audit.json'))
    assert data['governance_checks']['raw_cot_in_final_answers'] is False
    assert data['governance_checks']['secrets_leaked'] is False
    assert data['governance_checks']['semantic_faiss_mutated'] is False

def test_8091_agent_status():
    with urllib.request.urlopen('http://127.0.0.1:8091/v2/agent/status', timeout=10) as r:
        data = json.loads(r.read().decode())
        assert data['ok'] is True
        assert data['canonical_for_new_agent_runs'] is True

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
    assert any('deployment' in k for k in data.keys())

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
