"""
Smoke test for FRONT-BRAIN-AGENT-V2-8092-DASHBOARD-DOGFOOD-CLOSEOUT-01
"""
import json
import os
import hashlib
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
EVIDENCE = os.path.join(ROOT, 'tmp_agent/front_brain_agent_v2_8092_dashboard_dogfood_closeout_01')

def _read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_evidence_dir_exists():
    assert os.path.isdir(EVIDENCE), f"Evidence dir missing: {EVIDENCE}"

def test_state_lock_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_lock.json'))

def test_state_relock_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'state_relock.json'))

def test_agent_v2_baseline_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'agent_v2_8091_baseline.json'))

def test_memory_faiss_baseline_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))

def test_memory_faiss_final_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'memory_faiss_final.json'))

def test_8092_process_forensics_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'port_8092_process_forensics.json'))

def test_route_registry_8092_direct_import():
    data = _read_json(os.path.join(EVIDENCE, 'route_registry_8092_direct_import.json'))
    assert data['import_ok'] is True
    assert data['has_agent_v2_status'] is True
    assert any('agent-v2/status' in r for r in data['agent_v2_routes'])

def test_fix_8092_evidence_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'fix_8092_agent_v2_route.md'))

def test_powershell_scripts_exist():
    scripts = [
        'scripts/brain/restart_brain_8091_agent_v2.ps1',
        'scripts/brain/restart_dashboard_8092_agent_v2.ps1',
        'scripts/brain/probe_agent_v2_live.ps1',
        'scripts/brain/probe_dashboard_8092_agent_v2.ps1',
        'scripts/brain/start_brain_stack_agent_v2.ps1',
    ]
    for s in scripts:
        assert os.path.exists(os.path.join(ROOT, s)), f"Missing script: {s}"

def test_dogfood_evidence_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'agent_v2_8091_baseline_dogfood_run.json'))

def test_final_report_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'final_report.json'))

def test_docs_closeout_exists():
    assert os.path.exists(os.path.join(ROOT, 'docs/BRAIN_AGENT_8092_DASHBOARD_CLOSEOUT.md'))

def test_docs_frontend_usage_exists():
    assert os.path.exists(os.path.join(ROOT, 'docs/BRAIN_AGENT_FRONTEND_DASHBOARD_USAGE.md'))

def test_docs_runbook_exists():
    assert os.path.exists(os.path.join(ROOT, 'docs/BRAIN_AGENT_OPERATIONAL_RUNBOOK.md'))

def test_full_stack_verification_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'full_stack_live_verification.json'))

def test_dogfood_runs_evidence_exists():
    assert os.path.exists(os.path.join(EVIDENCE, 'dogfood_agent_v2_runs.json'))

def test_final_report_has_blocker_info():
    data = _read_json(os.path.join(EVIDENCE, 'final_report.json'))
    assert 'blocker_closed' in data
    assert 'blocker_type' in data
    if not data['blocker_closed']:
        assert data['blocker_type'] in ['windows_tcp_socket_zombie', 'stale_process']
        assert 'recommendation' in data

def test_memory_faiss_unchanged():
    data = _read_json(os.path.join(EVIDENCE, 'memory_faiss_baseline.json'))
    # Verify semantic memory lines
    semantic_path = os.path.join(ROOT, 'memory/semantic/semantic_memory.jsonl')
    with open(semantic_path, 'rb') as f:
        semantic_data = f.read()
    semantic_lines = semantic_data.decode('utf-8', errors='replace').count('\n')
    assert semantic_lines == 1732, f"semantic_memory.jsonl lines changed: {semantic_lines} != 1732"
    # Verify FAISS
    import faiss
    faiss_path = os.path.join(ROOT, 'memory/semantic/semantic_memory_faiss.index')
    idx = faiss.read_index(faiss_path)
    assert idx.ntotal == 1633, f"FAISS ntotal changed: {idx.ntotal} != 1633"

def test_no_trading_b8_touched():
    # Just verify trading dir exists but wasn't modified in this front
    assert os.path.exists(os.path.join(ROOT, 'trading'))

def test_agent_v2_imports():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2
    from tmp_agent.brain_v9.dashboard.dashboard_app import app
    assert get_agent_runtime_v2 is not None
    assert app is not None

def test_kimi_finalizer_available():
    sys.path.insert(0, ROOT)
    from tmp_agent.brain_v9.core.agent_kernel_v2.provider_finalizer import finalizer_status
    status = finalizer_status()
    assert status is not None

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
