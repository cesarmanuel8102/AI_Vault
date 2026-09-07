import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {closeoutSpec,resolveExecutableFront} from "../../../scripts/operator_proxy/roadmap_sequencer.js";
import {resolveRuntimeExecutableFront,validatePostMergeBaseAdvance} from "../../../scripts/operator_proxy/autonomous_runtime.js";
import {ProductionEffects} from "../../../scripts/operator_proxy/production_effects.js";
import {Ledger} from "../../../scripts/operator_proxy/decision_ledger.js";
import {issueBody} from "../../../scripts/operator_proxy/spec_contract.js";

const sha=(character:string)=>character.repeat(40);
const digest=(value:string)=>createHash("sha256").update(Buffer.from(value,"utf8")).digest("hex");

function parentSpec():any {
  return {
    schema_version:1, authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01", repository:"cesarmanuel8102/AI_Vault",
    roadmap_id:"BRAIN-101", roadmap_version:"1.0.0", roadmap_item_id:"R3.4", expected_base_sha:sha("a"),
    executor:"agent_loop", risk:"LOW", allowed_paths:["docs/e2e.md"], forbidden_paths:["trading/"], acceptance:["pass"],
    test_commands:["git diff --check"], deployment_allowed:false, objective:"parent", work_branch:"agent/r3-4", dependencies:["R3.2"],
    deployment_mode:"NO_DEPLOY", front_id:"BRAIN-101-R3-4-E2E-01", roadmap_sha256:"b".repeat(64), manifest_sha256:"c".repeat(64),
    test_profile:"roadmap-doc", max_executor_cycles:2,
    closeout:{front_id:"BRAIN-101-R3-4-E2E-CLOSEOUT-01",objective:"closeout",work_branch:"control-plane/r3-4-closeout",executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/roadmap/closeout.json"],forbidden_paths:["trading/"],acceptance:["close"],test_commands:["git diff --check"]}
  };
}

function persistedCloseoutSpec(child:any,parent:any){
  const evidence={schema_version:1,parent_front_id:parent.front_id,roadmap_id:"BRAIN-101",roadmap_item_id:parent.roadmap_item_id,issue:parent.issue,pr:parent.pr,decision_id:parent.decision_id,authorization_mode:"POLICY_APPROVED",base_sha:parent.base_sha,closeout_base_sha:parent.head_sha,head_sha:parent.head_sha,merge_commit:parent.head_sha,builder_session:parent.builder_session,reviewer_session:parent.reviewer_session};
  const serialized=JSON.stringify(evidence),instruction=`Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: ${serialized}`;
  return {...child,objective:`${child.objective.trim()}\n\nPARENT_LIFECYCLE_EVIDENCE_JSON=${serialized}`,acceptance:[...child.acceptance,instruction]};
}

function saveParent(store:LifecycleStore,parent:any){
  const head=sha("f");const record:any={schema_version:1,front_id:parent.front_id,roadmap_item_id:parent.roadmap_item_id,state:"CLOSEOUT_PENDING",base_sha:parent.expected_base_sha,head_sha:head,issue:246,pr:247,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:246",`build:${head}`,`merge:${head}`],builder_session:"parent-builder",reviewer_session:"parent-reviewer",decision_id:"11111111-1111-4111-8111-111111111111",updated_utc:new Date().toISOString()};store.save(record);return record;
}

test("a valid nonterminal closeout child is selected despite a settled owner system repair",()=>{
  const root=mkdtempSync(join(tmpdir(),"executable-front-")),store=new LifecycleStore(root),parent=parentSpec(),child=closeoutSpec(parent),frozenBase=sha("d"),childHead=sha("e");
  const parentRecord:any={schema_version:1,front_id:parent.front_id,roadmap_item_id:parent.roadmap_item_id,state:"CLOSEOUT_PENDING",base_sha:parent.expected_base_sha,head_sha:sha("f"),issue:246,pr:247,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:246",`build:${sha("f")}`,`merge:${sha("f")}`],builder_session:"parent-builder",reviewer_session:"parent-reviewer",decision_id:"11111111-1111-4111-8111-111111111111",updated_utc:new Date().toISOString()};
  const childRecord:any={schema_version:1,front_id:child.front_id,roadmap_item_id:child.roadmap_item_id,state:"BUILDING",base_sha:frozenBase,head_sha:childHead,issue:248,pr:249,repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${childHead}`],builder_session:"child-builder",updated_utc:new Date().toISOString()};
  store.save(parentRecord);store.save(childRecord);
  store.save({schema_version:1,front_id:"OWNER-SYSTEM-REPAIR-01",roadmap_item_id:parent.roadmap_item_id,state:"MERGED",base_sha:sha("1"),head_sha:sha("2"),issue:282,pr:283,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:282",`build:${sha("3")}`,`merge:${sha("2")}`],builder_session:"system-builder",reviewer_session:"system-reviewer",decision_id:"33333333-3333-4333-8333-333333333333",owner_critical_merge:{critical_merge_key:"4".repeat(64),consumed_event_sha256:"5".repeat(64)},updated_utc:new Date().toISOString()} as any);
  const historical={...persistedCloseoutSpec(child,parentRecord),expected_base_sha:frozenBase};
  const bus:any={
    issueSnapshot:(issue:number)=>{assert.equal(issue,248);return {state:"OPEN",labels:["operator:building"],body:`${issueBody(historical).trim()}\n\nOPERATOR_PROXY_PR: 249\n`};},
    prIdentity:(pr:number)=>{assert.equal(pr,249);return {author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:frozenBase,headRefName:child.work_branch,headRefOid:childHead,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"};},
    isAncestor:(older:string,newer:string)=>older===newer,
  };
  const resolved=resolveExecutableFront(bus,store,parent);
  assert.equal(resolved.spec.front_id,child.front_id);
  assert.equal(resolved.record?.front_id,child.front_id);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
});

test("runtime resolution rejects a directed parent tick while the owned closeout child remains nonterminal",()=>{
  const root=mkdtempSync(join(tmpdir(),"executable-runtime-")),store=new LifecycleStore(root),parent=parentSpec(),child=closeoutSpec(parent),head=sha("e");
  const parentRecord=saveParent(store,parent);
  const record:any={schema_version:1,front_id:child.front_id,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"child-builder",updated_utc:new Date().toISOString()};
  store.save(record);
  const bus:any={issueSnapshot:()=>({body:`${issueBody(persistedCloseoutSpec(child,parentRecord)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:parent.expected_base_sha,headRefName:child.work_branch,headRefOid:head,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),isAncestor:(left:string,right:string)=>left===right};
  assert.throws(()=>resolveRuntimeExecutableFront(bus,store,{spec:parent} as any,parent.front_id),/bypasses nonterminal closeout child/);
  assert.equal(resolveRuntimeExecutableFront(bus,store,{spec:parent} as any,child.front_id).spec.front_id,child.front_id);
});

test("child precedence recovery is append-only and idempotent",()=>{
  const root=mkdtempSync(join(tmpdir(),"executable-precedence-")),store=new LifecycleStore(root),parent=parentSpec(),child=closeoutSpec(parent),head=sha("e");
  const parentRecord:any={schema_version:1,front_id:parent.front_id,roadmap_item_id:parent.roadmap_item_id,state:"CLOSEOUT_PENDING",base_sha:parent.expected_base_sha,head_sha:sha("f"),issue:246,pr:247,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:246",`build:${sha("f")}`,`merge:${sha("f")}`],builder_session:"parent-builder",reviewer_session:"parent-reviewer",decision_id:"11111111-1111-4111-8111-111111111111",updated_utc:new Date().toISOString()};store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"child-builder",updated_utc:new Date().toISOString()} as any);
  const bus:any={issueSnapshot:()=>({body:`${issueBody(persistedCloseoutSpec(child,parentRecord)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:parent.expected_base_sha,headRefName:child.work_branch,headRefOid:head,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),isAncestor:(left:string,right:string)=>left===right};
  resolveExecutableFront(bus,store,parent);resolveExecutableFront(bus,store,parent);
  const precedence=readFileSync(join(root,"events.jsonl"),"utf8").split("\n").filter(line=>line.includes("lifecycle_executable_child_precedence"));
  assert.equal(precedence.length,1);
});

test("ordinary parent remains executable when no nonterminal sibling exists",()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-parent-"))),parent=parentSpec();
  const bus:any={issueSnapshot:()=>{throw new Error("no child issue");},prIdentity:()=>{throw new Error("no child pr");},isAncestor:()=>false};
  assert.equal(resolveExecutableFront(bus,store,parent).source,"ACTIVE_ITEM");
});

test("terminal closeout child no longer blocks its parent",()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-terminal-"))),parent=parentSpec(),child=closeoutSpec(parent);
  store.save({schema_version:1,front_id:child.front_id,roadmap_item_id:parent.roadmap_item_id,state:"TERMINAL_COMPLETED",base_sha:parent.expected_base_sha,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:[],updated_utc:new Date().toISOString()} as any);
  const bus:any={issueSnapshot:()=>{throw new Error("terminal child must not resolve");},prIdentity:()=>{throw new Error("terminal child must not resolve");},isAncestor:()=>false};
  assert.equal(resolveExecutableFront(bus,store,parent).spec.front_id,parent.front_id);
});

test("two nonterminal children fail closed before any child is selected",()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-ambiguous-"))),parent=parentSpec(),child=closeoutSpec(parent),head=sha("e");
  for(const front of [child.front_id,"BRAIN-101-R3-4-UNDECLARED-RECOVERY-01"]){store.save({schema_version:1,front_id:front,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"builder",updated_utc:new Date().toISOString()} as any);}
  const bus:any={issueSnapshot:()=>{throw new Error("ambiguity must fail before remote reads");},prIdentity:()=>{throw new Error("ambiguity must fail before remote reads");},isAncestor:()=>false};
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/executable lifecycle ambiguity/);
});

test("an unproven merged NO_DEPLOY lifecycle remains an ambiguity",()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-unproven-"))),parent=parentSpec(),child=closeoutSpec(parent),head=sha("e");
  store.save({schema_version:1,front_id:child.front_id,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"builder",updated_utc:new Date().toISOString()} as any);
  store.save({schema_version:1,front_id:"BRAIN-101-R3-4-UNPROVEN-MERGE-01",roadmap_item_id:parent.roadmap_item_id,state:"MERGED",base_sha:sha("1"),head_sha:sha("2"),issue:282,pr:283,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:282",`build:${sha("3")}`,`merge:${sha("2")}`],updated_utc:new Date().toISOString()} as any);
  const bus:any={issueSnapshot:()=>{throw new Error("ambiguity must fail before remote reads");},prIdentity:()=>{throw new Error("ambiguity must fail before remote reads");},isAncestor:()=>false};
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/executable lifecycle ambiguity/);
});

test("closeout selection rejects mismatched Issue, PR, branch, and explicit unrelated target",()=>{
  const make=(mutate:(bus:any)=>void)=>{
    const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-negative-"))),parent=parentSpec(),child=closeoutSpec(parent),head=sha("e");
    const parentRecord=saveParent(store,parent);
    store.save({schema_version:1,front_id:child.front_id,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"builder",updated_utc:new Date().toISOString()} as any);
    const bus:any={issueSnapshot:()=>({body:`${issueBody(persistedCloseoutSpec(child,parentRecord)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:parent.expected_base_sha,headRefName:child.work_branch,headRefOid:head,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),isAncestor:(left:string,right:string)=>left===right};
    mutate(bus);return {store,parent,bus};
  };
  const issue=make(bus=>bus.issueSnapshot=()=>({body:`${issueBody({...closeoutSpec(parentSpec()),front_id:"BRAIN-101-R3-4-WRONG-CLOSEOUT-01"}).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}));assert.throws(()=>resolveExecutableFront(issue.bus,issue.store,issue.parent),/closeout issue binding invalid/);
  const pr=make(bus=>bus.prIdentity=()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:sha("a"),headRefName:"control-plane/wrong",headRefOid:sha("e"),headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}));assert.throws(()=>resolveExecutableFront(pr.bus,pr.store,pr.parent),/closeout PR binding invalid/);
  const target=make(()=>{});assert.throws(()=>resolveExecutableFront(target.bus,target.store,target.parent,"BRAIN-101-R9-UNRELATED-01"),/does not belong/);
});

test("closeout selection rejects parent evidence bound to a different policy decision",()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-decision-mismatch-"))),parent=parentSpec(),child=closeoutSpec(parent),head=sha("e"),parentRecord=saveParent(store,parent);
  store.save({schema_version:1,front_id:child.front_id,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"builder",updated_utc:new Date().toISOString()} as any);
  const forgedParent={...parentRecord,decision_id:"22222222-2222-4222-8222-222222222222"};
  const bus:any={issueSnapshot:()=>({body:`${issueBody(persistedCloseoutSpec(child,forgedParent)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:parent.expected_base_sha,headRefName:child.work_branch,headRefOid:head,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),isAncestor:(left:string,right:string)=>left===right};
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout issue binding invalid/);
});

test("an exact dispatched Owner closeout retains its frozen historical spec after child selection",()=>{
  const root=mkdtempSync(join(tmpdir(),"executable-owner-frozen-")),store=new LifecycleStore(join(root,"lifecycle")),parent=parentSpec(),child=closeoutSpec(parent),frozenBase=sha("d"),failed=sha("e"),currentHead=sha("f"),parentRecord=saveParent(store,parent),roadmap="closeout roadmap\n";
  const manifest:any={roadmap_id:child.roadmap_id,roadmap_version:child.roadmap_version,repository:child.repository,integration_branch:"codex/own-capital-sustainable-return",approval_status:"HUMAN_ADOPTED",r0_status:"CLOSED_HUMAN_ADOPTED",human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading_enabled:false,roadmap_path:"docs/roadmap/BRAIN_101_ROADMAP.md",roadmap_sha256:digest(roadmap),roadmap_items:{[child.roadmap_item_id]:{status:"AUTHORIZED_ACTIVE",dependencies:child.dependencies}}};
  const manifestText=JSON.stringify(manifest),current={...child,roadmap_sha256:digest(roadmap),manifest_sha256:digest(manifestText)};
  const state:any={schema_version:1,front_id:child.front_id,roadmap_item_id:child.roadmap_item_id,state:"BUILDING",base_sha:frozenBase,head_sha:failed,issue:248,pr:249,repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${failed}`],builder_session:"child-builder",owner_payload_repair:{grant_key:"a".repeat(64),consumed_event_sha256:"b".repeat(64),build_attempt_id:"c".repeat(64)},updated_utc:new Date().toISOString()};
  const historical={...persistedCloseoutSpec(current,parentRecord),expected_base_sha:frozenBase},bus:any={setMutationGuard:()=>{},issueSnapshot:()=>({body:`${issueBody(historical).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),fileAt:(path:string)=>path.endsWith("MANIFEST.json")?manifestText:roadmap};
  const effects:any=new ProductionEffects(bus,new Ledger(join(root,"decisions")),root,root,{assert:()=>{}} as any);
  effects.validDispatchedOwnerResume=()=>true;
  const resolved=effects.resolveFrozenOwnerPayloadSpec(current,state);
  assert.equal(resolved.expected_base_sha,frozenBase);
  assert.equal(resolved.front_id,child.front_id);
  assert.notEqual(currentHead,failed);
});

test("an Owner closeout rejects a historical parent-evidence mutation",()=>{
  const root=mkdtempSync(join(tmpdir(),"executable-owner-frozen-mutation-")),store=new LifecycleStore(join(root,"lifecycle")),parent=parentSpec(),child=closeoutSpec(parent),frozenBase=sha("d"),failed=sha("e"),parentRecord=saveParent(store,parent),roadmap="closeout roadmap\n";
  const manifest:any={roadmap_id:child.roadmap_id,roadmap_version:child.roadmap_version,repository:child.repository,integration_branch:"codex/own-capital-sustainable-return",approval_status:"HUMAN_ADOPTED",r0_status:"CLOSED_HUMAN_ADOPTED",human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading_enabled:false,roadmap_path:"docs/roadmap/BRAIN_101_ROADMAP.md",roadmap_sha256:digest(roadmap),roadmap_items:{[child.roadmap_item_id]:{status:"AUTHORIZED_ACTIVE",dependencies:child.dependencies}}};
  const manifestText=JSON.stringify(manifest),current={...child,roadmap_sha256:digest(roadmap),manifest_sha256:digest(manifestText)};
  const state:any={schema_version:1,front_id:child.front_id,roadmap_item_id:child.roadmap_item_id,state:"BUILDING",base_sha:frozenBase,head_sha:failed,issue:248,pr:249,repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${failed}`],builder_session:"child-builder",owner_payload_repair:{grant_key:"a".repeat(64),consumed_event_sha256:"b".repeat(64),build_attempt_id:"c".repeat(64)},updated_utc:new Date().toISOString()};
  const historical:any={...persistedCloseoutSpec(current,parentRecord),expected_base_sha:frozenBase};
  historical.acceptance[historical.acceptance.length-1]="Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: {\"tampered\":true}";
  const bus:any={setMutationGuard:()=>{},issueSnapshot:()=>({body:`${issueBody(historical).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),fileAt:(path:string)=>path.endsWith("MANIFEST.json")?manifestText:roadmap};
  const effects:any=new ProductionEffects(bus,new Ledger(join(root,"decisions")),root,root,{assert:()=>{}} as any);
  effects.validDispatchedOwnerResume=()=>true;
  assert.equal(effects.resolveFrozenOwnerPayloadSpec(current,state),current);
});

test("an Owner child selection preserves the single logical attempt and never emits a second consumed receipt",()=>{
  const root=mkdtempSync(join(tmpdir(),"executable-owner-attempt-")),store=new LifecycleStore(root),parent=parentSpec(),child=closeoutSpec(parent),childFront=child.front_id!,frozen=sha("d"),failed=sha("e"),head=sha("f"),attempt="c".repeat(64);
  const parentRecord=saveParent(store,parent);
  const childRecord:any={schema_version:1,front_id:childFront,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:frozen,head_sha:failed,issue:248,pr:249,repair_cycles:2,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${failed}`],builder_session:"builder",owner_payload_repair:{grant_key:"a".repeat(64),consumed_event_sha256:"b".repeat(64),build_attempt_id:attempt},updated_utc:new Date().toISOString()};store.save(childRecord);const before=readFileSync(store.path(childFront));
  const historical={...persistedCloseoutSpec(child,parentRecord),expected_base_sha:frozen},bus:any={issueSnapshot:()=>({body:`${issueBody(historical).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:sha("9"),headRefName:child.work_branch,headRefOid:head,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),isAncestor:(left:string,right:string)=>left===failed&&right===head};
  const selected=resolveExecutableFront(bus,store,parent,childFront);
  assert.equal(selected.record?.owner_payload_repair?.build_attempt_id,attempt);assert.equal(selected.record?.repair_cycles,2);assert.deepEqual(readFileSync(store.path(childFront)),before);assert.doesNotMatch(readFileSync(join(root,"events.jsonl"),"utf8"),/CONSUMED|consumed/i);
});

test("undeclared nonterminal lifecycle and missing explicit child target fail closed",()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-unbound-"))),parent=parentSpec(),head=sha("e");
  store.save({schema_version:1,front_id:"BRAIN-101-R3-4-RECOVERY-UNBOUND-01",roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"builder",updated_utc:new Date().toISOString()} as any);
  const bus:any={issueSnapshot:()=>{throw new Error("must not validate an undeclared child");},prIdentity:()=>{throw new Error("must not validate an undeclared child");},isAncestor:()=>false};
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/not the declared closeout front/);
  const empty=new LifecycleStore(mkdtempSync(join(tmpdir(),"executable-target-missing-")));assert.throws(()=>resolveExecutableFront(bus,empty,parent,closeoutSpec(parent).front_id),/targeted closeout lifecycle missing/);
});

test("a canonical system repair advance never becomes an unrelated lifecycle merge",()=>{
  const ownMerge=sha("b"),systemRepair=sha("c"),state:any={state:"CLOSEOUT_PENDING",head_sha:ownMerge,completed_effects:[`merge:${ownMerge}`]},spec:any={expected_base_sha:systemRepair};
  assert.equal(validatePostMergeBaseAdvance(spec,state,(older:string,newer:string)=>older===ownMerge&&newer===systemRepair),true);
  assert.notEqual(state.head_sha,spec.expected_base_sha);assert.equal(state.completed_effects.includes(`merge:${systemRepair}`),false);
});

test("an unrelated legacy lifecycle cannot block active-item child resolution",()=>{
  const root=mkdtempSync(join(tmpdir(),"executable-legacy-")),store=new LifecycleStore(root),parent=parentSpec(),child=closeoutSpec(parent),head=sha("e");
  const parentRecord=saveParent(store,parent);
  writeFileSync(join(root,"BRAIN-101-LEGACY-UNRELATED-01.json"),JSON.stringify({schema_version:1,front_id:"BRAIN-101-LEGACY-UNRELATED-01",state:"REVIEWING",roadmap_item_id:"",updated_utc:new Date().toISOString()}));
  store.save({schema_version:1,front_id:child.front_id,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:parent.expected_base_sha,head_sha:head,issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248",`build:${head}`],builder_session:"builder",updated_utc:new Date().toISOString()} as any);
  const bus:any={issueSnapshot:()=>({body:`${issueBody(persistedCloseoutSpec(child,parentRecord)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:parent.expected_base_sha,headRefName:child.work_branch,headRefOid:head,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),isAncestor:(left:string,right:string)=>left===right};
  assert.equal(resolveExecutableFront(bus,store,parent).spec.front_id,child.front_id);
});
