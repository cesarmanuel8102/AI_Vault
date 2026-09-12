import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {AutonomousFlow,newLifecycle,type AutonomousEffects} from "../../../scripts/operator_proxy/autonomous_flow.js";
import {LifecycleStore} from "../../../scripts/operator_proxy/lifecycle_store.js";
import {evaluateSemanticCompletion} from "../../../scripts/operator_proxy/semantic_completion_gate.js";
import {ProductionEffects,resolveSemanticInput} from "../../../scripts/operator_proxy/production_effects.js";
import {closeoutSpec,resolveExecutableFront} from "../../../scripts/operator_proxy/roadmap_sequencer.js";
import {issueBody} from "../../../scripts/operator_proxy/spec_contract.js";
import {Ledger} from "../../../scripts/operator_proxy/decision_ledger.js";
import {POLICY_SHA256,stableDecisionId} from "../../../scripts/operator_proxy/policy_engine.js";
import type {LifecycleRecord,ProxySpec,ReviewerOutput,SemanticCompletionDecisionV1,SemanticCompletionInputV1} from "../../../scripts/operator_proxy/types.js";

const sha=(value:string)=>createHash("sha256").update(value).digest("hex");
const sourceSha="a".repeat(40);
const artifact="verified runtime observation";
const artifactPath="docs/roadmap/evidence/runtime.json";

// ---------------------------------------------------------------------------
// Canonical semantic universe, owned by the trusted source — never the caller.
// ---------------------------------------------------------------------------
const authoritativeRequirement:SemanticCompletionInputV1["requirements"][number]={
  requirement_id:"REQ-R15-SOAK-001",parent_phase:"R15",original_spec_path:"docs/roadmap/BRAIN_101_ROADMAP.md",
  original_spec_sha256:sha("roadmap bytes"),requirement_text_sha256:sha("paper soak must be observed"),
  minimum_evidence_level:"L6_RUNTIME",required_evidence_kinds:["RUNTIME_OBSERVATION"],
  runtime_binding_required:true,deferment_policy:"FORBIDDEN",parent_requirement_ids:[],
  required_environments:["PAPER_RUNTIME"],independent_verifier_required:true,
  minimum_duration_seconds:60,minimum_sample_size:1,
};
const canonicalEvidence={
  evidence_id:"EVIDENCE-R15-001",requirement_id:authoritativeRequirement.requirement_id,evidence_kind:"RUNTIME_OBSERVATION",
  evidence_level:"L6_RUNTIME",source_sha:sourceSha,certified_implementation_sha:sourceSha,
  artifact_path:artifactPath,artifact_sha256:sha(artifact),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",
  observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"runtime-probe",assertion_type:"OBSERVATION" as const,
  observation:{duration_seconds:60,sample_size:1},verifier:{verifier_id:"independent-contract",source_sha:sourceSha,independent:true},
};
const parentSpec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1.0.0-reconstructed-glm-harmonized",roadmap_item_id:"R15",expected_base_sha:sourceSha,executor:"codex_control_plane",risk:"LOW",allowed_paths:["docs/roadmap/"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,objective:"semantic closeout",work_branch:"control-plane/semantic",dependencies:["R0"],deployment_mode:"DOCUMENTATION_CLOSEOUT",front_id:"BRAIN-101-R15-SEMANTIC-01",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};

/** Trusted canonical source. Everything the evaluator consumes originates here. */
function trustedSource(overrides?:{evidence?:Partial<typeof canonicalEvidence>|null;requirements?:SemanticCompletionInputV1["requirements"]|null;artifactBytes?:string|null;now?:string}){
  const state={requirements:overrides?.requirements??[{...authoritativeRequirement}],evidence:overrides?.evidence===null?[]:[{...canonicalEvidence,...(overrides?.evidence??{})}],artifactBytes:overrides?.artifactBytes===null?undefined:overrides?.artifactBytes??artifact,now:overrides?.now??"2026-09-10T00:00:00.000Z"};
  const source={
    semanticRequirements:()=>state.requirements,
    semanticEvidence:()=>state.evidence,
    semanticDeferments:()=>[],
    semanticDefermentAuthorizations:()=>[],
    artifactBytes:()=>state.artifactBytes,
    canonicalSourceSha:()=>sourceSha,
    nowIsoUtc:()=>state.now,
  };
  return source as unknown as import("../../../scripts/operator_proxy/types.js").SemanticSourceV1 & {artifactBytes():string|undefined};
}
type TrustedSource=ReturnType<typeof trustedSource>;

/** Flow fixture with an injected semantic resolver over the trusted source. */
function semanticFixture(source:TrustedSource){
  let issueCalls=0,buildCalls=0,mergeCalls=0,closeoutCalls=0,nextCalls=0,semanticCalls=0;
  const effects:AutonomousEffects={
    bindLifecycle:()=>{},
    resolveSemanticCompletion:(spec:ProxySpec,merge:string)=>{semanticCalls++;return productionResolveSemanticCompletion(spec,merge,source);},
    ensureIssue:()=>{issueCalls++;return 70;},
    ensureBuild:(_s,_i,session)=>{buildCalls++;return Promise.resolve({pr:71,head_sha:"b".repeat(40),session});},
    ci:()=>"PASS",
    review:(_p,head,session)=>({session:`actual-${session}`,output:{verdict:"PASS",head_sha:head,summary:"PASS",findings:[]} as ReviewerOutput}),
    policy:()=>({outcome:"APPROVE",decision_id:"d".repeat(8)+"-4b3e-4c99-9f2e-1a2b3c4d5e6f"}),
    ensureMerge:()=>{mergeCalls++;return "f".repeat(40);},
    ensureInstall:()=>"PASS",
    ensureRuntimePilot:()=>"PASS",
    ensureCloseout:()=>{closeoutCalls++;return Promise.resolve("PASS");},
    discoverNext:()=>{nextCalls++;},
  };
  return {effects,counts:()=>({issueCalls,buildCalls,mergeCalls,closeoutCalls,nextCalls,semanticCalls})};
}
async function drive(flow:AutonomousFlow,spec:ProxySpec,max=40):Promise<LifecycleRecord>{
  let state:LifecycleRecord;for(let i=0;i<max;i++){state=await flow.step(spec);if(state.state==="TERMINAL_COMPLETED"||state.state==="BLOCKED")break;}return state!;
}
function semanticParentRecord(spec:ProxySpec):LifecycleRecord{
  const head="f".repeat(40);
  return {...newLifecycle(spec),state:"CLOSEOUT_PENDING",issue:70,pr:71,head_sha:head,builder_session:"builder-one",reviewer_session:"reviewer-one",decision_id:"d".repeat(8)+"-4b3e-4c99-9f2e-1a2b3c4d5e6f",completed_effects:["issue:70",`build:${head}`,`merge:${head}`]};
}

test("semantic PASS persists its decision hash and reaches terminal with successor discovery",async()=>{
  const f=semanticFixture(trustedSource());
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-flow-")));
  const state=await drive(new AutonomousFlow(store,f.effects),parentSpec);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  assert.ok(state.completed_effects.includes(`semantic_completion:${productionResolveSemanticCompletion(parentSpec,"f".repeat(40),trustedSource()).decision_artifact_sha256}`));
  assert.equal(f.counts().closeoutCalls,1);
  await new AutonomousFlow(store,f.effects).step(parentSpec);
  assert.equal(f.counts().nextCalls,1);
});

test("semantic BLOCK prevents closeout success, closeout merge, terminal completion, and successor discovery",async()=>{
  const blockedSource=trustedSource({evidence:{evidence_level:"L4_SIMULATED_INTEGRATION"}});
  const f=semanticFixture(blockedSource);
  const state=await drive(new AutonomousFlow(new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-block-"))),f.effects),parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().closeoutCalls,0);
  assert.equal(f.counts().nextCalls,0);
  assert.ok(!state.completed_effects.some(effect=>effect.startsWith("semantic_completion:")));
});

test("semantic BLOCK prevents successor authorization on later restart",async()=>{
  const blockedSource=trustedSource({evidence:{evidence_level:"L4_SIMULATED_INTEGRATION"}});
  const f=semanticFixture(blockedSource);
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-block-restart-")));
  const state=await drive(new AutonomousFlow(store,f.effects),parentSpec);
  assert.equal(state.state,"BLOCKED");
  const again=await new AutonomousFlow(store,f.effects).step(parentSpec);
  assert.equal(again.state,"BLOCKED");
  assert.equal(again.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().nextCalls,0);
});

test("blocked semantic state cannot be resumed into closeout by removing evidence",async()=>{
  const blockedSource=trustedSource({evidence:null});
  const f=semanticFixture(blockedSource);
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-block-empty-")));
  const state=await drive(new AutonomousFlow(store,f.effects),parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().closeoutCalls,0);
});

test("semantic PASS allows the pre-existing normal closeout path",async()=>{
  const f=semanticFixture(trustedSource());
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-normal-")));
  const flow=new AutonomousFlow(store,f.effects);
  const state=await drive(flow,parentSpec);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  assert.equal(f.counts().mergeCalls,1);
  assert.equal(f.counts().closeoutCalls,1);
  assert.ok(state.completed_effects.includes("closeout:R15"));
});

test("non-semantic spec never calls the semantic resolver",async()=>{
  const f=semanticFixture(trustedSource());
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-nonbound-")));
  const plain={...parentSpec,semantic_completion:undefined,front_id:"BRAIN-101-R15-PLAIN-01"};
  const state=await drive(new AutonomousFlow(store,f.effects),plain);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  assert.equal(f.counts().semanticCalls,0);
  assert.ok(!state.completed_effects.some(effect=>effect.startsWith("semantic_completion:")));
});

// ---------------------------------------------------------------------------
// Trust boundary: trusted resolver construction (RED — no production impl yet).
// ---------------------------------------------------------------------------

test("trusted resolver builds evaluator input from canonical source, not from the spec",()=>{
  const source=trustedSource();
  const input=resolveSemanticInput(parentSpec,source);
  assert.equal(input.phase_or_item_id,parentSpec.roadmap_item_id);
  assert.equal(input.source_sha,sourceSha);
  assert.deepEqual(input.expected_requirement_ids,[authoritativeRequirement.requirement_id]);
  assert.equal(input.expected_requirements.length,1);
  assert.equal(input.expected_requirements[0].requirement_id,authoritativeRequirement.requirement_id);
  assert.equal(input.requirements.length,1);
  assert.equal(input.evidence.length,1);
  // The canonical artifact bytes resolve from the trusted source and hash-bind.
  assert.equal(input.evidence[0].artifact_sha256,sha(artifact));
});

test("caller cannot self-assert expected requirement identities through the spec",()=>{
  const source=trustedSource();
  const hostileSpec={...parentSpec,semantic_completion:{requirements_path:"attacker/requirements.json",evidence_path:"attacker/evidence.json"}};
  // The resolver ignores spec paths entirely: identity comes from the source.
  const input=resolveSemanticInput(hostileSpec,source);
  assert.deepEqual(input.expected_requirement_ids,[authoritativeRequirement.requirement_id]);
  assert.equal(input.expected_requirements[0].original_spec_sha256,authoritativeRequirement.original_spec_sha256);
});

test("canonical artifact hash mismatch blocks through the trusted resolver",()=>{
  const source=trustedSource({artifactBytes:"tampered bytes"});
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),source);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["ARTIFACT_HASH_MISMATCH"]);
});

test("missing canonical artifact bytes block",()=>{
  const source=trustedSource({artifactBytes:null});
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),source);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("ARTIFACT_HASH_MISMATCH"));
});

test("stale noncanonical source SHA blocks",()=>{
  const staleSource=trustedSource();
  (staleSource as any).canonicalSourceSha=()=>"b".repeat(40);
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),staleSource);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["STALE_SOURCE_SHA"]);
});

test("caller artifact-byte injection is structurally rejected by the pure gate",()=>{
  const source=trustedSource();
  const input=resolveSemanticInput(parentSpec,source);
  // Even if a hostile caller smuggles bytes into the evidence record, the
  // reviewed evaluator's closed schema rejects unknown fields.
  const hostile={...input,evidence:[{...input.evidence[0],artifact_bytes:"attacker"}]};
  assert.throws(()=>evaluate(hostile,source),/unknown semantic evidence field/);
});

test("non-canonical timestamps are rejected at the trust boundary",()=>{
  for(const bad of ["September 10, 2026","09/10/2026","2026-09-10T00:00:00+02:00","2026-09-10 00:00:00Z","2026-09-10T00:00Z","never"]){
    const source=trustedSource({now:bad});
    assert.throws(()=>resolveSemanticInput(parentSpec,source),/canonical UTC timestamp/,bad);
  }
});

test("canonical UTC timestamps are accepted at the trust boundary",()=>{
  const source=trustedSource({now:"2026-09-10T12:34:56.789Z"});
  const input=resolveSemanticInput(parentSpec,source);
  assert.equal(input.evaluated_at_utc,"2026-09-10T12:34:56.789Z");
});

test("decision hash is bound and cannot be substituted downstream",()=>{
  const source=trustedSource();
  const decision=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),source);
  const otherSource=trustedSource({evidence:{evidence_level:"L4_SIMULATED_INTEGRATION"}});
  const other=productionResolveSemanticCompletion(parentSpec,"f".repeat(40),otherSource);
  assert.notEqual(decision.decision_artifact_sha256,other.decision_artifact_sha256);
  assert.match(decision.decision_artifact_sha256,/^[0-9a-f]{64}$/);
  // The exact decision hash is what the flow persists (see PASS test above).
});

test("resolver never accepts caller-supplied decision hashes",()=>{
  const source=trustedSource();
  // There is no path through resolveSemanticInput to inject a decision hash;
  // it is always computed. The input type has no decision field at all.
  const input=resolveSemanticInput(parentSpec,source);
  assert.equal("decision_artifact_sha256" in input,false);
  assert.equal("decision" in input,false);
});

function evaluate(input:SemanticCompletionInputV1,source:TrustedSource):SemanticCompletionDecisionV1{
  const bytes=new Map<string,string>();
  bytes.set(artifactPath,source.artifactBytes()??"");
  return evaluateSemanticCompletion(input,bytes);
}

/** Mirrors the production resolver contract until the real one exists (RED). */
function productionResolveSemanticCompletion(spec:ProxySpec,merge:string,source:TrustedSource):SemanticCompletionDecisionV1{
  const input=resolveSemanticInput(spec,source);
  const bytes=new Map<string,string>();
  for(const evidence of input.evidence){const resolved=source.artifactBytes();if(resolved!==undefined)bytes.set(evidence.artifact_path,resolved);}
  return evaluateSemanticCompletion(input,bytes);
}

// ---------------------------------------------------------------------------
// Successor authorization: closeout child selection requires the parent's
// semantic PASS receipt when the parent is semantic-bound.
// ---------------------------------------------------------------------------
function semanticParentWithCloseoutSpec():{parent:ProxySpec;child:ProxySpec}{
  const parent:ProxySpec={...parentSpec,closeout:{front_id:"BRAIN-101-R15-SEMANTIC-CLOSEOUT-01",objective:"closeout",work_branch:"control-plane/r15-closeout",executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/roadmap/"],forbidden_paths:["trading/"],acceptance:["close"],test_commands:["git diff --check"]}};
  return {parent,child:closeoutSpec(parent)};
}
function persistedSemanticCloseoutSpec(child:ProxySpec,parentRecord:LifecycleRecord,semanticHash?:string):ProxySpec{
  const evidence={schema_version:1,parent_front_id:parentRecord.front_id,roadmap_id:"BRAIN-101",roadmap_item_id:parentRecord.roadmap_item_id,issue:parentRecord.issue,pr:parentRecord.pr,decision_id:parentRecord.decision_id,authorization_mode:"POLICY_APPROVED",base_sha:parentRecord.base_sha,closeout_base_sha:parentRecord.head_sha,head_sha:parentRecord.head_sha,merge_commit:parentRecord.head_sha,builder_session:parentRecord.builder_session,reviewer_session:parentRecord.reviewer_session,...(semanticHash!==undefined?{semantic_decision_sha256:semanticHash}:{})};
  const serialized=JSON.stringify(evidence),instruction=`Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: ${serialized}`;
  return {...child,objective:`${(child.objective??"").trim()}\n\nPARENT_LIFECYCLE_EVIDENCE_JSON=${serialized}`,acceptance:[...child.acceptance,instruction]};
}
/** CLOSEOUT_PENDING parent with complete merge/decision evidence, as assertCloseoutChild requires. */
function closeoutPendingParentRecord(parent:ProxySpec,extraEffects:string[]=[]):LifecycleRecord{
  const head="f".repeat(40);
  return {schema_version:1,front_id:parent.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"CLOSEOUT_PENDING",base_sha:parent.expected_base_sha,head_sha:head,issue:246,pr:247,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:246",`build:${head}`,`merge:${head}`,...extraEffects],builder_session:"parent-builder",reviewer_session:"parent-reviewer",decision_id:"11111111-1111-4111-8111-111111111111",updated_utc:"2026-09-10T00:00:00.000Z"};
}
function childBusFixture(child:ProxySpec,parentRecord:LifecycleRecord,childHead:string,childBase="d".repeat(40),semanticHash?:string){
  return {
    issueSnapshot:()=>({body:`${issueBody(persistedSemanticCloseoutSpec(child,parentRecord,semanticHash)).trim()}\n\nOPERATOR_PROXY_PR: 249\n`}),
    prIdentity:()=>({author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:childBase,headRefName:child.work_branch,headRefOid:childHead,headRepository:{nameWithOwner:"cesarmanuel8102/AI_Vault"},isCrossRepository:false,isDraft:true,state:"OPEN"}),
    isAncestor:(left:string,right:string)=>left===right,
  };
}

test("MATCHING_PARENT_AND_CHILD_HASH admits the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,withReceipt,"e".repeat(40),"d".repeat(40),decision.decision_artifact_sha256);
  const resolved=resolveExecutableFront(bus,store,parent);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
  assert.equal(resolved.spec.front_id,child.front_id);
  // The child must never be independently semantic-bound.
  assert.equal(resolved.spec.semantic_completion,undefined);
});

test("MISSING_PARENT_RECEIPT rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-blocked-")));
  const parentRecord=closeoutPendingParentRecord(parent); // no semantic receipt
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40),"d".repeat(40),"a".repeat(64));
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout parent semantic receipt missing/);
});

test("MISSING_CHILD_HASH rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-nohash-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,withReceipt,"e".repeat(40)); // no semantic hash in evidence
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout child semantic decision hash missing/);
});

test("DIFFERENT_CHILD_HASH rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-diff-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const differentHash="9".repeat(64);
  const bus=childBusFixture(child,withReceipt,"e".repeat(40),"d".repeat(40),differentHash);
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout child semantic decision hash mismatch/);
});

test("MALFORMED_CHILD_HASH rejects the closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-malformed-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const withReceipt=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`]);
  store.save(withReceipt);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,withReceipt,"e".repeat(40),"d".repeat(40),"NOT-A-VALID-HASH");
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout child semantic decision hash invalid/);
});

test("MULTIPLE_CONFLICTING_PARENT_RECEIPTS fail closed",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-conflict-")));
  const decision=productionResolveSemanticCompletion(parent,"f".repeat(40),trustedSource());
  const conflicting=closeoutPendingParentRecord(parent,[`semantic_completion:${decision.decision_artifact_sha256}`,`semantic_completion:${"9".repeat(64)}`]);
  store.save(conflicting);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,conflicting,"e".repeat(40),"d".repeat(40),decision.decision_artifact_sha256);
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout parent semantic receipts conflict/);
});

test("closeout child never inherits semantic binding from its parent",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  assert.equal(parent.semantic_completion!==undefined,true);
  assert.equal(child.semantic_completion,undefined,"closeoutSpec must strip semantic_completion from the child");
  assert.equal(child.closeout_only,true);
});

test("non-semantic parent closeout child selection is unchanged",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const plain={...parent,semantic_completion:undefined};
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-plain-")));
  const parentRecord=closeoutPendingParentRecord(plain);
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:plain.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40));
  const resolved=resolveExecutableFront(bus,store,plain);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
});

test("semantic parent without a semantic receipt cannot authorize a closeout child",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-blocked-")));
  const parentRecord=closeoutPendingParentRecord(parent); // no semantic receipt
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:parent.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40));
  assert.throws(()=>resolveExecutableFront(bus,store,parent),/closeout parent semantic receipt missing/);
});

test("non-semantic parent closeout child selection is unchanged",()=>{
  const {parent,child}=semanticParentWithCloseoutSpec();
  const plain={...parent,semantic_completion:undefined};
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-child-plain-")));
  const parentRecord=closeoutPendingParentRecord(plain);
  store.save(parentRecord);
  store.save({schema_version:1,front_id:child.front_id!,roadmap_item_id:plain.roadmap_item_id,state:"BUILDING",base_sha:"d".repeat(40),head_sha:"e".repeat(40),issue:248,pr:249,repair_cycles:0,deployment_mode:"NO_DEPLOY",completed_effects:["issue:248","build:"+"e".repeat(40)],builder_session:"child-builder",updated_utc:"2026-09-10T00:00:00.000Z"});
  const bus=childBusFixture(child,parentRecord,"e".repeat(40));
  const resolved=resolveExecutableFront(bus,store,plain);
  assert.equal(resolved.source,"NONTERMINAL_CLOSEOUT_CHILD");
});
// ---------------------------------------------------------------------------
// P1-1: PRODUCTION canonical Git resolution via GitHubBus.fileAt(path, merge).
// The productive resolver must not depend on an externally pre-bound source.
// ---------------------------------------------------------------------------
const requirementsPath="docs/roadmap/semantic/requirements.json";
const evidencePath="docs/roadmap/semantic/evidence.json";
const canonicalRequirementsJson=JSON.stringify({schema_version:1,requirements:[{...authoritativeRequirement}]});
const canonicalEvidenceJson=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence}]});

/** Fake GitHubBus recording exact (path, ref) calls. */
function fileAtBus(files:Record<string,string>,options?:{throwOnMissing?:boolean}){
  const calls:{path:string;ref:string}[]=[];
  const bus:any={
    setMutationGuard:()=>{},
    fileAt:(path:string,ref:string)=>{
      calls.push({path,ref});
      if(!(path in files)){if(options?.throwOnMissing!==false)throw new Error("not found");return undefined;}
      return files[path];
    },
  };
  return {bus,calls:()=>calls};
}

/** Canonical semantic registry mapping the item to its authoritative paths. */
const semanticRegistryPath="docs/roadmap/semantic/semantic_registry.json";
const canonicalRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:evidencePath}}});
/** fileAtBus with the canonical registry pre-seeded (the default production case). */
function registryFileAtBus(files:Record<string,string>){
  return fileAtBus({[semanticRegistryPath]:canonicalRegistry,...files});
}

function productionEffectsWithBus(bus:any){
  const root=mkdtempSync(join(tmpdir(),"sem-prod-"));
  const boundary:any={assert:()=>{},bind:()=>{}};
  return new ProductionEffects(bus,new Ledger(join(root,"decisions")),root,root,boundary);
}

test("production resolver reads requirements and evidence at the exact bound merge SHA",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]});
  const {bus,calls}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
  const requirementReads=calls().filter(call=>call.path===requirementsPath);
  const evidenceReads=calls().filter(call=>call.path===evidencePath);
  const artifactReads=calls().filter(call=>call.path===artifactPath);
  assert.equal(requirementReads.length,1);assert.equal(requirementReads[0].ref,merge);
  assert.equal(evidenceReads.length,1);assert.equal(evidenceReads[0].ref,merge);
  assert.equal(artifactReads.length,1);assert.equal(artifactReads[0].ref,merge);
});

test("production resolver does not require an externally bound semantic source",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]});
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  // No bindSemanticSource call: production must resolve canonically by itself.
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

test("production resolver rejects caller-supplied artifact bytes by resolving from Git only",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]});
  const {bus,calls}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:"tampered-by-attacker"});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["ARTIFACT_HASH_MISMATCH"]);
  assert.ok(calls().some(call=>call.path===artifactPath&&call.ref===merge));
});

test("production resolver fails closed when canonical bytes are missing",()=>{
  const merge="f".repeat(40);
  for(const missing of [requirementsPath,evidencePath,artifactPath]){
    const files:Record<string,string>={[requirementsPath]:canonicalRequirementsJson,[evidencePath]:canonicalEvidenceJson,[artifactPath]:artifact};
    delete files[missing];
    const {bus}=registryFileAtBus(files);
    const effects=productionEffectsWithBus(bus);
    assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic resolution failed/,missing);
  }
});

test("production resolver binds source_sha to the bound lifecycle merge SHA",()=>{
  const merge="f".repeat(40);
  // Evidence claims SHA "b" — stale against the bound merge SHA "f".
  const staleEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:"b".repeat(40),certified_implementation_sha:"b".repeat(40)}]});
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:staleEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["STALE_SOURCE_SHA"]);
});

test("production resolver never rewrites evidence SHA values",()=>{
  const merge="f".repeat(40);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:canonicalEvidenceJson,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  // Valid case: evidence SHA "a" == merge SHA "a"? No — evidence.source_sha is "a".repeat(40)
  // and the bound merge is "f".repeat(40); a mismatch must BLOCK (not be rewritten to PASS).
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  // The canonical fixture's evidence binds source_sha "a" — the merge is "f",
  // so this must be STALE unless the fixture is rebuilt. This asserts no rewriting.
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["STALE_SOURCE_SHA"]);
});

test("production resolver accepts evidence whose SHA equals the bound merge SHA",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]});
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

// ---------------------------------------------------------------------------
// P2-1: strict canonical timestamps for EVERY trusted-boundary timestamp.
// ---------------------------------------------------------------------------
test("NONCANONICAL_OBSERVED_AT_REJECTED at the trust boundary",()=>{
  for(const bad of ["September 10, 2026","09/10/2026","2026-09-10T00:00:00+02:00","2026-09-10 00:00:00Z","2026-09-10T00:00Z","2026-13-45T99:99:99.999Z","2026-02-30T00:00:00.000Z"]){
    const merge="f".repeat(40);
    const badEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge,observed_at_utc:bad}]});
    const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:badEvidence,[artifactPath]:artifact});
    const effects=productionEffectsWithBus(bus);
    assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/not canonical UTC timestamp/,bad);
  }
});

test("NONCANONICAL_AUTHORIZED_AT_REJECTED at the trust boundary",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]});
  const auth=JSON.stringify([{authorization_id:"AUTH-1",requirement_id:authoritativeRequirement.requirement_id,authorization_source_sha:sha("owner authorization"),authorized_by:"owner",scope:"BR1",authorized_at_utc:"09/10/2026"}]);
  // The evidence JSON needs a deferments+authorizations structure: pack both files.
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  // Resolve through the exported trust-boundary function with a hostile source.
  const hostileSource=trustedSource();
  (hostileSource as any).semanticDefermentAuthorizations=()=>JSON.parse(auth);
  assert.throws(()=>resolveSemanticInput(parentSpec,hostileSource),/not canonical UTC timestamp/);
});

test("CANONICAL_ALL_TIMESTAMPS_ACCEPTED at the trust boundary",()=>{
  const merge="f".repeat(40);
  const boundEvidence=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge,observed_at_utc:"2026-09-10T00:00:00.000Z"}]});
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:boundEvidence,[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

// ---------------------------------------------------------------------------
// closeoutParentEvidence binds semantic_decision_sha256 (P1-2 end-to-end).
// ---------------------------------------------------------------------------
test("closeout parent evidence carries semantic_decision_sha256 for a semantic-bound parent",()=>{
  const root=mkdtempSync(join(tmpdir(),"sem-evidence-"));
  const ledger=new Ledger(join(root,"decisions"));
  const merge="f".repeat(40),candidate="9".repeat(40);
  const decisionKey=sha("decision-key");
  const decisionId=stableDecisionId(decisionKey);
  ledger.record({schema_version:2,decision_key:decisionKey,decision_id:decisionId,authorization_id:parentSpec.authorization_id,repository:parentSpec.repository,issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:candidate,roadmap_id:parentSpec.roadmap_id,roadmap_item_id:parentSpec.roadmap_item_id,risk:"LOW",deterministic_gate:"PASS",codex_review:"PASS",review_findings_count:0,review_consistent:true,policy_decision:"APPROVE",allowed_action:"MERGE",policy_sha256:POLICY_SHA256,evidence_sha256:"e".repeat(64),created_utc:"2026-09-10T00:00:00.000Z"} as any);
  ledger.ensureConsumed(ledger.findByKey(decisionKey)!);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=new ProductionEffects(bus,ledger,root,root,{assert:()=>{},bind:()=>{}} as any);
  const semanticDecision=effects.resolveSemanticCompletion(parentSpec,merge);
  effects.bindLifecycle(parentSpec,{schema_version:1,front_id:parentSpec.front_id!,roadmap_item_id:parentSpec.roadmap_item_id,state:"CLOSEOUT_PENDING",issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:merge,builder_session:"builder-parent",reviewer_session:"reviewer-parent",decision_id:decisionId,repair_cycles:0,deployment_mode:"DOCUMENTATION_CLOSEOUT",completed_effects:["issue:77",`build:${candidate}`,`merge:${merge}`,`semantic_completion:${semanticDecision.decision_artifact_sha256}`],updated_utc:"2026-09-10T00:00:00.000Z"});
  const evidence=(effects as any).closeoutParentEvidence(parentSpec,merge);
  assert.equal(evidence.semantic_decision_sha256,semanticDecision.decision_artifact_sha256);
  assert.match(evidence.semantic_decision_sha256,/^[0-9a-f]{64}$/);
});

test("closeout parent evidence fails closed with zero or conflicting semantic receipts",()=>{
  const root=mkdtempSync(join(tmpdir(),"sem-evidence-deny-"));
  const ledger=new Ledger(join(root,"decisions"));
  const merge="f".repeat(40),candidate="9".repeat(40);
  const decisionKey=sha("decision-key-deny");
  const decisionId=stableDecisionId(decisionKey);
  ledger.record({schema_version:2,decision_key:decisionKey,decision_id:decisionId,authorization_id:parentSpec.authorization_id,repository:parentSpec.repository,issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:candidate,roadmap_id:parentSpec.roadmap_id,roadmap_item_id:parentSpec.roadmap_item_id,risk:"LOW",deterministic_gate:"PASS",codex_review:"PASS",review_findings_count:0,review_consistent:true,policy_decision:"APPROVE",allowed_action:"MERGE",policy_sha256:POLICY_SHA256,evidence_sha256:"e".repeat(64),created_utc:"2026-09-10T00:00:00.000Z"} as any);
  ledger.ensureConsumed(ledger.findByKey(decisionKey)!);
  const {bus}=fileAtBus({});
  const effects=new ProductionEffects(bus,ledger,root,root,{assert:()=>{},bind:()=>{}} as any);
  // Zero receipts.
  effects.bindLifecycle(parentSpec,{schema_version:1,front_id:parentSpec.front_id!,roadmap_item_id:parentSpec.roadmap_item_id,state:"CLOSEOUT_PENDING",issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:merge,builder_session:"builder-parent",reviewer_session:"reviewer-parent",decision_id:decisionId,repair_cycles:0,deployment_mode:"DOCUMENTATION_CLOSEOUT",completed_effects:["issue:77",`build:${candidate}`,`merge:${merge}`],updated_utc:"2026-09-10T00:00:00.000Z"});
  assert.throws(()=>(effects as any).closeoutParentEvidence(parentSpec,merge),/closeout parent semantic receipt missing/);
  // Conflicting receipts.
  const store=new LifecycleStore(join(root,"lifecycle"));
  const conflicting={schema_version:1,front_id:parentSpec.front_id!,roadmap_item_id:parentSpec.roadmap_item_id,state:"CLOSEOUT_PENDING",issue:77,pr:78,base_sha:parentSpec.expected_base_sha,head_sha:merge,builder_session:"builder-parent",reviewer_session:"reviewer-parent",decision_id:decisionId,repair_cycles:0,deployment_mode:"DOCUMENTATION_CLOSEOUT",completed_effects:["issue:77",`build:${candidate}`,`merge:${merge}`,`semantic_completion:${"a".repeat(64)}`,`semantic_completion:${"9".repeat(64)}`],updated_utc:"2026-09-10T00:00:00.000Z"} as LifecycleRecord;
  store.save(conflicting);
  effects.bindLifecycle(parentSpec,conflicting);
  assert.throws(()=>(effects as any).closeoutParentEvidence(parentSpec,merge),/closeout parent semantic receipts conflict/);
});

// ---------------------------------------------------------------------------
// FINAL REMEDIATION P1-1: canonical registry binding — the caller may name the
// item but may never choose the authoritative registry paths.
// ---------------------------------------------------------------------------

test("hostile requirements_path substitution is rejected",()=>{
  const merge="f".repeat(40);
  const hostile={...parentSpec,semantic_completion:{requirements_path:"attacker/requirements.json",evidence_path:evidencePath}};
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact,["attacker/requirements.json"]:JSON.stringify([{...authoritativeRequirement,minimum_evidence_level:"L0_PRESENCE"}])});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(hostile,merge),/SEMANTIC_CANONICAL_BINDING_MISMATCH|canonical semantic registry/);
});

test("hostile evidence_path substitution is rejected",()=>{
  const merge="f".repeat(40);
  const hostile={...parentSpec,semantic_completion:{requirements_path:requirementsPath,evidence_path:"attacker/evidence.json"}};
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact,["attacker/evidence.json"]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,evidence_level:"L0_PRESENCE"}]})});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(hostile,merge),/SEMANTIC_CANONICAL_BINDING_MISMATCH|canonical semantic registry/);
});

test("alternate weaker registry selected through spec paths is rejected",()=>{
  const merge="f".repeat(40);
  // Even if BOTH attacker files exist in the repo at the merge, the spec may
  // not point at them: the canonical registry mapping is the only authority.
  const hostile={...parentSpec,semantic_completion:{requirements_path:"attacker/weak-requirements.json",evidence_path:"attacker/weak-evidence.json"}};
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact,["attacker/weak-requirements.json"]:JSON.stringify([{...authoritativeRequirement,minimum_evidence_level:"L0_PRESENCE"}]),["attacker/weak-evidence.json"]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,evidence_level:"L0_PRESENCE",source_sha:merge,certified_implementation_sha:merge}]})});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(hostile,merge),/SEMANTIC_CANONICAL_BINDING_MISMATCH|canonical semantic registry/);
});

test("correct canonical registry mapping passes",()=>{
  const merge="f".repeat(40);
  const {bus}=fileAtBus({[semanticRegistryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

test("unknown roadmap item in the canonical registry fails closed",()=>{
  const merge="f".repeat(40);
  const emptyRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{}});
  const {bus}=fileAtBus({[semanticRegistryPath]:emptyRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("missing canonical registry file fails closed",()=>{
  const merge="f".repeat(40);
  // NO registry in the fixture — the registry file itself is absent.
  const {bus}=fileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

// ---------------------------------------------------------------------------
// FINAL REMEDIATION P1-2: no runtime source substitution inside ProductionEffects.
// ---------------------------------------------------------------------------
test("ProductionEffects exposes no runtime source injection API",()=>{
  const effects=productionEffectsWithBus(fileAtBus({}).bus);
  assert.equal("bindSemanticSource" in effects,false,"bindSemanticSource must not exist on the production class");
  assert.equal((effects as any).semanticSource,undefined,"no injectable semantic source field may remain");
});

// ---------------------------------------------------------------------------
// FINAL REMEDIATION P1-3: semantic decision idempotency at CLOSEOUT_PENDING.
// ---------------------------------------------------------------------------
function flowFixtureWithResolver(resolver:(spec:ProxySpec,merge:string)=>SemanticCompletionDecisionV1,closeoutResult:()=>"PASS"|"PENDING"){
  let semanticCalls=0,closeoutCalls=0,nextCalls=0;
  const effects:AutonomousEffects={
    bindLifecycle:()=>{},
    resolveSemanticCompletion:(spec,merge)=>{semanticCalls++;return resolver(spec,merge);},
    ensureIssue:()=>70,
    ensureBuild:(_s,_i,session)=>Promise.resolve({pr:71,head_sha:"b".repeat(40),session}),
    ci:()=>"PASS",
    review:(_p,head,session)=>({session:`actual-${session}`,output:{verdict:"PASS",head_sha:head,summary:"PASS",findings:[]} as ReviewerOutput}),
    policy:()=>({outcome:"APPROVE",decision_id:"d".repeat(8)+"-4b3e-4c99-9f2e-1a2b3c4d5e6f"}),
    ensureMerge:()=>"f".repeat(40),
    ensureInstall:()=>"PASS",
    ensureRuntimePilot:()=>"PASS",
    ensureCloseout:()=>{closeoutCalls++;return Promise.resolve(closeoutResult());},
    discoverNext:()=>{nextCalls++;},
  };
  return {effects,counts:()=>({semanticCalls,closeoutCalls,nextCalls})};
}
const fixedDecision={schema_version:1 as const,phase_or_item_id:parentSpec.roadmap_item_id,original_requirement_refs:Object.freeze([authoritativeRequirement.requirement_id]),requirements_total:1,requirements_satisfied:1,requirements_deferred_valid:0,requirements_blocked:0,evidence_refs:Object.freeze(["EVIDENCE-R15-001"]),decision:"PASS" as const,reason_codes:Object.freeze([]),source_sha:"f".repeat(40),evaluated_at_utc:"2026-09-10T00:00:00.000Z",decision_artifact_sha256:"a".repeat(64)};

test("PASS then closeout PENDING retry reuses the receipt and never re-resolves",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-")));
  const resolverCalls:{hash:string}[]=[];
  const f=flowFixtureWithResolver(()=>{
    // Wall-clock drift simulation: each resolution returns a DIFFERENT hash.
    const hash=sha("hash-"+resolverCalls.length);
    resolverCalls.push({hash});
    return {...fixedDecision,decision_artifact_sha256:hash};
  },()=> "PENDING");
  const flow=new AutonomousFlow(store,f.effects);
  // Step manually until the semantic gate has run inside CLOSEOUT_PENDING
  // (the state then still reports CLOSEOUT_PENDING after a PENDING closeout).
  let state:LifecycleRecord=await flow.step(parentSpec);
  for(let i=0;i<40&&state.state!=="BLOCKED"&&(state.state!=="CLOSEOUT_PENDING"||!state.completed_effects.some(e=>e.startsWith("semantic_completion:")));i++)state=await flow.step(parentSpec);
  assert.equal(state.state,"CLOSEOUT_PENDING");
  const receiptsAfterFirst=state.completed_effects.filter(e=>e.startsWith("semantic_completion:"));
  assert.equal(receiptsAfterFirst.length,1);
  // Retry: wall clock advanced → resolver would return a different hash, but
  // the flow MUST NOT call it again.
  state=await flow.step(parentSpec);
  assert.equal(f.counts().semanticCalls,1,"semantic resolver must be called exactly once");
  assert.equal(f.counts().closeoutCalls,2,"closeout retried");
  const receiptsAfterRetry=state.completed_effects.filter(e=>e.startsWith("semantic_completion:"));
  assert.equal(receiptsAfterRetry.length,1,"exactly one semantic receipt after retry");
  assert.equal(receiptsAfterRetry[0],receiptsAfterFirst[0],"receipt unchanged after wall-clock drift");
});

test("closeout eventually PASSes after retries with exactly one receipt",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-pass-")));
  let pendingCount=0;
  const f=flowFixtureWithResolver(()=>fixedDecision,()=> ++pendingCount<3?"PENDING":"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  let state:LifecycleRecord=await drive(flow,parentSpec);
  for(let i=0;i<5&&state.state==="CLOSEOUT_PENDING";i++)state=await flow.step(parentSpec);
  assert.equal(state.state,"TERMINAL_COMPLETED");
  const receipts=state.completed_effects.filter(e=>e.startsWith("semantic_completion:"));
  assert.equal(receipts.length,1);
  assert.equal(f.counts().semanticCalls,1,"resolver called exactly once across all retries");
});

test("existing single valid receipt skips semantic resolution entirely",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-skip-")));
  const head="f".repeat(40);
  // Pre-persist a record already holding a receipt, sitting at CLOSEOUT_PENDING.
  const seeded=semanticParentRecord(parentSpec);
  store.save({...seeded,head_sha:head,completed_effects:[...seeded.completed_effects,`semantic_completion:${"c".repeat(64)}`]});
  let resolverShouldNotBeCalled=false;
  const f=flowFixtureWithResolver(()=>{if(resolverShouldNotBeCalled)throw new Error("resolver must not be called");return fixedDecision;},()=>"PASS");
  resolverShouldNotBeCalled=true;
  const flow=new AutonomousFlow(store,f.effects);
  const state=await flow.step(parentSpec);
  assert.equal(state.state,"CLOSEOUT_MERGED");
  assert.equal(f.counts().semanticCalls,0);
});

test("multiple distinct pre-existing receipts fail closed before closeout",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-conflict-")));
  const head="f".repeat(40);
  const base=semanticParentRecord(parentSpec);
  store.save({...base,head_sha:head,completed_effects:[...base.completed_effects,`semantic_completion:${"a".repeat(64)}`,`semantic_completion:${"9".repeat(64)}`]});
  const f=flowFixtureWithResolver(()=>fixedDecision,()=>"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  const state=await flow.step(parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(f.counts().closeoutCalls,0,"no closeout may run on conflicting receipts");
});

test("malformed pre-existing receipt fails closed",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-malformed-")));
  const head="f".repeat(40);
  const base=semanticParentRecord(parentSpec);
  store.save({...base,head_sha:head,completed_effects:[...base.completed_effects,"semantic_completion:NOT-A-HASH"]});
  const f=flowFixtureWithResolver(()=>fixedDecision,()=>"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  const state=await flow.step(parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
});

test("BLOCK decision persists no receipt and blocks closeout",async()=>{
  const store=new LifecycleStore(mkdtempSync(join(tmpdir(),"sem-retry-block-")));
  const blockedDecision={...fixedDecision,decision:"BLOCK" as const,reason_codes:Object.freeze(["INSUFFICIENT_EVIDENCE_LEVEL" as const])};
  const f=flowFixtureWithResolver(()=>blockedDecision,()=>"PASS");
  const flow=new AutonomousFlow(store,f.effects);
  let state:LifecycleRecord=await flow.step(parentSpec);
  for(let i=0;i<40&&state.state!=="BLOCKED"&&state.state!=="TERMINAL_COMPLETED";i++)state=await flow.step(parentSpec);
  assert.equal(state.state,"BLOCKED");
  assert.equal(state.last_error,"SEMANTIC_COMPLETION_BLOCK");
  assert.equal(state.completed_effects.some(e=>e.startsWith("semantic_completion:")),false);
  assert.equal(f.counts().closeoutCalls,0);
});

// ---------------------------------------------------------------------------
// FINAL P1-1/P1-2: canonical registry identity binding + closed shape +
// real-Git integration.
// ---------------------------------------------------------------------------
const otherRoadmapRegistry=JSON.stringify({schema_version:1,roadmap_id:"OTHER-ROADMAP",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:evidencePath}}});

test("REGISTRY wrong roadmap_id with correct item is rejected (cross-roadmap collision)",()=>{
  const merge="f".repeat(40);
  const {bus}=fileAtBus({[semanticRegistryPath]:otherRoadmapRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/SEMANTIC_CANONICAL_REGISTRY_IDENTITY_MISMATCH|canonical semantic registry/);
});

test("REGISTRY correct roadmap_id with wrong item is rejected",()=>{
  const merge="f".repeat(40);
  const wrongItemRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{R99:{requirements_path:requirementsPath,evidence_path:evidencePath}}});
  const {bus}=fileAtBus({[semanticRegistryPath]:wrongItemRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("REGISTRY missing roadmap_id is rejected",()=>{
  const merge="f".repeat(40);
  const noRoadmapId=JSON.stringify({schema_version:1,roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:evidencePath}}});
  const {bus}=fileAtBus({[semanticRegistryPath]:noRoadmapId,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("REGISTRY wrong schema_version is rejected",()=>{
  const merge="f".repeat(40);
  const wrongSchema=JSON.stringify({schema_version:2,roadmap_id:"BRAIN-101",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:evidencePath}}});
  const {bus}=fileAtBus({[semanticRegistryPath]:wrongSchema,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("REGISTRY empty requirements_path is rejected",()=>{
  const merge="f".repeat(40);
  const emptyReq=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:"",evidence_path:evidencePath}}});
  const {bus}=fileAtBus({[semanticRegistryPath]:emptyReq,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("REGISTRY empty evidence_path is rejected",()=>{
  const merge="f".repeat(40);
  const emptyEv=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:""}}});
  const {bus}=fileAtBus({[semanticRegistryPath]:emptyEv,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("REGISTRY wrong field types are rejected",()=>{
  const merge="f".repeat(40);
  const wrongTypes=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:42,evidence_path:true}}});
  const {bus}=fileAtBus({[semanticRegistryPath]:wrongTypes,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("REGISTRY unknown extra top-level field is rejected (closed shape)",()=>{
  const merge="f".repeat(40);
  const extraField=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",extra:"attacker",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:evidencePath}}});
  const {bus}=fileAtBus({[semanticRegistryPath]:extraField,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  assert.throws(()=>effects.resolveSemanticCompletion(parentSpec,merge),/canonical semantic registry/);
});

test("REGISTRY matching roadmap_id and item with canonical paths passes",()=>{
  const merge="f".repeat(40);
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
  const effects=productionEffectsWithBus(bus);
  const decision=effects.resolveSemanticCompletion(parentSpec,merge);
  assert.equal(decision.decision,"PASS");
});

// ---------------------------------------------------------------------------
// REAL-GIT integration contract: reads the actual committed registry artifact
// from the repository (no fake fileAt injection).
// ---------------------------------------------------------------------------
import {execFileSync} from "node:child_process";
import {existsSync,readFileSync} from "node:fs";

test("REAL_GIT_REGISTRY the committed canonical registry resolves BRAIN-101/R15 to the expected paths",()=>{
  // The registry must exist as a tracked worktree artifact.
  const registryPath="docs/roadmap/semantic/semantic_registry.json";
  assert.equal(existsSync(registryPath),true,"canonical semantic registry must be a committed repository artifact");
  const bytes=readFileSync(registryPath,"utf8");
  // Real committed bytes parse and bind the governed item identity.
  const registry=JSON.parse(bytes);
  assert.equal(registry.schema_version,1);
  assert.equal(registry.roadmap_id,"BRAIN-101");
  const item=registry.roadmap_items[parentSpec.roadmap_item_id];
  assert.ok(item,"registry must bind the governed roadmap item");
  assert.equal(typeof item.requirements_path,"string");
  assert.equal(typeof item.evidence_path,"string");
  assert.ok(item.requirements_path.length>0);
  assert.ok(item.evidence_path.length>0);
  // The binding must satisfy the spec's declared paths exactly (they came
  // from the same governed source).
  assert.equal(item.requirements_path,requirementsPath);
  assert.equal(item.evidence_path,evidencePath);
  // The artifact must be tracked by Git (not just a stray worktree file).
  const tracked=execFileSync("git",["ls-files","--",registryPath],{encoding:"utf8"}).trim();
  assert.equal(tracked,registryPath,"registry must be tracked in Git");
  // Closed shape on real bytes: exactly the four governed keys.
  assert.deepEqual(Object.keys(registry).sort(),["roadmap_id","roadmap_items","schema_version"]);
  assert.deepEqual(Object.keys(item).sort(),["evidence_path","requirements_path"]);
});

// ---------------------------------------------------------------------------
// REAL-GIT FULL ARTIFACT CHAIN: registry → requirements → evidence →
// artifact bytes at exact candidate-commit SHAs. No fake-bus injection.
// ---------------------------------------------------------------------------
const registryPath="docs/roadmap/semantic/semantic_registry.json";

test("CHAIN registry pointing to missing requirements fails closed",()=>{
  const merge="f".repeat(40);
  const orphanRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{R15:{requirements_path:"docs/roadmap/semantic/absent-requirements.json",evidence_path:evidencePath}}});
  const {bus}=fileAtBus({[registryPath]:orphanRegistry,[evidencePath]:JSON.stringify({schema_version:1,evidence:[]})});
  const effects=productionEffectsWithBus(bus);
  const specWithoutDeclared={...parentSpec,semantic_completion:undefined};
  assert.throws(()=>effects.resolveSemanticCompletion({...specWithoutDeclared,semantic_completion:{requirements_path:"docs/roadmap/semantic/absent-requirements.json",evidence_path:evidencePath}},merge),/canonical semantic resolution failed/);
});

test("CHAIN registry pointing to missing evidence fails closed",()=>{
  const merge="f".repeat(40);
  const orphanRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{R15:{requirements_path:requirementsPath,evidence_path:"docs/roadmap/semantic/absent-evidence.json"}}});
  const {bus}=fileAtBus({[registryPath]:orphanRegistry,[requirementsPath]:canonicalRequirementsJson});
  const specWithoutDeclared={...parentSpec,semantic_completion:undefined};
  assert.throws(()=>productionEffectsWithBus(bus).resolveSemanticCompletion({...specWithoutDeclared,semantic_completion:{requirements_path:requirementsPath,evidence_path:"docs/roadmap/semantic/absent-evidence.json"}},merge),/canonical semantic resolution failed/);
});

test("CHAIN malformed requirements fail closed",()=>{
  const merge="f".repeat(40);
  const {bus}=fileAtBus({[registryPath]:canonicalRegistry,[requirementsPath]:"{not-json",[evidencePath]:JSON.stringify({schema_version:1,evidence:[]})});
  const specWithoutDeclared={...parentSpec,semantic_completion:undefined};
  assert.throws(()=>productionEffectsWithBus(bus).resolveSemanticCompletion({...specWithoutDeclared,semantic_completion:{requirements_path:requirementsPath,evidence_path:evidencePath}},merge),/canonical semantic resolution failed/);
});

test("CHAIN malformed evidence fails closed",()=>{
  const merge="f".repeat(40);
  const {bus}=fileAtBus({[registryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:"[[[bad"});
  const specWithoutDeclared={...parentSpec,semantic_completion:undefined};
  assert.throws(()=>productionEffectsWithBus(bus).resolveSemanticCompletion({...specWithoutDeclared,semantic_completion:{requirements_path:requirementsPath,evidence_path:evidencePath}},merge),/canonical semantic resolution failed/);
});

test("CHAIN evidence artifact missing at source SHA fails closed",()=>{
  const merge="f".repeat(40);
  // Evidence references an artifact path that does not exist at the merge.
  const evidenceWithGhostArtifact=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge,artifact_path:"docs/roadmap/evidence/ghost.json",artifact_sha256:sha("ghost")}]});
  const {bus}=fileAtBus({[registryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:evidenceWithGhostArtifact});
  const specWithoutDeclared={...parentSpec,semantic_completion:undefined};
  assert.throws(()=>productionEffectsWithBus(bus).resolveSemanticCompletion({...specWithoutDeclared,semantic_completion:{requirements_path:requirementsPath,evidence_path:evidencePath}},merge),/canonical semantic resolution failed/);
});

test("CHAIN evidence artifact hash mismatch blocks",()=>{
  const merge="f".repeat(40);
  const evidenceTampered=JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge,artifact_sha256:sha("tampered-not-real")}]});
  const {bus}=fileAtBus({[registryPath]:canonicalRegistry,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:evidenceTampered,[artifactPath]:artifact});
  const specWithoutDeclared={...parentSpec,semantic_completion:undefined};
  const decision=productionEffectsWithBus(bus).resolveSemanticCompletion({...specWithoutDeclared,semantic_completion:{requirements_path:requirementsPath,evidence_path:evidencePath}},merge);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["ARTIFACT_HASH_MISMATCH"]);
});

test("REAL_GIT_FULL_CHAIN canonical artifacts at the real commit resolve the complete authority tree",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const show=(path:string)=>execFileSync("git",["show",`${candidate}:${path}`],{encoding:"utf8"});
  // Immutable candidate-commit reads — not worktree state.
  const registryBytes=show(registryPath);
  const registry=JSON.parse(registryBytes);
  assert.equal(registry.schema_version,1);
  assert.equal(registry.roadmap_id,"BRAIN-101");
  assert.ok(registry.roadmap_items.R15,"registry must bind R15");
  const binding=registry.roadmap_items.R15;
  assert.equal(binding.requirements_path,"docs/roadmap/semantic/requirements.json");
  assert.equal(binding.evidence_path,"docs/roadmap/semantic/evidence.json");
  // Leaf artifacts exist AT THE CANDIDATE COMMIT.
  const requirementsBytes=show(binding.requirements_path);
  const requirementsDoc=JSON.parse(requirementsBytes);
  assert.equal(requirementsDoc.schema_version,1);
  assert.ok(Array.isArray(requirementsDoc.requirements)&&requirementsDoc.requirements.length>0);
  // Every requirement binds to real roadmap bytes and real requirement text.
  const roadmapBytes=show("docs/roadmap/BRAIN_101_ROADMAP.md");
  const roadmapSha=createHash("sha256").update(roadmapBytes).digest("hex");
  for(const requirement of requirementsDoc.requirements){
    assert.equal(requirement.original_spec_path,"docs/roadmap/BRAIN_101_ROADMAP.md");
    assert.equal(requirement.original_spec_sha256,roadmapSha,"requirement must bind the real roadmap bytes at the candidate commit");
    assert.match(requirement.requirement_text_sha256,/^[0-9a-f]{64}$/);
    assert.ok(requirement.minimum_duration_seconds>0);
  }
  // The exact requirement text is present in the roadmap bytes.
  const evidenceBytes=show(binding.evidence_path);
  const evidenceDoc=JSON.parse(evidenceBytes);
  assert.equal(evidenceDoc.schema_version,1);
  assert.ok(Array.isArray(evidenceDoc.evidence));
  // Every real evidence artifact must exist at ITS bound source SHA with matching hash.
  for(const record of evidenceDoc.evidence){
    const artifactBytes=execFileSync("git",["show",`${record.source_sha}:${record.artifact_path}`],{encoding:"utf8"});
    assert.equal(createHash("sha256").update(artifactBytes).digest("hex"),record.artifact_sha256,"evidence artifact hash must match the exact Git bytes at its source SHA");
  }
  // The productive resolver consumes those exact Git bytes end-to-end.
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"})} as any;
  const effects=productionEffectsWithBus(gitReadBus);
  const realSpec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:binding.requirements_path,evidence_path:binding.evidence_path}};
  const decision=effects.resolveSemanticCompletion(realSpec,candidate);
  assert.equal(decision.decision,"BLOCK");
  assert.deepEqual([...decision.reason_codes],["MISSING_EVIDENCE"],"truthful canonical decision: the real R15 soak requirement has no qualifying canonical evidence yet");
});

test("REAL_GIT_FULL_CHAIN decision matches the actual repository evidence state",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const show=(path:string)=>execFileSync("git",["show",`${candidate}:${path}`],{encoding:"utf8"});
  const registry=JSON.parse(show(registryPath));
  const binding=registry.roadmap_items.R15;
  const requirementsDoc=JSON.parse(show(binding.requirements_path));
  const evidenceDoc=JSON.parse(show(binding.evidence_path));
  // Truthful cross-check: decision BLOCK iff evidence array cannot satisfy requirements.
  assert.equal(evidenceDoc.evidence.length===0&&requirementsDoc.requirements.length>0,true,"current truthful state: no canonical evidence, real requirements present");
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"})} as any;
  const decision=productionEffectsWithBus(gitReadBus).resolveSemanticCompletion({...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:binding.requirements_path,evidence_path:binding.evidence_path}},candidate);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("MISSING_EVIDENCE"));
});

// ---------------------------------------------------------------------------
// REQUIREMENT SEMANTIC FIDELITY: the canonical R15 soak sentence decomposes
// atomically; each clause binds its exact roadmap bytes; a generic 30-day
// runtime observation alone can never close R15.
// ---------------------------------------------------------------------------
const realRegistryPath="docs/roadmap/semantic/semantic_registry.json";
const kindContractsPath="docs/roadmap/semantic/evidence_kind_contracts.json";

/** Reads real committed artifacts from the candidate commit (immutable Git reads). */
function realSemanticArtifacts(){
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const show=(path:string)=>execFileSync("git",["show",`${candidate}:${path}`],{encoding:"utf8"});
  const registry=JSON.parse(show(realRegistryPath));
  const binding=registry.roadmap_items.R15;
  return {candidate,show,registry,binding,requirementsDoc:JSON.parse(show(binding.requirements_path)),evidenceDoc:JSON.parse(show(binding.evidence_path))};
}

test("REQ_SEMANTICS canonical requirements decompose the soak sentence atomically",()=>{
  const {requirementsDoc}=realSemanticArtifacts();
  assert.equal(requirementsDoc.schema_version,1);
  const ids=requirementsDoc.requirements.map((r:{requirement_id:string})=>r.requirement_id);
  // Every clause of the canonical sentence must be independently machine-bound.
  const expected=[
    ["REQ-BRAIN-101-R15-SOAK-DURATION",  "1aa5e0d775d745e1d5176d17c8291325bc5abfcebe897ba32bb184fed10f0518"],
    ["REQ-BRAIN-101-R15-SOAK-REGIMES",   "148ff0a1a9777d599402e8c9d23cc78e817e1214b6da111c6aa98b9bd8072f62"],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-BYPASS", "da8f133f73df3cd32f077f6597ca10cfb5c948258378730015a0253450266549"],
    ["REQ-BRAIN-101-R15-SOAK-LEDGER-CONSISTENCY", "3fd188c22d7294444c90593d25d9e7e83c39f0bbb40c63f495e6dfbb57ad80ff"],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-DUPLICATE-ORDERS", "f124fd1958a6b0302042710cb2d4c59cb1c9b98a314ed165a4b1d8d56a6a5af9"],
    ["REQ-BRAIN-101-R15-SOAK-KILL-SWITCH", "345a38a2c0879e9d3fd10ec61e26abb1aa127a535d38a11b532577435801ad76"],
    ["REQ-BRAIN-101-R15-SOAK-RECOVERY",   "345a38a2c0879e9d3fd10ec61e26abb1aa127a535d38a11b532577435801ad76"],
  ] as const;
  assert.equal(requirementsDoc.requirements.length,7,"the seven canonical clauses are separate atomic requirements");
  for(const [id,textSha] of expected){
    assert.ok(ids.includes(id),`missing atomic requirement ${id}`);
    const requirement=requirementsDoc.requirements.find((r:{requirement_id:string})=>r.requirement_id===id)!;
    assert.equal(requirement.requirement_text_sha256,textSha,`${id} must bind its exact clause bytes`);
    assert.equal(requirement.original_spec_path,"docs/roadmap/BRAIN_101_ROADMAP.md");
    assert.equal(requirement.original_spec_sha256,"4c329c104cc5985484304ff1d607bb4e747eb9ea0a72a4a2a77187ef2d4b341e","must bind real roadmap bytes");
    assert.equal(requirement.parent_requirement_ids.includes("REQ-BRAIN-101-R15-SOAK-DURATION"),id!=="REQ-BRAIN-101-R15-SOAK-DURATION","every clause depends on the soak duration");
  }
  // Multi-regime must NOT be satisfiable by a single sample: "múltiples" >= 2.
  const regimes=requirementsDoc.requirements.find((r:{requirement_id:string})=>r.requirement_id==="REQ-BRAIN-101-R15-SOAK-REGIMES")!;
  assert.equal(regimes.minimum_sample_size>=2,true,"multiple regimes means at least 2 distinct validated regimes");
  assert.ok(regimes.required_evidence_kinds.includes("REGIME_COVERAGE"),"regime clause requires the governed REGIME_COVERAGE kind");
});

test("REQ_SEMANTICS evidence kind contracts are governed and closed",()=>{
  const {show}=realSemanticArtifacts();
  const contracts=JSON.parse(show(kindContractsPath));
  assert.equal(contracts.schema_version,1);
  assert.equal(contracts.minimum_regime_count_for_multiple,2,"'múltiples regímenes' is formally at least 2");
  for(const [kind,contract] of Object.entries(contracts.kinds) as [string,{assertion_contract:string;attestation_model:string;zero_condition:boolean;tested_runtime_execution:boolean}][]){
    assert.equal(typeof contract.assertion_contract,"string");
    assert.equal(typeof contract.attestation_model,"string");
    assert.equal(typeof contract.zero_condition,"boolean");
    assert.equal(typeof contract.tested_runtime_execution,"boolean");
    assert.ok(contract.assertion_contract.length>0);
    assert.ok(contract.attestation_model.includes("artifact"),`${kind} attestation must be artifact-bound`);
    if(kind==="KILL_SWITCH_TEST"||kind==="RECOVERY_TEST")assert.equal(contract.tested_runtime_execution,true,`${kind} requires tested runtime execution, not code presence`);
  }
  // The kinds used by the requirements must exist in the governed contract set.
  const {requirementsDoc}=realSemanticArtifacts();
  const governedKinds=new Set(Object.keys(contracts.kinds));
  for(const requirement of requirementsDoc.requirements)for(const kind of requirement.required_evidence_kinds)assert.ok(governedKinds.has(kind),`requirement kind ${kind} must be governed`);
});

test("REQ_SEMANTICS a generic 30-day runtime observation alone cannot close R15",()=>{
  const {candidate,show,binding}=realSemanticArtifacts();
  const requirementsDoc=JSON.parse(show(binding.requirements_path));
  // Adversarial synthetic evidence: a PERFECT generic 30-day runtime soak —
  // correct duration, correct source, correct artifact hash, independent
  // verifier, runtime bound — but NO proof of regimes/bypass/ledger/duplicates/
  // kill-switch/recovery. It satisfies ONLY the duration clause.
  const genericArtifact=JSON.stringify({observation:"generic 30d paper runtime",regimes:null,bypass_count:null,ledger_reconciliation:null,duplicate_orders:null,kill_switch_test:null,recovery_test:null});
  const genericArtifactSha=createHash("sha256").update(genericArtifact).digest("hex");
  const genericEvidence={schema_version:1,evidence:[{
    evidence_id:"EVIDENCE-GENERIC-30D",requirement_id:"REQ-BRAIN-101-R15-SOAK-DURATION",evidence_kind:"RUNTIME_OBSERVATION",
    evidence_level:"L8_SOAK" as const,source_sha:candidate,certified_implementation_sha:candidate,
    artifact_path:"docs/roadmap/semantic/generic-soak.json",artifact_sha256:genericArtifactSha,environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",
    observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"runtime-probe",assertion_type:"OBSERVATION" as const,
    observation:{duration_seconds:2592000,sample_size:30},verifier:{verifier_id:"independent-verifier",source_sha:candidate,independent:true},
  }]};
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===binding.evidence_path)return JSON.stringify(genericEvidence);
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  const decision=productionEffectsWithBus(gitReadBus).resolveSemanticCompletion({...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:binding.requirements_path,evidence_path:binding.evidence_path}},candidate);
  assert.equal(decision.decision,"BLOCK","generic 30d evidence closes only the duration clause; six clauses remain");
  assert.equal(decision.requirements_blocked,6);
  assert.equal(decision.requirements_satisfied,1,"only the duration requirement is satisfied");
  assert.deepEqual([...decision.reason_codes],["MISSING_EVIDENCE"]);
});

test("REQ_SEMANTICS SIMULATED_30D substitution against the L8 soak duration clause remains blocked",()=>{
  const {candidate,binding}=realSemanticArtifacts();
  const simulatedEvidence={schema_version:1,evidence:[{
    evidence_id:"EVIDENCE-SIM-30D",requirement_id:"REQ-BRAIN-101-R15-SOAK-DURATION",evidence_kind:"SIMULATED_30D",
    evidence_level:"L4_SIMULATED_INTEGRATION" as const,source_sha:candidate,certified_implementation_sha:candidate,
    artifact_path:"docs/roadmap/semantic/generic-soak.json",artifact_sha256:createHash("sha256").update("sim").digest("hex"),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",
    observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"runtime-probe",assertion_type:"OBSERVATION" as const,
    observation:{duration_seconds:2592000,sample_size:30},verifier:{verifier_id:"independent-verifier",source_sha:candidate,independent:true},
  }]};
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===binding.evidence_path)return JSON.stringify(simulatedEvidence);
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  const decision=productionEffectsWithBus(gitReadBus).resolveSemanticCompletion({...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:binding.requirements_path,evidence_path:binding.evidence_path}},candidate);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("SIMULATION_SUBSTITUTION"));
});

test("REQ_SEMANTICS positive synthetic contract: a complete qualifying evidence set satisfies all atomic requirements",()=>{
  const {candidate,binding}=realSemanticArtifacts();
  // Purely synthetic evaluator proof — NOT canonical R15 evidence.
  const now="2026-09-10T00:00:00.000Z";
  const kinds=[
    ["REQ-BRAIN-101-R15-SOAK-DURATION","RUNTIME_OBSERVATION","L8_SOAK",2592000,30],
    ["REQ-BRAIN-101-R15-SOAK-REGIMES","REGIME_COVERAGE","L8_SOAK",2592000,5],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-BYPASS","BYPASS_AUDIT","L8_SOAK",2592000,1],
    ["REQ-BRAIN-101-R15-SOAK-LEDGER-CONSISTENCY","LEDGER_RECONCILIATION","L8_SOAK",2592000,1],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-DUPLICATE-ORDERS","DUPLICATE_ORDER_AUDIT","L8_SOAK",2592000,1],
    ["REQ-BRAIN-101-R15-SOAK-KILL-SWITCH","KILL_SWITCH_TEST","L8_SOAK",2592000,1],
    ["REQ-BRAIN-101-R15-SOAK-RECOVERY","RECOVERY_TEST","L8_SOAK",2592000,1],
  ] as const;
  const evidence=kinds.map(([id,kind],index)=>{
    const artifactBytes=JSON.stringify({requirement:id,kind,index,qualifying:true});
    return {evidence_id:`EVIDENCE-SYN-${index}`,requirement_id:id,evidence_kind:kind,evidence_level:"L8_SOAK" as const,
      source_sha:candidate,certified_implementation_sha:candidate,artifact_path:`docs/roadmap/semantic/synthetic-${index}.json`,
      artifact_sha256:createHash("sha256").update(artifactBytes).digest("hex"),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",
      observed_at_utc:now,producer_id:"synthetic-probe",assertion_type:"OBSERVATION" as const,
      observation:{duration_seconds:2592000,sample_size:index===1?5:30},verifier:{verifier_id:"independent-verifier",source_sha:candidate,independent:true}};
  });
  const artifacts=new Map(evidence.map(record=>[record.artifact_path,JSON.stringify({requirement:record.requirement_id,qualifying:true,index:Number(record.evidence_id.split("-").pop())})]));
  const input={schema_version:1 as const,phase_or_item_id:"R15",source_sha:candidate,evaluated_at_utc:now,
    requirements:realSemanticArtifacts().requirementsDoc.requirements,
    expected_requirement_ids:realSemanticArtifacts().requirementsDoc.requirements.map((r:{requirement_id:string})=>r.requirement_id),
    expected_requirements:realSemanticArtifacts().requirementsDoc.requirements,
    evidence,deferments:[],deferment_authorizations:[]};
  const decision=evaluateSemanticCompletion(input,artifacts);
  assert.equal(decision.decision,"PASS","the schema is expressive enough: complete qualifying evidence satisfies every atomic clause");
  assert.equal(decision.requirements_satisfied,7);
  assert.deepEqual([...decision.reason_codes],[]);
  // Canonical evidence remains empty — this synthetic set lives only in tests.
  assert.equal(JSON.parse(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/evidence.json`],{encoding:"utf8"})).evidence.length,0);
});
