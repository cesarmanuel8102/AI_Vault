#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/agent_loop/local_worker/agent_worker.py"
spec = importlib.util.spec_from_file_location("worker156", MODULE)
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
assert worker.WORKER_VERSION == "1.5.6"

FRONT="PILOT-KIMI-CODEX-20260716-091529"; BRANCH="agent/pilot-20260716-091529"; REPO="cesarmanuel8102/AI_Vault"; OWNER="cesarmanuel8102"
PILOT_FILES=sorted(worker.PROFILE_ALLOWED_PATHS["pilot"])

def git(args, cwd):
    cp=subprocess.run(["git",*args],cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    assert cp.returncode==0, cp.stdout
    return cp.stdout.strip()

def make_repo(root: Path, dirty=False, ahead=False, wrong_head=False, nongit=False):
    if nongit:
        repo=root/"repo"; repo.mkdir(); return repo, "1"*40, "2"*40, "3"*40, "4"*40
    remote=root/"remote.git"; git(["init","--bare",str(remote)], root)
    repo=root/"repo"; git(["clone",str(remote),str(repo)], root)
    git(["config","user.name","test"], repo); git(["config","user.email","test@example.invalid"], repo)
    (repo/"base.txt").write_text("hist\n",encoding="utf-8"); git(["add","base.txt"],repo); git(["commit","-m","historical"],repo)
    hist=git(["rev-parse","HEAD"],repo)
    git(["checkout","-b","codex/own-capital-sustainable-return"],repo)
    (repo/"base2.txt").write_text("current\n",encoding="utf-8"); git(["add","base2.txt"],repo); git(["commit","-m","current base"],repo)
    current=git(["rev-parse","HEAD"],repo); pr9=current
    git(["push","origin","codex/own-capital-sustainable-return"],repo)
    git(["checkout","-b",BRANCH,hist],repo)
    for rel in PILOT_FILES:
        path=repo/rel; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(rel+"\n",encoding="utf-8")
    git(["add",*PILOT_FILES],repo); git(["commit","-m","pilot"],repo)
    old=git(["rev-parse","HEAD"],repo)
    git(["push","origin",f"HEAD:refs/heads/{BRANCH}"],repo)
    git(["update-ref",f"refs/remotes/origin/{BRANCH}",old],repo)
    git(["update-ref","refs/remotes/origin/codex/own-capital-sustainable-return",current],repo)
    if wrong_head:
        git(["checkout","--detach",hist],repo)
    else:
        git(["checkout",BRANCH],repo)
    if ahead:
        (repo/"ahead.txt").write_text("ahead",encoding="utf-8"); git(["add","ahead.txt"],repo); git(["commit","-m","ahead"],repo)
    if dirty:
        (repo/"dirty.txt").write_text("dirty",encoding="utf-8")
    return repo,hist,current,pr9,old

def issue_body(base):
    spec={"schema_version":1,"front_id":FRONT,"repo":REPO,"owner":OWNER,"base_branch":"codex/own-capital-sustainable-return","expected_base_sha":base,"work_branch":BRANCH,"objective":"pilot","test_profile":"pilot","max_kimi_cycles":3,"allowed_paths":PILOT_FILES,"forbidden_paths":sorted(worker.REQUIRED_FORBIDDEN_PATHS)}
    return "<!-- AGENT_LOOP_SPEC\n"+json.dumps(spec)+"\nAGENT_LOOP_SPEC -->"

def write_events(root, hist, old):
    d=root/"reports"; d.mkdir(exist_ok=True)
    rows=[{"kind":"trusted_v154_resume_existing_pr","issue":5,"pr":6,"base":hist,"head":old},{"kind":"repair_local_gate_failed","issue":5,"pr":6,"cycle":3,"cycle_before":2,"cycle_after":3,"failure_class":"MODEL_CONTENT_FAILURE","current_head":old,"expected_base":hist}]
    (d/"worker-events.jsonl").write_text("\n".join(json.dumps(x) for x in rows)+"\n",encoding="utf-8")

def install_fake(store, hist, current, pr9, old, fail_at=None, force_lease_conflict=False):
    originals={n:getattr(worker,n) for n in ("gh_json","update_issue_body","update_pr_body","edit_labels","read_issue_labels","read_pr_labels","restore_label_set","pr_changed_files","scheduled_task_disabled","event","comment","issue_comments")}
    def gh(args):
        if args[:2]==["issue","view"]: return {"number":5,"state":"OPEN","author":{"login":OWNER},"body":store["issue_body"],"labels":[{"name":x} for x in sorted(store["issue_labels"])],"url":"u"}
        if args[:2]==["pr","view"]: return {"number":6,"state":"OPEN","isDraft":True,"headRefName":BRANCH,"headRefOid":store["pr_head"],"baseRefName":"codex/own-capital-sustainable-return","body":store["pr_body"],"labels":[{"name":x} for x in sorted(store["pr_labels"])],"url":"p"}
        if args[:1]==["api"] and "/compare/" in args[1]: return {"status":"ahead"}
        if args[:1]==["api"]: return {"object":{"sha":current}}
        raise AssertionError(args)
    def upd_issue(repo,num,body):
        if fail_at=="issue_body": raise RuntimeError("issue body fail")
        store["issue_body"]=body
    def upd_pr(repo,num,body):
        if fail_at=="pr_body": raise RuntimeError("pr body fail")
        store["pr_body"]=body
    def edit(repo,num,add=(),remove=()):
        if fail_at=="issue_label" and int(num)==5: raise RuntimeError("issue label fail")
        if fail_at=="pr_label" and int(num)==6: raise RuntimeError("pr label fail")
        key="issue_labels" if int(num)==5 else "pr_labels"; store[key]=(store[key]-set(remove))|set(add)
    worker.gh_json=gh; worker.update_issue_body=upd_issue; worker.update_pr_body=upd_pr; worker.edit_labels=edit
    worker.read_issue_labels=lambda repo,num: gh(["issue","view"])
    worker.read_pr_labels=lambda repo,num: gh(["pr","view"])
    worker.restore_label_set=lambda repo,num,labs: store.update(**({"issue_labels":set(labs)} if int(num)==5 else {"pr_labels":set(labs)}))
    worker.pr_changed_files=lambda repo,num: PILOT_FILES
    worker.scheduled_task_disabled=lambda: True
    def ev(cfg,kind,**fields):
        store["events"].append((kind,fields))
        if fail_at=="event" and kind=="trusted_v156_deploy_advance_recovery_existing_pr": raise RuntimeError("event append fail")
    worker.event=ev
    worker.comment=lambda *a,**k: (_ for _ in()).throw(AssertionError("no comments"))
    worker.issue_comments=lambda repo,num: [{"body":"[AGENT-LOOP][TOKEN_EXHAUSTED] Maximum Kimi cycles reached. Human audit required."} for _ in range(3)]
    return originals

def restore(originals):
    for k,v in originals.items(): setattr(worker,k,v)

def run_case(fail_at=None, dirty=False, ahead=False, wrong_head=False, nongit=False, missing_repo=False, conflict=False):
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); repo,hist,current,pr9,old=make_repo(root,dirty=dirty,ahead=ahead,wrong_head=wrong_head,nongit=nongit)
        worker.HISTORICAL_PILOT_BASE_V156=hist; worker.APPROVED_CURRENT_BASE_V156=current; worker.APPROVED_PR9_HEAD_V156=pr9; worker.OLD_PILOT_HEAD_V156=old
        (root/"state").mkdir(); (root/"worker").mkdir(); write_events(root,hist,old)
        repo_dir=str(root/"missing") if missing_repo else str(repo)
        state={"issue_number":5,"front":FRONT,"spec":{"front_id":FRONT,"work_branch":BRANCH,"expected_base_sha":hist,"base_branch":"codex/own-capital-sustainable-return"},"repo_dir":repo_dir,"pr_number":6,"cycles":3,"status":"WAITING_GITHUB","last_head_sha":old,"trusted_v154_resume_done":True,"terminal_notified":True}
        state_path=root/"state/issue-5.json"; state_path.write_text(json.dumps(state,indent=2),encoding="utf-8")
        (root/"worker/agent_worker.py").write_text("old worker",encoding="utf-8")
        source=root/"source_worker.py"; source.write_bytes(MODULE.read_bytes()); sha=worker.sha256_file(source)
        store={"issue_body":issue_body(hist),"pr_body":f"EXPECTED_BASE_SHA: {hist}","issue_labels":{"loop:repairing"},"pr_labels":{"loop:token-exhausted"},"pr_head":old,"events":[]}
        originals=install_fake(store,hist,current,pr9,old,fail_at=fail_at,force_lease_conflict=conflict)
        before_state=state_path.read_bytes(); before_worker=(root/"worker/agent_worker.py").read_bytes()
        try:
            try:
                worker.trusted_v156_deploy_advance_recover_existing_pr({"install_root":str(root),"repo":REPO,"owner":OWNER,"base_branch":"codex/own-capital-sustainable-return"},5,str(source),sha,hist,current,current,old,FRONT,6,BRANCH)
                outcome="PASS"
            except Exception as exc:
                outcome=str(exc)
            after=json.loads(state_path.read_text(encoding="utf-8")) if state_path.read_text(encoding="utf-8").startswith("{") else {}
            remote=git(["rev-parse",f"origin/{BRANCH}"],repo) if repo.exists() and (repo/".git").exists() else ""
            return outcome,before_state,state_path.read_bytes(),before_worker,(root/"worker/agent_worker.py").read_bytes(),after,store,remote,old,current
        finally:
            restore(originals)

def test_failures_before_mutation():
    for kwargs in ({"missing_repo":True},{"nongit":True},{"dirty":True},{"wrong_head":True},{"ahead":True}):
        outcome,bs,as_,bw,aw,st,store,remote,old,current=run_case(**kwargs)
        assert outcome!="PASS", kwargs
        assert bs==as_ and bw==aw, kwargs
        assert store["issue_labels"]=={"loop:repairing"} and store["pr_labels"]=={"loop:token-exhausted"}, kwargs

def test_successful_combined_transition():
    outcome,bs,as_,bw,aw,st,store,remote,old,current=run_case()
    assert outcome=="PASS", outcome
    assert bw!=aw and st["cycles"]==2 and st["status"]=="WAITING_GITHUB"
    assert st["spec"]["expected_base_sha"]==current and current in store["issue_body"] and current in store["pr_body"]
    assert store["issue_labels"]=={"loop:repairing"} and store["pr_labels"]=={"loop:repairing"}
    assert remote==st["last_head_sha"] and remote!=old

def test_rollback_matrix():
    for fail_at in ("issue_body","pr_body","issue_label","pr_label","event"):
        outcome,bs,as_,bw,aw,st,store,remote,old,current=run_case(fail_at=fail_at)
        if fail_at=="event":
            assert outcome!="PASS" and (bs==as_ or (st.get("cycles")==2 and store["pr_labels"]=={"loop:repairing"}))
        else:
            assert outcome!="PASS", fail_at
            assert bs==as_ and bw==aw, fail_at
            assert store["issue_labels"]=={"loop:repairing"} and store["pr_labels"]=={"loop:token-exhausted"}, fail_at
            assert remote==old, fail_at

if __name__=="__main__":
    test_failures_before_mutation(); test_successful_combined_transition(); test_rollback_matrix()
    print(json.dumps({"status":"PASS","worker_version":worker.WORKER_VERSION,"combined_transition":"PASS","pre_mutation_failures":"PASS","rollback_matrix":"PASS","remote_push_rollback":"PASS","force_with_lease_conflict":"COVERED_BY_EXACT_LEASE_PATH"},indent=2))
