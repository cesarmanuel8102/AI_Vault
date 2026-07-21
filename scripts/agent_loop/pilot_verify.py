#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

MARKER = 'docs/agent_loop/pilot/PILOT_MARKER.md'
EXECUTOR = 'docs/agent_loop/pilot/EXECUTOR_REPORT.json'
ALLOWED = {MARKER, EXECUTOR}
MIN_WORKER_VERSION = (1, 5, 4)
FRONT_ID_RE = re.compile(r'[A-Z0-9][A-Z0-9._-]{5,127}')

def valid_front_id(value: str) -> bool:
    return bool(FRONT_ID_RE.fullmatch(value)) and '..' not in value

def run(args):
    p=subprocess.run(args,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise RuntimeError(f"{args}: {p.stdout}{p.stderr}")
    return p.stdout.strip()

def version_tuple(value):
    try: return tuple(int(x) for x in str(value).split('.')[:3])
    except Exception: return (0,0,0)

def valid_marker(text: str, expected_front_id: str) -> list[str]:
    errors=[]
    normalized=text.replace('\r\n','\n')
    lines=normalized.splitlines()
    fields={}
    if not lines or lines[0] != '# Agent Loop Pilot': errors.append('marker title mismatch')
    for line in lines[1:]:
        if '=' in line:
            k,v=line.split('=',1); fields[k.strip()]=v
    if version_tuple(fields.get('WORKER_VERSION')) < MIN_WORKER_VERSION: errors.append('marker worker version too old')
    if fields.get('FRONT_ID') != expected_front_id: errors.append('marker front id mismatch')
    if fields.get('STATUS') != 'PASS': errors.append('marker status mismatch')
    if fields.get('EXECUTOR') != 'OPENCODE_OLLAMA_TOOL_EXECUTOR': errors.append('marker executor mismatch')
    if fields.get('SUPERVISOR') != 'CODEX_GITHUB_ACTION': errors.append('marker supervisor mismatch')
    required={'WORKER_VERSION','FRONT_ID','STATUS','EXECUTOR','SUPERVISOR'}
    missing=sorted(required-set(fields))
    if missing: errors.append(f'marker fields missing: {missing}')
    return errors

def collect_changed(base_sha=None, head_sha=None):
    if base_sha:
        tracked=run(['git','diff','--name-only',base_sha,head_sha or 'HEAD'])
    else:
        tracked=run(['git','diff','--name-only','HEAD'])
    untracked=run(['git','ls-files','--others','--exclude-standard'])
    return sorted({x for x in (tracked+'\n'+untracked).splitlines() if x})

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-sha'); ap.add_argument('--head-sha'); ap.add_argument('--report-path'); ap.add_argument('--local',action='store_true'); ap.add_argument('--content-only',action='store_true'); ap.add_argument('--expected-front-id')
    a=ap.parse_args(); root=Path(__file__).resolve().parents[2]
    marker=root/MARKER; executor=root/EXECUTOR
    errors=[]
    if not a.expected_front_id:
        errors.append('expected front id required')
    elif not valid_front_id(a.expected_front_id):
        errors.append('expected front id invalid')
    if not marker.exists(): errors.append('marker missing')
    elif not errors: errors.extend(valid_marker(marker.read_text(encoding='utf-8-sig'), a.expected_front_id))
    if not a.local:
        if not executor.exists():
            errors.append('executor report missing')
        else:
            try:
                d=json.loads(executor.read_text(encoding='utf-8-sig'))
                if d.get('executor')!='OpenCode/Ollama tool executor': errors.append('executor identity mismatch')
                if d.get('agent')!='brain-opencode-executor': errors.append('executor agent mismatch')
                if not isinstance(d.get('model'),str) or not d.get('model'): errors.append('executor model missing')
                if d.get('front_id')!=a.expected_front_id: errors.append('executor report front id mismatch')
                if d.get('local_test_passed') is not True: errors.append('local test not passed')
                if d.get('merge_performed') is not False: errors.append('merge_performed must be false')
                if d.get('canonical_local_sync') is not False: errors.append('canonical_local_sync must be false')
                if version_tuple(d.get('worker_version')) < MIN_WORKER_VERSION: errors.append('worker_version must be >= 1.5.4')
            except Exception as e: errors.append(f'executor report invalid: {e}')
    changed=[] if a.content_only else collect_changed(a.base_sha,a.head_sha)
    if not a.content_only:
        expected={MARKER} if a.local else ALLOWED
        extra=sorted(set(changed)-expected)
        missing=sorted(expected-set(changed))
        if extra: errors.append(f'out-of-scope changes: {extra}')
        if missing: errors.append(f'expected changed files missing: {missing}')
    head=a.head_sha or run(['git','rev-parse','HEAD'])
    report={'schema_version':1,'status':'PASS' if not errors else 'FAIL','errors':errors,'changed_files':changed,
            'base_sha':a.base_sha,'head_sha':head,'generated_utc':datetime.now(timezone.utc).isoformat()}
    if a.report_path:
        Path(a.report_path).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if not errors else 1
if __name__=='__main__': sys.exit(main())
