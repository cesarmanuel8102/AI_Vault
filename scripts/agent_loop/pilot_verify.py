#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

MARKER = 'docs/agent_loop/pilot/PILOT_MARKER.md'
EXECUTOR = 'docs/agent_loop/pilot/EXECUTOR_REPORT.json'
ALLOWED = {MARKER, EXECUTOR}
EXPECTED = '# Agent Loop Pilot\nWORKER_VERSION=1.5.2\nSTATUS=PASS\nEXECUTOR=KIMI_OPENCODE_OLLAMA\nSUPERVISOR=CODEX_GITHUB_ACTION\n'
MIN_WORKER_VERSION = (1, 5, 2)

def run(args):
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if p.returncode: raise RuntimeError(f"{args}: {p.stdout}")
    return p.stdout.strip()

def version_tuple(value):
    try: return tuple(int(x) for x in str(value).split('.')[:3])
    except Exception: return (0,0,0)

def collect_changed(base_sha=None, head_sha=None):
    if base_sha:
        tracked=run(['git','diff','--name-only',base_sha,head_sha or 'HEAD'])
    else:
        tracked=run(['git','diff','--name-only','HEAD'])
    untracked=run(['git','ls-files','--others','--exclude-standard'])
    return sorted({x for x in (tracked+'\n'+untracked).splitlines() if x})

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-sha'); ap.add_argument('--head-sha'); ap.add_argument('--report-path'); ap.add_argument('--local',action='store_true')
    a=ap.parse_args(); root=Path(__file__).resolve().parents[2]
    marker=root/MARKER; executor=root/EXECUTOR
    errors=[]
    if not marker.exists(): errors.append('marker missing')
    elif marker.read_text(encoding='utf-8-sig').replace('\r\n','\n') != EXPECTED: errors.append('marker content mismatch')
    if not a.local:
        if not executor.exists():
            errors.append('executor report missing')
        else:
            try:
                d=json.loads(executor.read_text(encoding='utf-8-sig'))
                if d.get('executor')!='Kimi via OpenCode/Ollama': errors.append('executor identity mismatch')
                if d.get('local_test_passed') is not True: errors.append('local test not passed')
                if d.get('merge_performed') is not False: errors.append('merge_performed must be false')
                if d.get('canonical_local_sync') is not False: errors.append('canonical_local_sync must be false')
                if version_tuple(d.get('worker_version')) < MIN_WORKER_VERSION: errors.append('worker_version must be >= 1.5.2')
            except Exception as e: errors.append(f'executor report invalid: {e}')
    changed=collect_changed(a.base_sha,a.head_sha)
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
