"""Smoke test: FRONT-BRAIN-AGENT-V2-UI-CHAT-ROUTING-UNIFICATION-01"""
import sys, os, json, requests

BASE = 'http://127.0.0.1:8091'
DASHBOARD = 'http://127.0.0.1:8092'
EV = 'tmp_agent/front_brain_agent_v2_ui_chat_routing_unification_01'

def file_exists(path):
    return os.path.exists(path)

def probe(url, method='GET', body=None, timeout=30):
    try:
        if method == 'POST':
            r = requests.post(url, json=body, timeout=timeout)
        else:
            r = requests.get(url, timeout=timeout)
        return r.status_code, r.json() if r.status_code == 200 else None
    except Exception as e:
        return 0, str(e)

def test_state_lock():
    assert file_exists(f'{EV}/state_lock.json'), "state_lock missing"
    print("PASS: state_lock")

def test_ui_routing_audit():
    assert file_exists(f'{EV}/ui_routing_audit.json'), "ui_routing_audit missing"
    print("PASS: ui_routing_audit")

def test_canonical_chat_contract():
    assert file_exists(f'{EV}/canonical_chat_contract.json'), "canonical_chat_contract missing"
    print("PASS: canonical_chat_contract")

def test_visible_execution_trace_contract():
    assert file_exists(f'{EV}/visible_execution_trace_contract.json'), "visible_execution_trace_contract missing"
    print("PASS: visible_execution_trace_contract")

def test_ui_8091_fix():
    assert file_exists(f'{EV}/ui_8091_fix.json'), "ui_8091_fix missing"
    print("PASS: ui_8091_fix")

def test_ui_8092_fix():
    assert file_exists(f'{EV}/ui_8092_fix.json'), "ui_8092_fix missing"
    print("PASS: ui_8092_fix")

def test_live_api_baseline():
    assert file_exists(f'{EV}/live_api_baseline_test.json'), "live_api_baseline missing"
    print("PASS: live_api_baseline")

def test_live_8092_dashboard():
    assert file_exists(f'{EV}/live_8092_dashboard_test.json'), "live_8092_dashboard missing"
    print("PASS: live_8092_dashboard")

def test_trace_verification():
    assert file_exists(f'{EV}/trace_verification.json'), "trace_verification missing"
    print("PASS: trace_verification")

def test_8091_health():
    status, _ = probe(f'{BASE}/health')
    assert status == 200, f"8091 health: {status}"
    print("PASS: 8091_health")

def test_8091_v2_chat():
    body = {"message":"Test","mode":"read_only","user_id":"smoke_test"}
    status, data = probe(f'{BASE}/v2/chat/agent', method='POST', body=body, timeout=60)
    assert status == 200, f"8091 v2/chat: {status}"
    assert data.get("canonical_agent_v2"), "not canonical"
    assert data.get("run_id", "").startswith("agv2_"), "bad run_id"
    print("PASS: 8091_v2_chat")

def test_8091_status():
    status, _ = probe(f'{BASE}/v2/agent/status')
    assert status == 200, f"8091 status: {status}"
    print("PASS: 8091_status")

def test_8091_capabilities():
    status, _ = probe(f'{BASE}/v2/agent/capabilities')
    assert status == 200, f"8091 capabilities: {status}"
    print("PASS: 8091_capabilities")

def test_8091_operator_presets():
    status, data = probe(f'{BASE}/v2/agent/operator-presets')
    assert status == 200, f"8091 presets: {status}"
    assert len(data.get("presets", [])) >= 8, "presets < 8"
    print("PASS: 8091_operator_presets")

def test_8092_dashboard_root():
    status, _ = probe(DASHBOARD + '/')
    assert status == 200, f"8092 root: {status}"
    print("PASS: 8092_dashboard_root")

def test_8092_agent_v2_status():
    status, _ = probe(f'{DASHBOARD}/brain-dashboard/agent-v2/status')
    assert status == 200, f"8092 agent-v2 status: {status}"
    print("PASS: 8092_agent_v2_status")

def test_8092_dashboard_chat():
    body = {"message":"Test","mode":"read_only","user_id":"smoke_test"}
    status, data = probe(f'{DASHBOARD}/brain-dashboard/chat', method='POST', body=body, timeout=60)
    assert status == 200, f"8092 chat: {status}"
    assert data.get("canonical_agent_v2"), "not canonical"
    assert data.get("run_id", "").startswith("agv2_"), "bad run_id"
    print("PASS: 8092_dashboard_chat")

def test_8092_trace_proxy():
    with open(f'{EV}/live_8092_dashboard_test.json') as f:
        d = json.load(f)
    run_id = d.get('run_id', '')
    if not run_id:
        print("SKIP: 8092_trace_proxy (no run_id)")
        return
    status, data = probe(f'{DASHBOARD}/brain-dashboard/agent-v2/runs/{run_id}/trace')
    assert status == 200, f"8092 trace proxy: {status}"
    assert data.get("ok"), "trace not ok"
    print("PASS: 8092_trace_proxy")

def test_memory_faiss_unchanged():
    with open(f'{EV}/memory_faiss_final.json') as f:
        d = json.load(f)
    assert d["faiss_ntotal"] == 1633, f"faiss_ntotal={d['faiss_ntotal']}"
    assert not d["faiss_mutated"], "faiss mutated"
    assert not d["semantic_staged"], "semantic staged"
    print("PASS: memory_faiss_unchanged")

if __name__ == "__main__":
    tests = [
        test_state_lock, test_ui_routing_audit, test_canonical_chat_contract,
        test_visible_execution_trace_contract, test_ui_8091_fix, test_ui_8092_fix,
        test_live_api_baseline, test_live_8092_dashboard, test_trace_verification,
        test_8091_health, test_8091_v2_chat, test_8091_status,
        test_8091_capabilities, test_8091_operator_presets,
        test_8092_dashboard_root, test_8092_agent_v2_status,
        test_8092_dashboard_chat, test_8092_trace_proxy,
        test_memory_faiss_unchanged
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
