"""Smoke test for FRONT-REAL-CANARY-EXEC-01 single-record canary write."""

import json
import hashlib
import os

target = 'memory/semantic/semantic_memory.jsonl'
evidence_dir = 'tmp_agent/front_real_canary_exec_01'
canary_id = 'canary-00000000-0000-0000-0000-000000000001'


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_canary_exec_evidence_exists():
    assert os.path.isdir(evidence_dir)


def test_pre_write_snapshot_exists():
    path = os.path.join(evidence_dir, 'pre_write_snapshot.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['result'] == 'PASSED'


def test_backup_verification_passed():
    path = os.path.join(evidence_dir, 'backup_verification.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['result'] == 'PASSED'
    assert data['sha256_matches_before'] is True


def test_write_operation_completed():
    path = os.path.join(evidence_dir, 'write_operation.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['write_attempted'] is True
    assert data['write_completed'] is True
    assert data['lines_appended'] == 1
    assert data['faiss_write'] is False
    assert data['promotion'] is False
    assert data['patch_application'] is False


def test_post_write_verification_passed():
    path = os.path.join(evidence_dir, 'post_write_verification.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['all_checks_passed'] is True
    assert data['result'] == 'PASSED'


def test_line_count_incremented_by_one():
    with open(target, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert len(lines) == 1706


def test_canary_record_exists_once():
    count = 0
    with open(target, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get('id') == canary_id:
                count += 1
    assert count == 1


def test_canary_record_is_last_line():
    with open(target, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    assert last['id'] == canary_id
    assert last['kind'] == 'canary'


def test_canary_record_schema_valid():
    with open(target, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    last = json.loads(lines[-1])
    assert 'created_utc' in last
    assert 'id' in last
    assert 'kind' in last
    assert 'metadata' in last
    assert 'session_id' in last
    assert 'source' in last
    assert 'text' in last


def test_canary_record_metadata_flags_safe():
    with open(target, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    meta = json.loads(lines[-1])['metadata']
    assert meta.get('canary') is True
    assert meta.get('faiss_write') is False
    assert meta.get('promotion') is False
    assert meta.get('patch_application') is False
    assert meta.get('trading') is False
    assert meta.get('b8') is False


def test_no_faiss_write():
    path = os.path.join(evidence_dir, 'write_operation.json')
    data = load_json(path)
    assert data['faiss_write'] is False


def test_no_promotion():
    path = os.path.join(evidence_dir, 'write_operation.json')
    data = load_json(path)
    assert data['promotion'] is False


def test_no_patch_application():
    path = os.path.join(evidence_dir, 'write_operation.json')
    data = load_json(path)
    assert data['patch_application'] is False


def test_no_trading_b8():
    with open(target, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    meta = json.loads(lines[-1])['metadata']
    assert meta.get('trading') is False
    assert meta.get('b8') is False


def test_rollback_readiness_verified():
    path = os.path.join(evidence_dir, 'rollback_readiness.json')
    assert os.path.isfile(path)
    data = load_json(path)
    assert data['result'] == 'PASSED'
    assert data['sha256_matches_pre_write'] is True
    assert data['canary_would_disappear_on_restore'] is True


def test_backup_hash_matches_pre_write_hash():
    backup_path = os.path.join(evidence_dir, 'backups', 'semantic_memory.jsonl.backup_20260608_203610.jsonl')
    with open(backup_path, 'rb') as f:
        backup_hash = hashlib.sha256(f.read()).hexdigest()
    pre_write_path = os.path.join(evidence_dir, 'pre_write_snapshot.json')
    pre_write_hash = load_json(pre_write_path)['sha256_before']
    assert backup_hash == pre_write_hash
