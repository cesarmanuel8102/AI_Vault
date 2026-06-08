"""Smoke test for FRONT-REAL-CANARY-POST-AUDIT-01."""

import json
import os

TARGET = 'memory/semantic/semantic_memory.jsonl'
EVIDENCE_DIR = 'tmp_agent/front_real_canary_post_audit_01'
CANARY_ID = 'canary-00000000-0000-0000-0000-000000000001'
EXEC_EVIDENCE_DIR = 'tmp_agent/front_real_canary_exec_01'


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_post_audit_doc_exists():
    assert os.path.isfile('docs/FRONT_REAL_CANARY_POST_AUDIT_01.md')


def test_canary_presence_audit_exists():
    path = os.path.join(EVIDENCE_DIR, 'canary_presence_audit.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['result'] == 'PASSED'


def test_canary_exists_exactly_once():
    count = 0
    with open(TARGET, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get('id') == CANARY_ID:
                count += 1
    assert count == 1


def test_canary_is_last_line():
    with open(TARGET, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    assert last['id'] == CANARY_ID
    assert last['kind'] == 'canary'


def test_canary_metadata_safe():
    with open(TARGET, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    meta = json.loads(lines[-1])['metadata']
    assert meta.get('canary') is True
    assert meta.get('faiss_write') is False
    assert meta.get('promotion') is False
    assert meta.get('patch_application') is False
    assert meta.get('trading') is False
    assert meta.get('b8') is False


def test_prior_exec_evidence_audit_exists():
    path = os.path.join(EVIDENCE_DIR, 'prior_exec_evidence_audit.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['all_present'] is True


def test_prior_exec_write_completed():
    path = os.path.join(EXEC_EVIDENCE_DIR, 'write_operation.json')
    data = load_json(path)
    assert data['write_completed'] is True
    assert data['lines_appended'] == 1


def test_prior_exec_post_write_passed():
    path = os.path.join(EXEC_EVIDENCE_DIR, 'post_write_verification.json')
    data = load_json(path)
    assert data['result'] == 'PASSED'
    assert data['all_checks_passed'] is True


def test_rollback_readiness_passed():
    path = os.path.join(EXEC_EVIDENCE_DIR, 'rollback_readiness.json')
    data = load_json(path)
    assert data['result'] == 'PASSED'


def test_faiss_integrity_audit_exists():
    path = os.path.join(EVIDENCE_DIR, 'faiss_index_integrity_audit.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['all_unmodified'] is True


def test_no_faiss_files_modified():
    path = os.path.join(EVIDENCE_DIR, 'faiss_index_integrity_audit.json')
    data = load_json(path)
    for fpath, info in data['files'].items():
        if info['exists']:
            assert info['unmodified'] is True, f'{fpath} modified unexpectedly'


def test_commit_scope_audit_exists():
    path = os.path.join(EVIDENCE_DIR, 'git_commit_scope_audit.json')
    assert os.path.isfile(path)


def test_functional_commit_scope_clean():
    path = os.path.join(EVIDENCE_DIR, 'git_commit_scope_audit.json')
    data = load_json(path)
    assert data['canary_scope_clean'] is True
    assert data['ledger_scope_clean'] is True


def test_roadmap_ledger_audit_exists():
    path = os.path.join(EVIDENCE_DIR, 'roadmap_ledger_consistency_audit.json')
    assert os.path.isfile(path)


def test_roadmap_json_valid():
    with open('ROADMAP_STATUS.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert 'FRONT-REAL-CANARY-EXEC-01' in data['completed_fronts']
    assert data['front_real_canary_exec_01']['status'] == 'done'


def test_post_audit_decision_present():
    with open('docs/FRONT_REAL_CANARY_POST_AUDIT_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'KEEP_CANARY' in content or 'ROLLBACK_RECOMMENDED' in content


def test_decision_is_keep_or_rollback_recommended():
    with open('docs/FRONT_REAL_CANARY_POST_AUDIT_01.md', 'r', encoding='utf-8') as f:
        content = f.read()
    has_keep = 'KEEP_CANARY' in content
    has_rollback = 'ROLLBACK_RECOMMENDED' in content
    assert has_keep or has_rollback
    # At least one must be the explicit decision
    assert '## 9. Decision' in content


def test_no_rollback_executed():
    path = os.path.join(EXEC_EVIDENCE_DIR, 'write_operation.json')
    data = load_json(path)
    assert data.get('rollback_executed') in [None, False]

    path = os.path.join(EVIDENCE_DIR, 'canary_presence_audit.json')
    data = load_json(path)
    assert data['canary_count'] == 1
    assert data['canary_is_last_line'] is True
