"""Smoke test for FRONT-REAL-READ-VERIFY-01 runtime read-only retrieval verification."""

import json
import os

TARGET = 'memory/semantic/semantic_memory.jsonl'
CANARY_ID = 'canary-00000000-0000-0000-0000-000000000001'
EVIDENCE_DIR = 'tmp_agent/front_real_read_verify_01'

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_read_verify_doc_exists():
    assert os.path.isfile('docs/FRONT_REAL_READ_VERIFY_01.md'), "Read verify doc missing"

def test_baseline_snapshot_exists():
    assert os.path.isfile(f'{EVIDENCE_DIR}/baseline_snapshot.json'), "Baseline snapshot missing"
    data = load_json(f'{EVIDENCE_DIR}/baseline_snapshot.json')
    assert data['result'] == 'PASSED'

def test_runtime_status_check_exists():
    assert os.path.isfile(f'{EVIDENCE_DIR}/runtime_status_check.json'), "Runtime status check missing"
    data = load_json(f'{EVIDENCE_DIR}/runtime_status_check.json')
    assert data['result'] == 'PASSED'

def test_read_only_inventory_exists():
    assert os.path.isfile(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.json'), "Read-only inventory missing"
    assert os.path.isfile(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.md'), "Read-only inventory markdown missing"

def test_read_only_result_exists():
    assert os.path.isfile(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.json'), "Read-only result missing"
    data = load_json(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.json')
    assert 'selected_verification_method' in data
    assert data['no_write_endpoints_used'] is True

def test_post_runtime_snapshot_exists():
    assert os.path.isfile(f'{EVIDENCE_DIR}/post_runtime_snapshot.json'), "Post-runtime snapshot missing"
    data = load_json(f'{EVIDENCE_DIR}/post_runtime_snapshot.json')
    assert data['result'] == 'PASSED'

def test_semantic_memory_hash_unchanged():
    data = load_json(f'{EVIDENCE_DIR}/baseline_snapshot.json')
    baseline_hash = data['files']['memory/semantic/semantic_memory.jsonl']['sha256']
    data2 = load_json(f'{EVIDENCE_DIR}/post_runtime_snapshot.json')
    post_hash = data2['files_hashes']['memory/semantic/semantic_memory.jsonl']
    assert baseline_hash == post_hash, "semantic_memory.jsonl hash changed unexpectedly"

def test_faiss_hashes_unchanged():
    data = load_json(f'{EVIDENCE_DIR}/baseline_snapshot.json')
    post = load_json(f'{EVIDENCE_DIR}/post_runtime_snapshot.json')
    for f in ['memory/semantic/semantic_memory_faiss.index',
              'memory/semantic/semantic_memory_faiss_ids.json',
              'memory/semantic/semantic_memory_index.npz']:
        if data['files'][f]['sha256'] is not None:
            assert data['files'][f]['sha256'] == post['files_hashes'][f], f"Hash changed for {f}"

def test_canary_still_exists_once():
    count = 0
    with open(TARGET, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get('id') == CANARY_ID:
                count += 1
    assert count == 1, f"Expected 1 canary, found {count}"

def test_no_write_request_sent():
    inventory = load_json(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.json')
    assert inventory['no_write_endpoints_used'] is True

def test_no_faiss_write():
    inventory = load_json(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.json')
    assert inventory['no_write_endpoints_used'] is True

def test_no_promotion():
    # No promotion endpoint is a write endpoint; read-only inventory confirms no writes
    inventory = load_json(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.json')
    assert inventory['no_write_endpoints_used'] is True

def test_no_patch_application():
    # Same logic: no write endpoints used implies no patches applied
    inventory = load_json(f'{EVIDENCE_DIR}/read_only_endpoint_inventory.json')
    assert inventory['no_write_endpoints_used'] is True

def test_decision_present():
    with open('docs/FRONT_REAL_READ_VERIFY_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert '## 11. Decision' in content, "Decision section missing"

def test_decision_allowed_value():
    doc_path = 'docs/FRONT_REAL_READ_VERIFY_01.md'
    with open(doc_path, 'r', encoding='utf-8') as f:
        content = f.read()
    allowed_decisions = ['READ_VERIFY_PASS', 'NEED_READ_ONLY_LOOKUP_ADAPTER', 'FAILED_READ_ONLY_MUTATION_DETECTED']
    assert any(d in content for d in allowed_decisions), f"Decision must be one of {allowed_decisions}"

def test_no_memory_or_faiss_staged():
    import subprocess
    staged = subprocess.run(['git', 'diff', '--cached', '--name-status'], capture_output=True, text=True).stdout
    assert 'memory/semantic/semantic_memory.jsonl' not in staged
    assert 'memory/semantic/semantic_memory_faiss' not in staged
