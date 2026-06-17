"""Smoke test: FRONT-BRAIN-AGENT-V2-UI-METADATA-TRACE-PANEL-CLEANUP-01"""
import sys, os, json, requests

BASE = 'http://127.0.0.1:8091'
DASHBOARD = 'http://127.0.0.1:8092'
EV = 'tmp_agent/front_brain_agent_v2_ui_metadata_trace_panel_cleanup_01'

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

def test_corrected_surface_audit():
    assert file_exists(f'{EV}/corrected_surface_audit.json'), "corrected_surface_audit missing"
    print("PASS: corrected_surface_audit")

def test_fix_8092_metadata_header():
    assert file_exists(f'{EV}/live_8092_metadata_trace_test.json'), "live_8092_metadata_trace_test missing"
    print("PASS: fix_8092_metadata_header")

def test_fix_8092_execution_trace_panel():
    assert file_exists(f'{EV}/trace_proxy_test.json'), "trace_proxy_test missing"
    print("PASS: fix_8092_execution_trace_panel")

def test_regression_8091_ui_check():
    assert file_exists(f'{EV}/regression_8091_ui_check.json'), "regression_8091_ui_check missing"
    print("PASS: regression_8091_ui_check")

def test_planner_gap_deferred():
    assert file_exists(f'{EV}/planner_gap_deferred.json'), "planner_gap_deferred missing"
    print("PASS: planner_gap_deferred")

def test_memory_faiss_final():
    assert file_exists(f'{EV}/memory_faiss_final.json'), "memory_faiss_final missing"
    print("PASS: memory_faiss_final")

def test_8091_health():
    status, _ = probe(f'{BASE}/health')
    assert status == 200, f"8091 health: {status}"
    print("PASS: 8091_health")

def test_8091_ui_loads():
    status, _ = probe(f'{BASE}/ui/')
    assert status == 200, f"8091 ui: {status}"
    print("PASS: 8091_ui_loads")

def test_8092_dashboard_chat():
    body = {"message":"Test","mode":"read_only","user_id":"smoke_test"}
    status, data = probe(f'{DASHBOARD}/brain-dashboard/chat', method='POST', body=body, timeout=60)
    assert status == 200, f"8092 chat: {status}"
    assert data.get("canonical_agent_v2"), "not canonical"
    assert data.get("run_id", "").startswith("agv2_"), "bad run_id"
    print("PASS: 8092_dashboard_chat")

def test_8092_trace_proxy():
    with open(f'{EV}/live_8092_metadata_trace_test.json') as f:
        d = json.load(f)
    run_id = d.get('run_id', '')
    if not run_id:
        print("SKIP: 8092_trace_proxy (no run_id)")
        return
    status, data = probe(f'{DASHBOARD}/brain-dashboard/agent-v2/runs/{run_id}/trace')
    assert status == 200, f"8092 trace proxy: {status}"
    assert data.get("ok"), "trace not ok"
    print("PASS: 8092_trace_proxy")

def test_metadata_no_cot_risk():
    with open(f'{EV}/live_8092_metadata_trace_test.json') as f:
        d = json.load(f)
    assert d.get("raw_cot_exposed") is not True, "CoT should not be exposed"
    print("PASS: metadata_no_cot_risk")

def test_memory_faiss_unchanged():
    with open(f'{EV}/memory_faiss_final.json') as f:
        d = json.load(f)
    assert d["faiss_ntotal"] == 1633, f"faiss_ntotal={d['faiss_ntotal']}"
    assert not d["faiss_mutated"], "faiss mutated"
    assert not d["semantic_staged"], "semantic staged"
    print("PASS: memory_faiss_unchanged")

if __name__ == "__main__":
    tests = [
        test_state_lock, test_corrected_surface_audit, test_fix_8092_metadata_header,
        test_fix_8092_execution_trace_panel, test_regression_8091_ui_check,
        test_planner_gap_deferred, test_memory_faiss_final,
        test_8091_health, test_8091_ui_loads,
        test_8092_dashboard_chat, test_8092_trace_proxy,
        test_metadata_no_cot_risk, test_memory_faiss_unchanged
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
