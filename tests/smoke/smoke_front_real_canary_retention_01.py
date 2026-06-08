"""Smoke test for FRONT-REAL-CANARY-RETENTION-01."""

import json
import os

TARGET = 'memory/semantic/semantic_memory.jsonl'
CANARY_ID = 'canary-00000000-0000-0000-0000-000000000001'
RETENTION_DIR = 'tmp_agent/front_real_canary_retention_01'
POST_AUDIT_DIR = 'tmp_agent/front_real_canary_post_audit_01'
EXEC_DIR = 'tmp_agent/front_real_canary_exec_01'

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_retention_doc_exists():
    assert os.path.isfile('docs/FRONT_REAL_CANARY_RETENTION_01.md')

def test_retention_doc_declares_keep_canary_marker():
    with open('docs/FRONT_REAL_CANARY_RETENTION_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'KEEP_CANARY_PERMANENT_MARKER' in content

def test_retention_doc_does_not_authorize_new_writes():
    with open('docs/FRONT_REAL_CANARY_RETENTION_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'future_writes_require_separate_front' in content or 'Future Write Policy' in content

def test_retention_doc_declares_no_rollback():
    with open('docs/FRONT_REAL_CANARY_RETENTION_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'rollback_executed: false' in content or 'No rollback executed' in content

def test_retention_doc_declares_no_faiss_promotion():
    with open('docs/FRONT_REAL_CANARY_RETENTION_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'promotion' in content.lower()

def test_post_audit_report_exists():
    assert os.path.isfile(os.path.join(POST_AUDIT_DIR, 'report.json'))
    data = load_json(os.path.join(POST_AUDIT_DIR, 'report.json'))
    assert data['decision'] == 'KEEP_CANARY'

def test_post_audit_decision_keep_canary():
    with open('docs/FRONT_REAL_CANARY_POST_AUDIT_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'KEEP_CANARY' in content

def test_canary_still_exists_once():
    count = 0
    with open(TARGET, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get('id') == CANARY_ID:
                count += 1
    assert count == 1

def test_canary_still_last_line():
    with open(TARGET, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    assert last['id'] == CANARY_ID

def test_canary_metadata_safe():
    with open(TARGET, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    meta = json.loads(lines[-1])['metadata']
    assert meta.get('canary') is True
    assert meta.get('faiss_write') is False
    assert meta.get('promotion') is False

def test_faiss_files_not_modified():
    import subprocess
    faiss_files = [
        'memory/semantic/semantic_memory_faiss.index',
        'memory/semantic/semantic_memory_faiss_ids.json',
        'memory/semantic/semantic_memory_index.npz'
    ]
    staged = subprocess.run(['git', 'diff', '--cached', '--name-status'], capture_output=True, text=True).stdout
    unstaged = subprocess.run(['git', 'diff', '--name-status'], capture_output=True, text=True).stdout
    for f in faiss_files:
        assert f not in staged, f'{f} staged unexpectedly'
        assert f not in unstaged, f'{f} unstaged unexpectedly'

def test_roadmap_json_valid():
    with open('ROADMAP_STATUS.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert 'FRONT-REAL-CANARY-POST-AUDIT-01' in data['completed_fronts']
    assert data['front_real_canary_post_audit_01']['status'] == 'done'

def test_ledger_contains_post_audit():
    with open('docs/MIGRATION_CONTROL_LEDGER.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'FRONT-REAL-CANARY-POST-AUDIT-01' in content

def test_retention_evidence_exists():
    assert os.path.isfile(os.path.join(RETENTION_DIR, 'post_audit_state_verification.json'))
    assert os.path.isfile(os.path.join(RETENTION_DIR, 'canary_stability_verification.json'))
    assert os.path.isfile(os.path.join(RETENTION_DIR, 'faiss_retention_integrity_check.json'))

def test_no_rollback_executed():
    path = os.path.join(EXEC_DIR, 'write_operation.json')
    data = load_json(path)
    assert data.get('rollback_executed') in [None, False]
    # Canary still exists, confirming rollback was not executed
    with open(TARGET, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    assert last['id'] == CANARY_ID

def test_future_writes_require_separate_front():
    with open('docs/FRONT_REAL_CANARY_RETENTION_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'Future Write Policy' in content
    assert 'separate_front' in content.lower() or 'frente separado' in content.lower()
