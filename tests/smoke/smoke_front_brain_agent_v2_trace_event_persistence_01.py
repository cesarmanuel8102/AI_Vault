"""
Smoke test for FRONT-BRAIN-AGENT-V2-TRACE-EVENT-PERSISTENCE-01
"""
import json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
EVIDENCE = os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_trace_event_persistence_01')

def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_evidence_dir_exists():
    assert os.path.isdir(EVIDENCE)

def test_state_lock_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_lock.json'))

def test_memory_baseline_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))

def test_root_cause_audit_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'root_cause_audit.json'))

def test_simple_trace_exists():
    data = _read_json(os.path.join(EVIDENCE, 'simple_trace_retest.json'))
    assert data['result']['trace_ok'] is True
    assert data['result']['event_count'] > 0

def test_mandatory_trace_exists():
    data = _read_json(os.path.join(EVIDENCE, 'mandatory_trace_retest.json'))
    assert data['result']['trace_ok'] is True
    assert data['result']['event_count'] >= 10
    assert 'mandatory_multitool' == data['result']['classification']

def test_mandatory_trace_includes_route_probe():
    data = _read_json(os.path.join(EVIDENCE, 'mandatory_trace_retest.json'))
    assert 'route_probe' in data['result']['tools_started']

def test_mandatory_trace_includes_repo_status():
    data = _read_json(os.path.join(EVIDENCE, 'mandatory_trace_retest.json'))
    assert 'repo_status_read' in data['result']['tools_started']

def test_mandatory_trace_includes_grep_search():
    data = _read_json(os.path.join(EVIDENCE, 'mandatory_trace_retest.json'))
    assert 'grep_search' in data['result']['tools_started']

def test_mandatory_trace_includes_semantic_retrieve():
    data = _read_json(os.path.join(EVIDENCE, 'mandatory_trace_retest.json'))
    # semantic_retrieve shows as memory_retrieval_started in events
    assert 'memory_retrieval_started' in data['result']['event_types']

def test_trace_includes_final_answer_created():
    data = _read_json(os.path.join(EVIDENCE, 'mandatory_trace_retest.json'))
    assert 'final_answer_created' in data['result']['event_types']

def test_trace_includes_run_completed():
    data = _read_json(os.path.join(EVIDENCE, 'mandatory_trace_retest.json'))
    assert 'run_completed' in data['result']['event_types']

def test_blocked_tool_trace_exists():
    data = _read_json(os.path.join(EVIDENCE, 'blocked_tool_trace_retest.json'))
    assert data['result']['trace_ok'] is True

def test_blocked_trace_has_approval_or_blocked():
    data = _read_json(os.path.join(EVIDENCE, 'blocked_tool_trace_retest.json'))
    assert data['result']['blocked_events'] >= 1

def test_no_raw_cot_in_trace():
    # Check simple trace for raw CoT markers
    data = _read_json(os.path.join(EVIDENCE, 'simple_trace_retest.json'))
    for et in data['result']['event_types']:
        assert 'chain-of-thought' not in et
        assert 'hidden reasoning' not in et
        assert 'scratchpad' not in et

def test_memory_faiss_unchanged():
    baseline = _read_json(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))
    import faiss
    idx = faiss.read_index(os.path.join(ROOT, 'memory/semantic/semantic_memory_faiss.index'))
    assert idx.ntotal == baseline['faiss_ntotal']
    with open(os.path.join(ROOT, 'memory/semantic/semantic_memory.jsonl'), 'rb') as f:
        lines = f.read().decode('utf-8', errors='replace').count('\n')
    assert lines == baseline['semantic_jsonl_lines']

def test_roadmap_updated():
    data = _read_json(os.path.join(ROOT, 'ROADMAP_STATUS.json'))
    assert any('trace' in k for k in data.keys())

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
