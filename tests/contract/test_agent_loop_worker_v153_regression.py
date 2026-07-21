#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("worker153", MODULE)
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
FRONT = "PILOT-KIMI-CODEX-20260716-091529"

def assert_raises(fn, text):
    try: fn()
    except Exception as exc:
        assert text.lower() in str(exc).lower(), str(exc)
    else: raise AssertionError("expected failure")

out, mode = worker.decode_process_output(b"ok\x81done")
assert "ok" in out and "done" in out and mode == "utf-8-replace"
valid, mode = worker.decode_process_output('{"ok": true, "text": "ñ"}'.encode('utf-8'))
assert json.loads(valid)["ok"] is True and mode == "utf-8"

with tempfile.TemporaryDirectory() as td:
    cfg_events = {"install_root": td}
    class FakeCompleted:
        returncode = 0
        stdout = b"ok\x81done"
    old_run = worker.subprocess.run
    old_cfg = worker._RUN_EVENT_CFG
    worker.subprocess.run = lambda *a, **k: FakeCompleted()
    worker._RUN_EVENT_CFG = cfg_events
    try:
        assert "ok" in worker.run(["git", "status"])
    finally:
        worker.subprocess.run = old_run
        worker._RUN_EVENT_CFG = old_cfg
    events = (Path(td) / "reports" / "worker-events.jsonl").read_text(encoding="utf-8").splitlines()
    evt = json.loads(events[-1])
    assert evt["kind"] == "subprocess_output_decoding_fallback"
    assert evt["command"] == "git"
    assert evt["decoding"] == "utf-8-replace"

with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "repo"; repo.mkdir()
    subprocess.run(["git","init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git","config","user.name","test"], cwd=repo, check=True)
    subprocess.run(["git","config","user.email","test@example.invalid"], cwd=repo, check=True)
    pv = repo / "scripts/agent_loop/pilot_verify.py"; pv.parent.mkdir(parents=True); pv.write_text((ROOT/"scripts/agent_loop/pilot_verify.py").read_text(encoding='utf-8'), encoding='utf-8')
    marker = repo / "docs/agent_loop/pilot/PILOT_MARKER.md"; marker.parent.mkdir(parents=True)
    marker.write_text(f"# Agent Loop Pilot\nWORKER_VERSION=1.5.2\nFRONT_ID={FRONT}\nSTATUS=PASS\nEXECUTOR=OPENCODE_OLLAMA_TOOL_EXECUTOR\nSUPERVISOR=CODEX_GITHUB_ACTION\n", encoding='utf-8')
    (marker.parent/"EXECUTOR_REPORT.json").write_text(json.dumps({"worker_version":"1.5.2"}), encoding='utf-8')
    subprocess.run(["git","add","."], cwd=repo, check=True); subprocess.run(["git","commit","-m","old"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    marker.write_text(worker.pilot_marker_text(FRONT), encoding='utf-8')
    p = subprocess.run([sys.executable, str(pv), "--local", "--expected-front-id", FRONT], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert p.returncode == 0, p.stdout
    marker.write_text("bad marker\n", encoding='utf-8')
    p = subprocess.run([sys.executable, str(pv), "--local", "--expected-front-id", FRONT], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert p.returncode != 0 and "marker" in p.stdout.lower()

cfg = {"repo":"cesarmanuel8102/AI_Vault","owner":"cesarmanuel8102","base_branch":"codex/own-capital-sustainable-return","install_root":"X","max_local_retries":1,"max_kimi_cycles_default":3,"test_profiles":{"pilot":{}}}
with tempfile.TemporaryDirectory() as td:
    state = Path(td)/"issue-5.json"
    state.write_text(json.dumps({"issue_number":5,"status":"loop:blocked","spec":{},"front":"PILOT-KIMI-CODEX-20260716-091529"}), encoding='utf-8')
    old = worker.gh_json
    worker.gh_json = lambda *a, **k: (_ for _ in ()).throw(AssertionError("gh should not be called"))
    try: worker.process_state(cfg, state)
    finally: worker.gh_json = old

with tempfile.TemporaryDirectory() as td:
    cfg2 = dict(cfg, install_root=td)
    st = {"issue_number":5,"front":"PILOT-KIMI-CODEX-20260716-091529","spec":{},"status":"WAITING","pr_number":6,"terminal_notified":True}
    state = Path(td)/"state/issue-5.json"; state.parent.mkdir(); state.write_text(json.dumps(st), encoding='utf-8')
    calls=[]; old_set=worker.set_phase; old_comment=worker.comment; old_issue_labels=worker.read_issue_labels; old_pr_labels=worker.read_pr_labels; old_comments=worker.issue_comments
    worker.set_phase=lambda *a, **k: calls.append(('phase',a))
    worker.comment=lambda *a, **k: calls.append(('comment',a))
    worker.read_issue_labels=lambda repo, num: {"labels":[{"name":"loop:token-exhausted"}]}
    worker.read_pr_labels=lambda repo, num: {"labels":[{"name":"loop:token-exhausted"}]}
    marker=worker.notification_marker(worker.notification_key(st["front"], st["pr_number"], st.get("last_head_sha"), "loop:token-exhausted"))
    worker.issue_comments=lambda repo, num: [{"body":marker}]
    try: worker.terminalize_state_error(cfg2, state, RuntimeError('MAX_CYCLES_EXHAUSTED'))
    finally: worker.set_phase=old_set; worker.comment=old_comment; worker.read_issue_labels=old_issue_labels; worker.read_pr_labels=old_pr_labels; worker.issue_comments=old_comments
    assert not [c for c in calls if c[0]=='comment']

cap={}; old=worker.edit_labels
worker.edit_labels=lambda repo,number,add=(),remove=(): cap.update(add=set(add), remove=set(remove))
try: worker.set_phase('r',5,'loop:blocked')
finally: worker.edit_labels=old
assert cap['add']=={'loop:blocked'} and 'loop:executing' in cap['remove'] and 'agent:queued' in cap['remove']

with tempfile.TemporaryDirectory() as td:
    cfg3 = dict(cfg, install_root=td)
    sd=Path(td)/'state'; sd.mkdir(); sp=sd/'issue-5.json'
    specd={"schema_version":1,"front_id":"PILOT-KIMI-CODEX-20260716-091529","repo":"cesarmanuel8102/AI_Vault","owner":"cesarmanuel8102","base_branch":"codex/own-capital-sustainable-return","expected_base_sha":"4722de72388c9d4d1bd2659dfc8cbfe214c1772e","work_branch":"agent/pilot-20260716-091529","objective":"pilot","test_profile":"pilot","max_kimi_cycles":3,"allowed_paths":["docs/agent_loop/pilot/PILOT_MARKER.md","docs/agent_loop/pilot/EXECUTOR_REPORT.json"],"forbidden_paths":["memory/semantic/","memory/rollback","tmp_agent/state/","tmp_agent/brain_v9/trading/","financial_autonomy/","tmp_agent/brain_v9/core/session.py"]}
    sp.write_text(json.dumps({"issue_number":5,"front":specd['front_id'],"spec":specd,"status":"loop:blocked","cycles":3,"terminal_notified":True,"pr_number":6,"pr_url":"https://github.com/cesarmanuel8102/AI_Vault/pull/6","last_head_sha":"b9d5a6dbc0e00c1dc02ec864281956a9b4326032"}), encoding='utf-8')
    phases=[]; old_set=worker.set_phase; old_event=worker.event; old_gh=worker.gh_json
    worker.set_phase=lambda *a, **k: phases.append(a)
    worker.event=lambda *a, **k: None
    def fake_gh(args):
        if args[:2] == ["issue", "view"]:
            return {"number":5,"state":"OPEN","author":{"login":"cesarmanuel8102"},"body":"<!-- AGENT_LOOP_SPEC "+json.dumps(specd)+" AGENT_LOOP_SPEC -->","labels":[{"name":"loop:blocked"}],"url":"https://github.com/cesarmanuel8102/AI_Vault/issues/5"}
        if args[:2] == ["pr", "view"]:
            return {"number":6,"url":"https://github.com/cesarmanuel8102/AI_Vault/pull/6","state":"OPEN","isDraft":True,"headRefName":"agent/pilot-20260716-091529","headRefOid":"b9d5a6dbc0e00c1dc02ec864281956a9b4326032","baseRefName":"codex/own-capital-sustainable-return","labels":[{"name":"loop:blocked"}]}
        if args[:1] == ["api"]:
            return {"object":{"sha":"4722de72388c9d4d1bd2659dfc8cbfe214c1772e"}}
        raise AssertionError(args)
    worker.gh_json=fake_gh
    try:
        backup=worker.trusted_resume_existing_pr(cfg3,5,specd['front_id'],specd['expected_base_sha'],6,specd['work_branch'],'b9d5a6dbc0e00c1dc02ec864281956a9b4326032')
        ns=json.loads(sp.read_text(encoding='utf-8'))
        assert backup.exists() and ns['status']=='WAITING_GITHUB' and ns['cycles']==2 and ns['terminal_notified'] is False
        assert ns['pr_number']==6 and ns['pr_url'].endswith('/6') and ns['last_head_sha']=='b9d5a6dbc0e00c1dc02ec864281956a9b4326032'
        assert phases[-2][2]=='loop:repairing' and phases[-1][2]=='loop:repairing'
        assert_raises(lambda: worker.trusted_resume_existing_pr(cfg3,6,specd['front_id'],specd['expected_base_sha'],6,specd['work_branch'],'b9d5a6dbc0e00c1dc02ec864281956a9b4326032'), 'Issue #5')
        assert_raises(lambda: worker.trusted_resume_existing_pr(cfg3,5,'WRONG',specd['expected_base_sha'],6,specd['work_branch'],'b9d5a6dbc0e00c1dc02ec864281956a9b4326032'), 'front')
        assert_raises(lambda: worker.trusted_resume_existing_pr(cfg3,5,specd['front_id'],specd['expected_base_sha'],6,specd['work_branch'],'moved'), 'HEAD moved')
    finally: worker.set_phase=old_set; worker.event=old_event; worker.gh_json=old_gh

with tempfile.TemporaryDirectory() as td:
    repo=Path(td)/'repo'; repo.mkdir(); (repo/'.git').mkdir()
    model, seed=worker.prepare_model_workspace(repo, {"front_id":"PILOT-KIMI-CODEX-20260716-091529"}, 1)
    assert not (model/'.git').exists()
contract=json.loads((ROOT/'scripts/agent_loop/local_worker/worker_contract.json').read_text(encoding='utf-8'))
assert contract['auto_merge'] is False and contract['canonical_local_sync'] is False and contract['pilot_only'] is True
assert contract['general_fronts_supported'] is False
print(json.dumps({"status":"PASS","worker_version":worker.WORKER_VERSION}, indent=2))
