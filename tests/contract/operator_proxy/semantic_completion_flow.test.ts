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
const canonicalRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{[parentSpec.roadmap_item_id]:{requirements_path:requirementsPath,evidence_path:evidencePath,evidence_kind_contracts_path:"docs/roadmap/semantic/evidence_kind_contracts.json",soak_execution_manifest_path:"docs/roadmap/semantic/soak_execution_manifest.json",regime_classifier_contract_path:"docs/roadmap/semantic/regime_classifier_contract.json"}}});
/** Governed fixture manifest/classifier bytes for registry-backed fixtures. */
const fixtureManifest=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",soak_execution_id:"SOAK-EXEC-FIXTURE-001",source_sha:"a".repeat(40),environment:"PAPER_RUNTIME",started_at_utc:null,ended_at_utc:null,calendar_day_policy:"UTC_24H_DAY",runtime_binding:"paper-runtime:v1",regime_classifier_id:"BRAIN-101-R15-REGIME-CLASSIFIER",regime_classifier_version:"0.1.0-preregistered",regime_classifier_contract_path:"docs/roadmap/semantic/regime_classifier_contract.json",regime_classifier_contract_sha256:"b".repeat(64)});
const fixtureClassifier=JSON.stringify({schema_version:1,classifier_id:"BRAIN-101-R15-REGIME-CLASSIFIER",classifier_version:"0.1.0-preregistered",roadmap_id:"BRAIN-101",roadmap_item_id:"R15",definition_path:null,definition_sha256:null,output_identity_semantics:"stable string regime IDs within one classifier identity",minimum_distinct_regimes:2,frozen_source_sha:"a".repeat(40),state:"PREREGISTERED_NOT_YET_OBSERVED"});
/** Governed evidence-kind contract bytes used by registry-backed fixtures. */
const fixtureKindContracts=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",calendar_day_policy:"UTC_24H_DAY",minimum_regime_count_for_multiple:2,kinds:{
  RUNTIME_OBSERVATION:{assertion_contract:"runtime observation artifact",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:false},
  REGIME_COVERAGE:{assertion_contract:"distinct regime enumeration",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:true},
  BYPASS_AUDIT:{assertion_contract:"zero bypass attestation",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:false},
  LEDGER_RECONCILIATION:{assertion_contract:"zero ledger inconsistency attestation",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:false},
  DUPLICATE_ORDER_AUDIT:{assertion_contract:"zero duplicate order attestation",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:false},
  KILL_SWITCH_TEST:{assertion_contract:"executed kill-switch test",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:false},
  RECOVERY_TEST:{assertion_contract:"executed recovery test",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:false},
}});
/** fileAtBus with the canonical registry + kind contracts + manifest + classifier pre-seeded (the default production case). */
function registryFileAtBus(files:Record<string,string>){
  return fileAtBus({[semanticRegistryPath]:canonicalRegistry,[kindContractsPath]:fixtureKindContracts,[manifestPath]:fixtureManifest,[classifierPath]:fixtureClassifier,...files});
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
  const {bus}=registryFileAtBus({[requirementsPath]:canonicalRequirementsJson,[evidencePath]:JSON.stringify({schema_version:1,evidence:[{...canonicalEvidence,source_sha:merge,certified_implementation_sha:merge}]}),[artifactPath]:artifact});
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
  // Resolve the repository root from Git so the contract is cwd-independent
  // (CI runs the semantic suite from scripts/operator_proxy).
  const repoRoot=execFileSync("git",["rev-parse","--show-toplevel"],{encoding:"utf8"}).trim();
  // The registry must exist as a tracked worktree artifact.
  const registryPath=join(repoRoot,"docs/roadmap/semantic/semantic_registry.json");
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
  const tracked=execFileSync("git",["ls-files","--","docs/roadmap/semantic/semantic_registry.json"],{encoding:"utf8",cwd:repoRoot}).trim();
  assert.equal(tracked,"docs/roadmap/semantic/semantic_registry.json","registry must be tracked in Git");
  // Closed shape on real bytes: exactly the governed keys.
  assert.deepEqual(Object.keys(registry).sort(),["roadmap_id","roadmap_items","schema_version"]);
  assert.deepEqual(Object.keys(item).sort(),["evidence_kind_contracts_path","evidence_path","regime_classifier_contract_path","requirements_path","soak_execution_manifest_path"]);
});

// ---------------------------------------------------------------------------
// REAL-GIT FULL ARTIFACT CHAIN: registry → requirements → evidence →
// artifact bytes at exact candidate-commit SHAs. No fake-bus injection.
// ---------------------------------------------------------------------------
const registryPath="docs/roadmap/semantic/semantic_registry.json";

test("CHAIN registry pointing to missing requirements fails closed",()=>{
  const merge="f".repeat(40);
  const orphanRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{R15:{requirements_path:"docs/roadmap/semantic/absent-requirements.json",evidence_path:evidencePath,evidence_kind_contracts_path:"docs/roadmap/semantic/evidence_kind_contracts.json",soak_execution_manifest_path:"docs/roadmap/semantic/soak_execution_manifest.json",regime_classifier_contract_path:"docs/roadmap/semantic/regime_classifier_contract.json"}}});
  const {bus}=fileAtBus({[registryPath]:orphanRegistry,[evidencePath]:JSON.stringify({schema_version:1,evidence:[]})});
  const effects=productionEffectsWithBus(bus);
  const specWithoutDeclared={...parentSpec,semantic_completion:undefined};
  assert.throws(()=>effects.resolveSemanticCompletion({...specWithoutDeclared,semantic_completion:{requirements_path:"docs/roadmap/semantic/absent-requirements.json",evidence_path:evidencePath}},merge),/canonical semantic resolution failed/);
});

test("CHAIN registry pointing to missing evidence fails closed",()=>{
  const merge="f".repeat(40);
  const orphanRegistry=JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",roadmap_items:{R15:{requirements_path:requirementsPath,evidence_path:"docs/roadmap/semantic/absent-evidence.json",evidence_kind_contracts_path:"docs/roadmap/semantic/evidence_kind_contracts.json",soak_execution_manifest_path:"docs/roadmap/semantic/soak_execution_manifest.json",regime_classifier_contract_path:"docs/roadmap/semantic/regime_classifier_contract.json"}}});
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
  const {bus}=fileAtBus({[registryPath]:canonicalRegistry,[kindContractsPath]:fixtureKindContracts,[requirementsPath]:canonicalRequirementsJson,[evidencePath]:evidenceTampered,[artifactPath]:artifact});
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
  }
  // The soak-duration clause is the only one carrying the 30-day minimum;
  // its atomic children depend on it.
  const durationRequirement=requirementsDoc.requirements.find((r:{requirement_id:string})=>r.requirement_id==="REQ-BRAIN-101-R15-SOAK-DURATION");
  assert.ok(durationRequirement&&durationRequirement.minimum_duration_seconds===2592000,"the duration clause binds 30 calendar days");
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
  assert.ok(decision.reason_codes.includes("MISSING_EVIDENCE"),"truthful canonical decision: the real R15 soak requirement has no qualifying canonical evidence yet");
  assert.equal(decision.requirements_total,7,"atomic decomposition: seven clause requirements");
  assert.equal(decision.requirements_blocked,7);
  assert.equal(decision.requirements_satisfied,0);
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
    if(path==="docs/roadmap/semantic/generic-soak.json")return genericArtifact;
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  const decision=productionEffectsWithBus(gitReadBus).resolveSemanticCompletion({...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:binding.requirements_path,evidence_path:binding.evidence_path}},candidate);
  assert.equal(decision.decision,"BLOCK","generic 30d evidence cannot close R15: without a governed soak cohort binding it cannot even satisfy the duration clause");
  assert.equal(decision.requirements_blocked,7);
  assert.equal(decision.requirements_satisfied,0);
  // The un-cohorted generic artifact fails the duration clause (missing the
  // governed cohort identity); every other clause then fails through its
  // unsatisfied parent.
  assert.ok(decision.reason_codes.includes("MISSING_EVIDENCE_COHORT_ID"),"the generic artifact is not bound to the governed soak execution identity");
  assert.ok(decision.reason_codes.includes("PARENT_REQUIREMENT_UNSATISFIED"));
});

test("REQ_SEMANTICS SIMULATED_30D substitution against the L8 soak duration clause remains blocked",()=>{
  const {candidate,binding}=realSemanticArtifacts();
  const simulatedEvidence={schema_version:1,evidence:[{
    evidence_id:"EVIDENCE-SIM-30D",requirement_id:"REQ-BRAIN-101-R15-SOAK-DURATION",evidence_kind:"RUNTIME_OBSERVATION",
    evidence_level:"L4_SIMULATED_INTEGRATION" as const,source_sha:candidate,certified_implementation_sha:candidate,
    artifact_path:"docs/roadmap/semantic/generic-soak.json",artifact_sha256:createHash("sha256").update("sim").digest("hex"),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",
    observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"runtime-probe",assertion_type:"OBSERVATION" as const,
    observation:{duration_seconds:2592000,sample_size:30},verifier:{verifier_id:"independent-verifier",source_sha:candidate,independent:true},
  }]};
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===binding.evidence_path)return JSON.stringify(simulatedEvidence);
    if(path==="docs/roadmap/semantic/generic-soak.json")return "sim";
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  const decision=productionEffectsWithBus(gitReadBus).resolveSemanticCompletion({...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:binding.requirements_path,evidence_path:binding.evidence_path}},candidate);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("SIMULATION_SUBSTITUTION"));
});

test("REQ_SEMANTICS positive synthetic contract: a complete qualifying evidence set satisfies all atomic requirements",()=>{
  const {candidate}=realSemanticArtifacts();
  // Purely synthetic evaluator proof — NOT canonical R15 evidence.
  // Complete qualifying set: same governed soak cohort, full-window audits.
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const requirementsDoc=realSemanticArtifacts().requirementsDoc;
  const input={schema_version:1 as const,phase_or_item_id:"R15",source_sha:candidate,evaluated_at_utc:"2026-09-10T00:00:00.000Z",
    requirements:requirementsDoc.requirements,
    expected_requirement_ids:requirementsDoc.requirements.map((r:{requirement_id:string})=>r.requirement_id),
    expected_requirements:requirementsDoc.requirements,
    evidence,deferments:[],deferment_authorizations:[]};
  const decision=evaluateSemanticCompletion(input,artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"PASS","the schema is expressive enough: a complete same-cohort qualifying set satisfies every atomic clause");
  assert.equal(decision.requirements_satisfied,7);
  assert.deepEqual([...decision.reason_codes],[]);
  // Canonical evidence remains empty — this synthetic set lives only in tests.
  assert.equal(JSON.parse(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/evidence.json`],{encoding:"utf8"})).evidence.length,0);
});

// ---------------------------------------------------------------------------
// SOAK COHORT SEMANTICS (external-review P1-1/P1-2/P1-3 + P2-1/P2-2).
// All R15 soak evidence must bind to ONE governed soak execution cohort.
// ---------------------------------------------------------------------------

/** Builds a complete 7-clause synthetic evidence set with per-clause overrides. */
function cohortEvidenceSet(candidate:string,overrides:{cohort?:(index:number)=>string|undefined;duration?:(index:number)=>number;assertion?:(index:number)=>"OBSERVATION"|"BOOLEAN";kind?:(index:number)=>string;authorities?:{manifest:Record<string,unknown>;classifier:Record<string,unknown>}}={}){
  const now="2026-09-10T00:00:00.000Z";
  const kinds=[
    ["REQ-BRAIN-101-R15-SOAK-DURATION","RUNTIME_OBSERVATION"],
    ["REQ-BRAIN-101-R15-SOAK-REGIMES","REGIME_COVERAGE"],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-BYPASS","BYPASS_AUDIT"],
    ["REQ-BRAIN-101-R15-SOAK-LEDGER-CONSISTENCY","LEDGER_RECONCILIATION"],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-DUPLICATE-ORDERS","DUPLICATE_ORDER_AUDIT"],
    ["REQ-BRAIN-101-R15-SOAK-KILL-SWITCH","KILL_SWITCH_TEST"],
    ["REQ-BRAIN-101-R15-SOAK-RECOVERY","RECOVERY_TEST"],
  ] as const;
  // The default cohort is the AUTHORITATIVE governed manifest identity; the
  // regime record binds the governed classifier identity exactly.
  const governed=overrides.authorities??governedSemanticAuthorities();
  const manifest=governed.manifest as typeof governed.manifest&{soak_execution_id:string;runtime_binding:string};
  const classifier=governed.classifier as typeof governed.classifier&{classifier_id:string;classifier_version:string;regime_classifier_contract_sha256:string};
  const classifierContractSha=classifier.regime_classifier_contract_sha256;
  const defaultCohort=manifest.soak_execution_id;
  const cohortFor=(index:number)=>{const overridden=overrides.cohort?overrides.cohort(index):undefined;return overridden!==undefined?overridden:defaultCohort;};
  const evidence=kinds.map(([id,kind],index)=>{
    const isRegime=index===1;
    const regimeIds=isRegime?["REGIME-A","REGIME-B","REGIME-C","REGIME-D","REGIME-E"]:undefined;
    const artifactBytes=JSON.stringify({requirement:id,kind,index,qualifying:true,soak_execution_id:cohortFor(index),...(isRegime?{observed_regime_ids:regimeIds,classifier_id:classifier.classifier_id,classifier_version:classifier.classifier_version,classifier_contract_sha256:classifierContractSha}:{})});
    return {evidence_id:`EVIDENCE-SYN-${index}`,requirement_id:id,evidence_kind:overrides.kind?overrides.kind(index):kind,evidence_level:"L8_SOAK" as const,
      source_sha:candidate,certified_implementation_sha:candidate,artifact_path:`docs/roadmap/semantic/synthetic-${index}.json`,
      artifact_sha256:createHash("sha256").update(artifactBytes).digest("hex"),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",
      observed_at_utc:now,producer_id:"synthetic-probe",assertion_type:overrides.assertion?overrides.assertion(index):"OBSERVATION" as const,
      soak_execution_id:cohortFor(index),
      ...(isRegime?{observed_regime_ids:regimeIds,classifier_id:classifier.classifier_id,classifier_version:classifier.classifier_version,classifier_contract_sha256:classifierContractSha}:{}),
      observation:{duration_seconds:overrides.duration?overrides.duration(index):2592000,sample_size:isRegime?5:30},verifier:{verifier_id:"independent-verifier",source_sha:candidate,independent:true}};
  });
  const artifacts=new Map(evidence.map((record,index)=>{
    const isRegime=index===1;
    return [record.artifact_path,JSON.stringify({requirement:record.requirement_id,kind:kinds[index][1],index,qualifying:true,soak_execution_id:record.soak_execution_id,...(isRegime?{observed_regime_ids:["REGIME-A","REGIME-B","REGIME-C","REGIME-D","REGIME-E"],classifier_id:record.classifier_id,classifier_version:record.classifier_version,classifier_contract_sha256:record.classifier_contract_sha256}:{})})];
  }));
  return {evidence,artifacts};
}
function cohortInput(candidate:string,evidence:ReturnType<typeof cohortEvidenceSet>["evidence"]){
  const requirementsDoc=realSemanticArtifacts().requirementsDoc;
  return {schema_version:1 as const,phase_or_item_id:"R15",source_sha:candidate,evaluated_at_utc:"2026-09-10T00:00:00.000Z",
    requirements:requirementsDoc.requirements,
    expected_requirement_ids:requirementsDoc.requirements.map((r:{requirement_id:string})=>r.requirement_id),
    expected_requirements:requirementsDoc.requirements,
    evidence,deferments:[],deferment_authorizations:[]};
}

test("R1 DIFFERENT_SOAK_COHORTS_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const cohorts=["SOAK-A","SOAK-B","SOAK-C","SOAK-D","SOAK-E","SOAK-F","SOAK-G"];
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},cohort:index=>cohorts[index]});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","seven individually perfect records from seven different soaks are NOT one governed soak");
  assert.ok(decision.reason_codes.includes("EVIDENCE_COHORT_AUTHORITY_MISMATCH"),"none of the seven labels matches the governed manifest identity");
});

test("R2 SAME_COHORT_COMPLETE_SYNTHETIC_PASS",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"PASS");
  assert.equal(decision.requirements_satisfied,7);
  assert.deepEqual([...decision.reason_codes],[]);
});

test("R3 BYPASS_SHORT_WINDOW_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},duration:index=>index===2?300:2592000});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","a 5-minute bypass audit cannot attest zero violations across a 30-day soak window");
  assert.ok(decision.reason_codes.includes("INSUFFICIENT_EVIDENCE_LEVEL"));
});

test("R4 LEDGER_SHORT_WINDOW_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},duration:index=>index===3?300:2592000});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("INSUFFICIENT_EVIDENCE_LEVEL"));
});

test("R5 DUPLICATE_ORDER_SHORT_WINDOW_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},duration:index=>index===4?300:2592000});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("INSUFFICIENT_EVIDENCE_LEVEL"));
});

test("R6 KILL_SWITCH_DIFFERENT_COHORT_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},cohort:index=>index===5?"SOAK-OTHER":undefined!});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","a kill-switch test executed in a different soak cohort does not prove this soak");
  assert.ok(decision.reason_codes.includes("EVIDENCE_COHORT_AUTHORITY_MISMATCH"));
});

test("R7 RECOVERY_DIFFERENT_COHORT_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},cohort:index=>index===6?"SOAK-OTHER":undefined!});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("EVIDENCE_COHORT_AUTHORITY_MISMATCH"));
});

test("R8 STATIC_KILL_SWITCH_PRESENCE_NOT_TEST",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},assertion:index=>index===5?"BOOLEAN":"OBSERVATION"});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","a naked boolean claim of kill-switch presence is not an executed test");
  assert.ok(decision.reason_codes.includes("NAKED_BOOLEAN_ASSERTION"));
});

test("R9 STATIC_RECOVERY_PRESENCE_NOT_TEST",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},assertion:index=>index===6?"BOOLEAN":"OBSERVATION"});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("NAKED_BOOLEAN_ASSERTION"));
});

test("R10 KIND_CONTRACT_SUBSTITUTION_CHANGES_DECISION_IDENTITY",()=>{
  const {candidate,show}=realSemanticArtifacts();
  const realContractBytes=show(kindContractsPath);
  const mutated=JSON.parse(realContractBytes);
  mutated.kinds.RUNTIME_OBSERVATION.assertion_contract="weakened: any string counts as a runtime observation";
  const decisionWithReal=runRealResolverDecision(candidate);
  const decisionWithMutated=runRealResolverDecision(candidate,JSON.stringify(mutated));
  // Different governed kind-contract bytes MUST change the decision identity
  // (or fail closed at the canonical path). Same bytes → same identity.
  assert.ok(decisionWithReal.evidence_kind_contracts_sha256!==decisionWithMutated.evidence_kind_contracts_sha256||decisionWithReal.decision_artifact_sha256!==decisionWithMutated.decision_artifact_sha256,"decision identity must depend on the governed kind-contract bytes");
});

test("R11 KIND_CONTRACT_PATH_SUBSTITUTION_BLOCKED",()=>{
  const {candidate}=realSemanticArtifacts();
  const hostile={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json",evidence_kind_contracts_path:"attacker/kind-contracts.json"}};
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"})} as any;
  assert.throws(()=>productionEffectsWithBus(gitReadBus).resolveSemanticCompletion(hostile,candidate),/SEMANTIC_CANONICAL_BINDING_MISMATCH|canonical semantic registry/);
});

test("R12 UNKNOWN_KIND_CONTRACT_BLOCKED",()=>{
  const {candidate,show}=realSemanticArtifacts();
  const mutated=JSON.parse(show(kindContractsPath));
  delete mutated.kinds.BYPASS_AUDIT; // canonical requirement kind now ungoverned
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===kindContractsPath)return JSON.stringify(mutated);
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  const effects=productionEffectsWithBus(gitReadBus);
  const realSpec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};
  assert.throws(()=>effects.resolveSemanticCompletion(realSpec,candidate),/canonical semantic evidence kind contract/);
});

test("R13 29_CALENDAR_DAYS_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},duration:()=>2505600});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","29 UTC calendar days is not 30");
  assert.ok(decision.reason_codes.includes("INSUFFICIENT_EVIDENCE_LEVEL"));
});

test("R14 30_CALENDAR_DAYS_ELIGIBLE",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=cohortEvidenceSet(candidate,{authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier},});
  const decision=evaluateSemanticCompletion(cohortInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"PASS","30 consecutive UTC calendar days (2592000s) satisfies the duration clause");
});

/** Runs the production resolver with real Git bytes; optionally overrides the kind-contract file bytes. */
function runRealResolverDecision(candidate:string,contractBytesOverride?:string){
  const {binding}=realSemanticArtifacts();
  const gitReadBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===kindContractsPath&&contractBytesOverride!==undefined)return contractBytesOverride;
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  const realSpec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:binding.requirements_path,evidence_path:binding.evidence_path}};
  return productionEffectsWithBus(gitReadBus).resolveSemanticCompletion(realSpec,candidate);
}

// ---------------------------------------------------------------------------
// SOAK EXECUTION AUTHORITY + REGIME CLASSIFIER AUTHORITY (Owner decisions
// 1+2). The manifest/classifier are governed Git-bound artifacts; evidence
// strings alone can never authorize cohort membership or regime identity.
// ---------------------------------------------------------------------------
const manifestPath="docs/roadmap/semantic/soak_execution_manifest.json";
const classifierPath="docs/roadmap/semantic/regime_classifier_contract.json";

/** Loads the real governed soak manifest and classifier contract from Git at HEAD. */
function governedSemanticAuthorities(){
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const show=(path:string)=>execFileSync("git",["show",`${candidate}:${path}`],{encoding:"utf8"});
  const manifestBytes=show(manifestPath);
  const classifierBytes=show(classifierPath);
  const manifest={...JSON.parse(manifestBytes),soak_execution_manifest_sha256:createHash("sha256").update(manifestBytes,"utf8").digest("hex")};
  const classifier={...JSON.parse(classifierBytes),regime_classifier_contract_sha256:createHash("sha256").update(classifierBytes,"utf8").digest("hex")};
  return {candidate,show,manifest,classifier,manifestBytes,classifierBytes};
}

/** Full-authority synthetic evidence set: takes the authoritative soak id / classifier from Git. */
function authoritativeEvidenceSet(candidate:string,overrides:{soakId?:(index:number)=>string|undefined;classifierId?:string;classifierVersion?:string;classifierSha?:string;regimeIds?:(index:number)=>string[]|undefined;sampleSize?:(index:number)=>number;duration?:(index:number)=>number;assertion?:(index:number)=>"OBSERVATION"|"BOOLEAN";authorities?:{manifest:Record<string,unknown>;classifier:Record<string,unknown>}}={}){
  const {manifest,classifier}=governedSemanticAuthorities();
  const authManifest=(overrides.authorities?.manifest ?? manifest) as typeof manifest;
  const authClassifier=(overrides.authorities?.classifier ?? classifier) as typeof classifier;
  const now="2026-09-10T00:00:00.000Z";
  const kinds=[
    ["REQ-BRAIN-101-R15-SOAK-DURATION","RUNTIME_OBSERVATION"],
    ["REQ-BRAIN-101-R15-SOAK-REGIMES","REGIME_COVERAGE"],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-BYPASS","BYPASS_AUDIT"],
    ["REQ-BRAIN-101-R15-SOAK-LEDGER-CONSISTENCY","LEDGER_RECONCILIATION"],
    ["REQ-BRAIN-101-R15-SOAK-ZERO-DUPLICATE-ORDERS","DUPLICATE_ORDER_AUDIT"],
    ["REQ-BRAIN-101-R15-SOAK-KILL-SWITCH","KILL_SWITCH_TEST"],
    ["REQ-BRAIN-101-R15-SOAK-RECOVERY","RECOVERY_TEST"],
  ] as const;
  const evidence=kinds.map(([id,kind],index)=>{
    const regimeIds=overrides.regimeIds?overrides.regimeIds(index):undefined;
    const artifactBytes=JSON.stringify({requirement:id,kind,index,qualifying:true,soak_execution_id:overrides.soakId?overrides.soakId(index):authManifest.soak_execution_id,...(regimeIds?{observed_regime_ids:regimeIds,classifier_id:overrides.classifierId??authClassifier.classifier_id,classifier_version:overrides.classifierVersion??authClassifier.classifier_version,classifier_contract_sha256:overrides.classifierSha??authClassifier.regime_classifier_contract_sha256}:{})});
    const sampleOverride=overrides.sampleSize?overrides.sampleSize(index):undefined;
    return {evidence_id:`EVIDENCE-SYN-${index}`,requirement_id:id,evidence_kind:kind,evidence_level:"L8_SOAK" as const,
      source_sha:candidate,certified_implementation_sha:candidate,artifact_path:`docs/roadmap/semantic/synthetic-${index}.json`,
      artifact_sha256:createHash("sha256").update(artifactBytes).digest("hex"),environment:"PAPER_RUNTIME",runtime_binding:authManifest.runtime_binding,
      observed_at_utc:now,producer_id:"synthetic-probe",assertion_type:overrides.assertion?overrides.assertion(index):"OBSERVATION" as const,
      soak_execution_id:overrides.soakId?overrides.soakId(index):authManifest.soak_execution_id,
      ...(regimeIds?{observed_regime_ids:regimeIds,classifier_id:overrides.classifierId??authClassifier.classifier_id,classifier_version:overrides.classifierVersion??authClassifier.classifier_version,classifier_contract_sha256:overrides.classifierSha??authClassifier.regime_classifier_contract_sha256}:{}),
      observation:{duration_seconds:overrides.duration?overrides.duration(index):2592000,sample_size:sampleOverride??(regimeIds?regimeIds.length:30)},verifier:{verifier_id:"independent-verifier",source_sha:candidate,independent:true}};
  });
  const artifacts=new Map(evidence.map((record,index)=>{
    const regimeIds=overrides.regimeIds?overrides.regimeIds(index):undefined;
    const bytes=JSON.stringify({requirement:record.requirement_id,kind:kinds[index][1],index,qualifying:true,soak_execution_id:record.soak_execution_id,...(regimeIds?{observed_regime_ids:regimeIds,classifier_id:record.classifier_id,classifier_version:record.classifier_version,classifier_contract_sha256:record.classifier_contract_sha256}:{})});
    return [record.artifact_path,bytes];
  }));
  return {evidence,artifacts,manifest,classifier};
}
function authoritativeInput(candidate:string,evidence:ReturnType<typeof authoritativeEvidenceSet>["evidence"]){
  const requirementsDoc=realSemanticArtifacts().requirementsDoc;
  return {schema_version:1 as const,phase_or_item_id:"R15",source_sha:candidate,evaluated_at_utc:"2026-09-10T00:00:00.000Z",
    requirements:requirementsDoc.requirements,
    expected_requirement_ids:requirementsDoc.requirements.map((r:{requirement_id:string})=>r.requirement_id),
    expected_requirements:requirementsDoc.requirements,
    evidence,deferments:[],deferment_authorizations:[]};
}


/** Synthetic governed kind-contract document for pure-evaluator regime tests (P2-1 decoupling). */
function syntheticKindContracts(){
  const kinds:Record<string,{assertion_contract:string;attestation_model:string;zero_condition:boolean;tested_runtime_execution:boolean;requires_regime_identity:boolean}>={
    RUNTIME_OBSERVATION:{assertion_contract:"runtime observation",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:false},
    REGIME_COVERAGE:{assertion_contract:"regime enumeration",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:true},
    BYPASS_AUDIT:{assertion_contract:"zero bypass",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:false},
    LEDGER_RECONCILIATION:{assertion_contract:"zero ledger inconsistency",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:false},
    DUPLICATE_ORDER_AUDIT:{assertion_contract:"zero duplicate orders",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:false},
    KILL_SWITCH_TEST:{assertion_contract:"executed kill-switch test",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:false},
    RECOVERY_TEST:{assertion_contract:"executed recovery test",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:false},
  };
  return {schema_version:1 as const,roadmap_id:"BRAIN-101",calendar_day_policy:"UTC_24H_DAY" as const,minimum_regime_count_for_multiple:2,kinds};
}

test("R15 SAME_STRING_DIFFERENT_EXECUTIONS_BLOCKED: evidence strings cannot self-authorize",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  // Every record claims the SAME label "SOAK-X" — but the governed manifest
  // declares a different authoritative execution identity. String agreement
  // among evidence is insufficient: the authority is the Git-bound manifest.
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{soakId:()=>"SOAK-X",authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  assert.notEqual(authorities.governedManifest.soak_execution_id,"SOAK-X");
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("EVIDENCE_COHORT_AUTHORITY_MISMATCH"));
});

test("R16 EVIDENCE_SOAK_ID_DIFFERS_FROM_MANIFEST yields authority mismatch",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{soakId:index=>index===0?"SOAK-REAL-A":undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("EVIDENCE_COHORT_AUTHORITY_MISMATCH"));
});

test("R17 MISSING_EVIDENCE_IS_NOT_COHORT_MISMATCH: empty canonical evidence yields MISSING_EVIDENCE",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{});
  const input=authoritativeInput(candidate,evidence);
  input.evidence=[]; // canonical truthful state: zero evidence records
  const decision=evaluateSemanticCompletion(input,artifacts);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("MISSING_EVIDENCE"),"the primary truthful reason for an unevidenced requirement is MISSING_EVIDENCE");
  assert.ok(!decision.reason_codes.includes("EVIDENCE_COHORT_MISMATCH"),"cohort mismatch must not be emitted for absent evidence");
  assert.ok(!decision.reason_codes.includes("EVIDENCE_COHORT_AUTHORITY_MISMATCH"),"authority mismatch must not be emitted for absent evidence");
});

test("R18 MISSING_SOAK_EXECUTION_ID_WITH_EVIDENCE yields the precise missing-cohort reason",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{});
  const stripped=evidence.map((record,index)=>{const {soak_execution_id,...rest}=record as Record<string,unknown>;return rest as typeof record;});
  // Repair artifacts keys for the stripped set.
  const strippedArtifacts=new Map(artifacts);
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,stripped as typeof evidence),strippedArtifacts);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("MISSING_EVIDENCE_COHORT_ID"),"evidence present but lacking the governed cohort identity is its own precise failure");
  assert.ok(!decision.reason_codes.includes("EVIDENCE_COHORT_MISMATCH"),"missing identity is not disagreement among records");
});

test("R19 CLASSIFIER_ID_SUBSTITUTION_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{classifierId:"CLASSIFIER-B",authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,syntheticKindContracts(),authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("REGIME_CLASSIFIER_AUTHORITY_MISMATCH"));
});

test("R20 CLASSIFIER_VERSION_SUBSTITUTION_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{classifierVersion:"99.0.0-forged",authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,syntheticKindContracts(),authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("REGIME_CLASSIFIER_AUTHORITY_MISMATCH"));
});

test("R21 CLASSIFIER_HASH_SUBSTITUTION_BLOCKED",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{classifierSha:"f".repeat(64),authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,syntheticKindContracts(),authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("REGIME_CLASSIFIER_AUTHORITY_MISMATCH"));
});

test("R22 SAMPLE_SIZE_REGIME_ID_MISMATCH_BLOCKED: sample_size=2 with one regime ID",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A"]:undefined,sampleSize:index=>index===1?2:30,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,syntheticKindContracts(),authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","claiming 2 regimes while observing 1 distinct ID is spoofing");
  assert.ok(decision.reason_codes.includes("REGIME_ID_COUNT_MISMATCH"));
});

test("R23 DUPLICATE_REGIME_IDS_DO_NOT_COUNT: ['R1','R1'] is one regime",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["R1","R1"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,syntheticKindContracts(),authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK");
  assert.ok(decision.reason_codes.includes("REGIME_ID_COUNT_MISMATCH"));
});

test("R24 TWO_DISTINCT_GOVERNED_REGIME_IDS_ELIGIBLE",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"PASS","two distinct regime IDs under the governed classifier satisfy 'múltiples regímenes'");
  assert.equal(decision.requirements_satisfied,7);
});

test("R25 SOAK_MANIFEST_SUBSTITUTION_CHANGES_DECISION_IDENTITY",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const input=authoritativeInput(candidate,evidence);
  const real=evaluateSemanticCompletion(input,artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  // Byte-different manifest with IDENTICAL semantics: only the decision hash changes.
  const semanticallyIdenticalManifest={...authorities.governedManifest,note:"byte-different"};
  const mutatedManifestSha=createHash("sha256").update(JSON.stringify(semanticallyIdenticalManifest),"utf8").digest("hex");
  const forged=evaluateSemanticCompletion(input,artifacts,undefined,{...semanticallyIdenticalManifest,soak_execution_manifest_sha256:mutatedManifestSha},authorities.governedClassifier);
  assert.equal(real.decision,"PASS");
  assert.equal(forged.decision,"PASS","same semantics => same decision");
  assert.notEqual(real.decision_artifact_sha256,forged.decision_artifact_sha256,"decision identity must depend on the governed manifest bytes");
});

test("R26 CLASSIFIER_CONTRACT_SUBSTITUTION_CHANGES_DECISION_IDENTITY",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const byteDifferentClassifier={...authorities.governedClassifier,note:"byte-different"};
  const mutatedClassifierSha=createHash("sha256").update(JSON.stringify(byteDifferentClassifier),"utf8").digest("hex");
  const mutatedPairClassifier={...byteDifferentClassifier,regime_classifier_contract_sha256:mutatedClassifierSha};
  const mutatedPairManifestBase={...authorities.governedManifest,regime_classifier_contract_sha256:mutatedClassifierSha};
  const mutatedPairManifest={...mutatedPairManifestBase,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(mutatedPairManifestBase),"utf8").digest("hex")};
  // Each pair is evaluated with ITS OWN coherent evidence: the only semantic
  // difference between the two runs is the BOUND CLASSIFIER BYTES.
  const original=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const substituted=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:mutatedPairManifest,classifier:mutatedPairClassifier}});
  const real=evaluateSemanticCompletion(authoritativeInput(candidate,original.evidence),original.artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  const forged=evaluateSemanticCompletion(authoritativeInput(candidate,substituted.evidence),substituted.artifacts,undefined,mutatedPairManifest,mutatedPairClassifier);
  assert.equal(real.decision,"PASS");
  assert.equal(forged.decision,"PASS","same semantics => same decision");
  assert.notEqual(real.decision_artifact_sha256,forged.decision_artifact_sha256,"decision identity must depend on the governed classifier bytes");
});

test("SAME_GOVERNED_SOAK_COMPLETE_SYNTHETIC_PASS: one manifest + one classifier + 7 authoritative records",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B","REGIME-C"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"PASS");
  assert.equal(decision.requirements_satisfied,7);
  assert.deepEqual([...decision.reason_codes],[]);
  // Canonical evidence remains empty — synthetic only.
  assert.equal(JSON.parse(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/evidence.json`],{encoding:"utf8"})).evidence.length,0);
});

/** Loads the governed manifest/classifier through the production resolver's Git-backed fixture (for pure-evaluator authority tests). */
function governedSemanticArtifactsFixture(){
  const {candidate}=governedSemanticAuthorities();
  const {evidence,artifacts,manifest,classifier}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined});
  return {candidate,evidence,artifacts,manifest,classifier};
}

// ---------------------------------------------------------------------------
// EXECUTION-STATE AUTHORITY (external review P1-1/P1-2/P1-3 + P2-1/P2-2):
// a not-started soak manifest and a non-materialized classifier must never
// authorize qualifying evidence; the manifest must actually bind the
// classifier contract bytes; hash-binding must be byte-identity; regime
// semantics come from the governed contract, not gate constants.
// ---------------------------------------------------------------------------

/** Builds a governed-state synthetic authority pair derived from the REAL committed artifacts. */
function syntheticGovernedAuthorities(state:"NOT_STARTED"|"EXECUTING"|"COMPLETED"){
  const {manifest,classifier,candidate}=governedSemanticAuthorities();
  // A fully materialized synthetic classifier definition (test-only bytes).
  const definitionBytes=JSON.stringify({classifier:classifier.classifier_id,version:classifier.classifier_version,definition:"synthetic governed classifier definition for tests",regime_id_space:"TEST-REGIME"});
  const definitionSha=createHash("sha256").update(definitionBytes,"utf8").digest("hex");
  const materialized=state!=="NOT_STARTED";
  // The synthetic classifier in OBSERVED state with a materialized definition.
  const governedClassifier={...classifier,
    definition_path:materialized?"docs/roadmap/semantic/synthetic-classifier-definition.json":null,
    definition_sha256:materialized?definitionSha:null,
    state:(materialized?"OBSERVED":"PREREGISTERED_NOT_YET_OBSERVED") as "OBSERVED"|"PREREGISTERED_NOT_YET_OBSERVED"};
  // The classifier contract's own byte SHA changes with its bytes.
  const governedClassifierBytes=JSON.stringify(governedClassifier);
  const governedClassifierSha=createHash("sha256").update(governedClassifierBytes,"utf8").digest("hex");
  // The manifest binds the EXACT synthetic classifier contract bytes, aligns
  // its execution source with the evaluated candidate (source authority), and
  // declares the truthful window for its state: NOT_STARTED = null/null,
  // EXECUTING = started/not-ended, COMPLETED = started + ended 30 days later
  // (2026-09-10 → 2026-10-10: a full 30-day governed soak window).
  const window=state==="NOT_STARTED"?{started_at_utc:null,ended_at_utc:null}:state==="EXECUTING"?{started_at_utc:"2026-09-10T00:00:00.000Z",ended_at_utc:null}:{started_at_utc:"2026-09-10T00:00:00.000Z",ended_at_utc:"2026-10-10T00:00:00.000Z"};
  const {soak_execution_manifest_sha256:_dropped,...manifestWithoutSha}=manifest;
  const governedManifestBase={...manifestWithoutSha,
    source_sha:candidate,
    regime_classifier_id:governedClassifier.classifier_id,
    regime_classifier_version:governedClassifier.classifier_version,
    regime_classifier_contract_sha256:governedClassifierSha,
    ...window};
  const governedManifestBytes=JSON.stringify(governedManifestBase);
  const governedManifestSha=createHash("sha256").update(governedManifestBytes,"utf8").digest("hex");
  // loaderManifestBytes: closed 14-key shape for the resolver's loader (no sha field).
  // governedManifest: the evaluator-facing object WITH its byte sha attached.
  return {governedManifest:{...governedManifestBase,soak_execution_manifest_sha256:governedManifestSha},loaderManifestBytes:governedManifestBytes,governedClassifier:{...governedClassifier,regime_classifier_contract_sha256:governedClassifierSha},loaderClassifierBytes:governedClassifierBytes,classifierSha:governedClassifierSha,manifestBytes:governedManifestBytes,classifierBytes:governedClassifierBytes,definitionBytes,definitionSha};
}

test("P1-1 NOT_STARTED_SOAK_MANIFEST cannot authorize evidence",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const {governedManifest,governedClassifier}=syntheticGovernedAuthorities("NOT_STARTED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,governedManifest,governedClassifier);
  assert.equal(decision.decision,"BLOCK","a preregistered not-started soak cannot have qualifying evidence");
  assert.ok(decision.reason_codes.includes("SOAK_EXECUTION_NOT_STARTED"));
});

test("P1-2 PLACEHOLDER_CLASSIFIER cannot authorize regime evidence",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  // Completed soak, but the classifier remains a non-materialized placeholder.
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const classifierBase=authorities.governedClassifier;
  const {regime_classifier_contract_sha256:_clsShaDrop,...classifierWithoutSha}=classifierBase;
  const nonMaterializedBase={...classifierWithoutSha,definition_path:null,definition_sha256:null,state:"PREREGISTERED_NOT_YET_OBSERVED" as const} as typeof classifierBase;
  const nonMaterializedSha=createHash("sha256").update(JSON.stringify(nonMaterializedBase),"utf8").digest("hex");
  const coherentManifestBase={...authorities.governedManifest,regime_classifier_contract_sha256:nonMaterializedSha};
  const coherentManifest={...coherentManifestBase,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(coherentManifestBase),"utf8").digest("hex")};
  const coherentClassifier={...nonMaterializedBase,regime_classifier_contract_sha256:nonMaterializedSha};
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:coherentManifest,classifier:coherentClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,syntheticKindContracts(),coherentManifest,coherentClassifier);
  assert.equal(decision.decision,"BLOCK","a non-materialized classifier cannot produce regime observations");
  assert.ok(decision.reason_codes.includes("REGIME_CLASSIFIER_NOT_MATERIALIZED"));
});

test("P1-3 MANIFEST must actually bind the classifier contract bytes",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const {manifest,classifier}=governedSemanticAuthorities();
  // A manifest whose classifier SHA does not equal the actual contract bytes SHA fails closed.
  const mismatchedManifest={...manifest,started_at_utc:"2026-09-10T00:00:00.000Z",regime_classifier_contract_sha256:"9".repeat(64)};
  assert.throws(()=>evaluateSemanticCompletion(authoritativeInput(candidate,[]),new Map(),undefined,mismatchedManifest,{...classifier,state:"OBSERVED" as const}),/regime classifier contract not bound|soak execution manifest invalid/i);
});

test("P1-3 unbound classifier SHA in the manifest fails closed structurally",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  // The REAL committed manifest now binds the ACTUAL classifier bytes SHA (raw Git bytes, closed shape).
  const rawManifest=JSON.parse(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/soak_execution_manifest.json`],{encoding:"utf8"}));
  const rawClassifier=JSON.parse(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/regime_classifier_contract.json`],{encoding:"utf8"}));
  const rawClassifierSha=createHash("sha256").update(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/regime_classifier_contract.json`],{encoding:"utf8"}),"utf8").digest("hex");
  assert.equal(rawManifest.regime_classifier_contract_sha256,rawClassifierSha,"the canonical manifest must bind the real classifier contract bytes");
  // A hostile manifest declaring an all-zeros placeholder SHA must fail closed
  // at the resolver cross-binding before any evidence is authorized.
  const spec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};
  const evidenceWithCohort={schema_version:1,evidence:[{...canonicalEvidence,requirement_id:"REQ-BRAIN-101-R15-SOAK-DURATION",evidence_kind:"RUNTIME_OBSERVATION",evidence_level:"L8_SOAK" as const,source_sha:candidate,certified_implementation_sha:candidate,artifact_path:artifactPath,artifact_sha256:sha(artifact),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"p",assertion_type:"OBSERVATION" as const,soak_execution_id:rawManifest.soak_execution_id,observation:{duration_seconds:2592000,sample_size:30},verifier:{verifier_id:"v",source_sha:candidate,independent:true}}]};
  const hostileBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===manifestPath)return JSON.stringify({...rawManifest,regime_classifier_contract_sha256:"0".repeat(64)});
    if(path==="docs/roadmap/semantic/evidence.json")return JSON.stringify(evidenceWithCohort);
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  assert.throws(()=>productionEffectsWithBus(hostileBus).resolveSemanticCompletion(spec,candidate),/regime classifier contract not bound/i);
});

test("P2-1 BYTE_HASH_BINDING is isolated: same semantics, different bytes => different decision hash",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  // Manifest-only byte difference (note): the classifier — and therefore the
  // evidence coherence — is UNTOUCHED. Identical semantics, different bytes.
  const byteDifferentManifestBase={...authorities.governedManifest,note:"byte-different"};
  const byteDifferentManifest={...byteDifferentManifestBase,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(byteDifferentManifestBase),"utf8").digest("hex")};
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const input=authoritativeInput(candidate,evidence);
  const real=evaluateSemanticCompletion(input,artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  const forged=evaluateSemanticCompletion(input,artifacts,undefined,byteDifferentManifest,authorities.governedClassifier);
  assert.equal(real.decision,"PASS");
  assert.equal(forged.decision,"PASS","identical semantics => same decision");
  assert.notEqual(real.decision_artifact_sha256,forged.decision_artifact_sha256,"different bound bytes => different decision identity");
});

test("P2-2 REGIME_SEMANTICS come from the governed contract, not gate constants",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  // A coherent pair whose contract demands MORE distinct regimes than the
  // evidence provides: the threshold must be read from the CONTRACT bytes.
  const demandingClassifierBase={...authorities.governedClassifier,minimum_distinct_regimes:5};
  const demandingClassifierSha=createHash("sha256").update(JSON.stringify(demandingClassifierBase),"utf8").digest("hex");
  const demandingClassifier={...demandingClassifierBase,regime_classifier_contract_sha256:demandingClassifierSha};
  const demandingManifestBase={...authorities.governedManifest,regime_classifier_contract_sha256:demandingClassifierSha};
  const demandingManifest={...demandingManifestBase,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(demandingManifestBase),"utf8").digest("hex")};
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B","REGIME-C"]:undefined,authorities:{manifest:demandingManifest,classifier:demandingClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,syntheticKindContracts(),demandingManifest,demandingClassifier);
  assert.equal(decision.decision,"BLOCK","contract demanding 5 distinct regimes rejects a 3-regime observation");
  assert.ok(decision.reason_codes.includes("REGIME_ID_COUNT_MISMATCH"));
});

// ---------------------------------------------------------------------------
// EXECUTION LIFECYCLE + SOURCE + MATERIALIZATION AUTHORITY (external review
// round 2): completion state, soak window span, evidence-in-window binding,
// classifier definition materialization, and execution source SHA authority.
// ---------------------------------------------------------------------------

/** Kind-contract document bytes including the governed requires_regime_identity flag. */
function fixtureKindContractsWithFlag(requiresRegimeIdentity:boolean){
  return JSON.stringify({schema_version:1,roadmap_id:"BRAIN-101",calendar_day_policy:"UTC_24H_DAY",minimum_regime_count_for_multiple:2,kinds:{
    RUNTIME_OBSERVATION:{assertion_contract:"runtime observation artifact",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:requiresRegimeIdentity},
    REGIME_COVERAGE:{assertion_contract:"distinct regime enumeration",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:requiresRegimeIdentity},
    BYPASS_AUDIT:{assertion_contract:"zero bypass attestation",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:requiresRegimeIdentity},
    LEDGER_RECONCILIATION:{assertion_contract:"zero ledger inconsistency attestation",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:requiresRegimeIdentity},
    DUPLICATE_ORDER_AUDIT:{assertion_contract:"zero duplicate order attestation",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true,requires_regime_identity:requiresRegimeIdentity},
    KILL_SWITCH_TEST:{assertion_contract:"executed kill-switch test",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:requiresRegimeIdentity},
    RECOVERY_TEST:{assertion_contract:"executed recovery test",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true,requires_regime_identity:requiresRegimeIdentity},
  }});
}

test("Q1 SOAK_STARTED_BUT_NOT_COMPLETED cannot authorize evidence",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  // A soak that started but has NOT completed cannot yet have full-window
  // qualifying evidence: 30-day window evidence implies the window closed.
  const authorities=syntheticGovernedAuthorities("EXECUTING");
  assert.equal(authorities.governedManifest.started_at_utc!==null,true);
  assert.equal(authorities.governedManifest.ended_at_utc,null);
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","a started-but-never-ended soak cannot vouch a completed 30-day observation");
  assert.ok(decision.reason_codes.includes("SOAK_EXECUTION_NOT_COMPLETED"));
});

test("Q2 COMPLETED_SOAK_WITH_SHORT_WINDOW cannot authorize full-window evidence",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  // The governed window spans only 15 days (1296000s) — evidence claiming a
  // 30-day (2592000s) observation cannot have occurred INSIDE this window.
  const shortWindowManifestBase={...authorities.governedManifest,ended_at_utc:"2026-09-25T00:00:00.000Z"};
  const shortWindowManifest={...shortWindowManifestBase,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(shortWindowManifestBase),"utf8").digest("hex")};
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:shortWindowManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,shortWindowManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","a 30-day observation cannot fit a 15-day governed window");
  assert.ok(decision.reason_codes.includes("EVIDENCE_OUTSIDE_SOAK_WINDOW"));
});

test("Q3 evidence observed OUTSIDE the governed soak window is rejected",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  // All evidence is INSIDE the window except the kill-switch test, which
  // claims an execution date before the soak started.
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const outsideWindow=evidence.map((record,index)=>index===5?{...record,observed_at_utc:"2025-01-01T00:00:00.000Z"}:record);
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,outsideWindow),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","a kill-switch test executed before the soak window does not prove this soak");
  assert.ok(decision.reason_codes.includes("EVIDENCE_OUTSIDE_SOAK_WINDOW"));
});

test("Q4 COMPLETED_FULL_WINDOW soak authorizes the complete qualifying set",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"PASS","a completed 30-day governed window with in-window evidence satisfies every clause");
  assert.equal(decision.requirements_satisfied,7);
});

test("Q5 CLASSIFIER_DEFINITION_MATERIALIZATION is proven by the resolver from Git",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const manifestLoaderForQ5=()=>JSON.parse(authorities.loaderManifestBytes);
  // The REAL canonical classifier is truthfully PREREGISTERED with no
  // materialized definition — documented separately from this isolation test.
  const {classifier:realClassifier}=governedSemanticAuthorities();
  assert.equal(realClassifier.state,"PREREGISTERED_NOT_YET_OBSERVED");
  assert.equal(realClassifier.definition_sha256,null);
  // ISOLATION (per review): a COMPLETED governed soak + coherent pair whose
  // classifier is NOT materialized. Regime evidence must fail closed on
  // materialization — NOT masked by soak lifecycle codes.
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const classifierBase=authorities.governedClassifier;
  const {regime_classifier_contract_sha256:_clsShaDrop,...classifierWithoutSha}=classifierBase;
  const nonMaterializedBase={...classifierWithoutSha,definition_path:null,definition_sha256:null,state:"PREREGISTERED_NOT_YET_OBSERVED" as const} as typeof classifierBase;
  const nonMaterializedLoaderBytes=JSON.stringify(nonMaterializedBase);
  const nonMaterializedSha=createHash("sha256").update(nonMaterializedLoaderBytes,"utf8").digest("hex");
  const coherentClassifier={...nonMaterializedBase,regime_classifier_contract_sha256:nonMaterializedSha};
  const coherentManifestBase={...manifestLoaderForQ5(),regime_classifier_contract_sha256:nonMaterializedSha};
  const {soak_execution_manifest_sha256:_shaDrop,...coherentLoader}=coherentManifestBase as Record<string,unknown>;
  const coherentManifest={...coherentManifestBase,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(coherentLoader),"utf8").digest("hex")};
  const spec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};
  const evidenceWithRegime={schema_version:1,evidence:[
    {evidence_id:"E-DUR",requirement_id:"REQ-BRAIN-101-R15-SOAK-DURATION",evidence_kind:"RUNTIME_OBSERVATION",evidence_level:"L8_SOAK" as const,source_sha:candidate,certified_implementation_sha:candidate,artifact_path:artifactPath,artifact_sha256:sha(artifact),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"p",assertion_type:"OBSERVATION" as const,soak_execution_id:coherentManifest.soak_execution_id,observation:{duration_seconds:2592000,sample_size:30},verifier:{verifier_id:"v",source_sha:candidate,independent:true}},
    {evidence_id:"E-REG",requirement_id:"REQ-BRAIN-101-R15-SOAK-REGIMES",evidence_kind:"REGIME_COVERAGE",evidence_level:"L8_SOAK" as const,source_sha:candidate,certified_implementation_sha:candidate,artifact_path:artifactPath,artifact_sha256:sha(artifact),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"p",assertion_type:"OBSERVATION" as const,soak_execution_id:coherentManifest.soak_execution_id,observed_regime_ids:["REGIME-A","REGIME-B"],classifier_id:coherentClassifier.classifier_id,classifier_version:coherentClassifier.classifier_version,classifier_contract_sha256:nonMaterializedSha,observation:{duration_seconds:2592000,sample_size:2},verifier:{verifier_id:"v",source_sha:candidate,independent:true}},
  ]};
  const isolationBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===manifestPath)return JSON.stringify(coherentLoader);
    if(path===classifierPath)return nonMaterializedLoaderBytes;
    if(path==="docs/roadmap/semantic/evidence.json")return JSON.stringify(evidenceWithRegime);
    if(path===artifactPath)return artifact;
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  const decision=productionEffectsWithBus(isolationBus).resolveSemanticCompletion(spec,candidate);
  assert.equal(decision.decision,"BLOCK","a non-materialized classifier can never authorize regime observations, even under a completed soak");
  assert.ok(decision.reason_codes.includes("REGIME_CLASSIFIER_NOT_MATERIALIZED"));
  assert.ok(!decision.reason_codes.includes("SOAK_EXECUTION_NOT_STARTED"),"materialization must not be masked by lifecycle codes");
  assert.ok(!decision.reason_codes.includes("SOAK_EXECUTION_NOT_COMPLETED"),"materialization must not be masked by lifecycle codes");
});

test("Q5b FORGED classifier definition is rejected by the PRODUCTION resolver's byte verification",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  // OBSERVED classifier declaring a materialized definition — but the bus
  // serves bytes that DIFFER from the declared SHA: forged materialization.
  const declaredDefinitionSha=createHash("sha256").update("legitimate definition bytes","utf8").digest("hex");
  const forgedClassifierBase={...authorities.governedClassifier,definition_path:"docs/roadmap/semantic/synthetic-classifier-definition.json",definition_sha256:declaredDefinitionSha,state:"OBSERVED" as const};
  const forgedLoaderBytes=JSON.stringify(forgedClassifierBase);
  const forgedClassifierSha=createHash("sha256").update(forgedLoaderBytes,"utf8").digest("hex");
  const forgedClassifier={...forgedClassifierBase,regime_classifier_contract_sha256:forgedClassifierSha};
  const {soak_execution_manifest_sha256:_drop2,...manifestLoader}=authorities.governedManifest as Record<string,unknown>;
  const forgedManifestLoader={...manifestLoader,regime_classifier_contract_sha256:forgedClassifierSha};
  const forgedManifest={...forgedManifestLoader,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(forgedManifestLoader),"utf8").digest("hex")};
  const spec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};
  const forgedBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===manifestPath)return JSON.stringify(forgedManifestLoader);
    if(path===classifierPath)return forgedLoaderBytes;
    if(path==="docs/roadmap/semantic/synthetic-classifier-definition.json")return "FORGED definition bytes that do not hash to the declared SHA";
    if(path==="docs/roadmap/semantic/evidence.json")return JSON.stringify({schema_version:1,evidence:[]});
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  assert.throws(()=>productionEffectsWithBus(forgedBus).resolveSemanticCompletion(spec,candidate),/definition not materialized|canonical regime classifier contract invalid/i);
});

test("Q5c MISSING classifier definition artifact fails closed at the resolver",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  // OBSERVED classifier declaring a definition that does not exist in the bus.
  const declaredDefinitionSha=createHash("sha256").update("definition bytes","utf8").digest("hex");
  const missingDefinitionClassifierBase={...authorities.governedClassifier,definition_path:"docs/roadmap/semantic/absent-definition.json",definition_sha256:declaredDefinitionSha,state:"OBSERVED" as const};
  const missingLoaderBytes=JSON.stringify(missingDefinitionClassifierBase);
  const missingClassifierSha=createHash("sha256").update(missingLoaderBytes,"utf8").digest("hex");
  const missingClassifier={...missingDefinitionClassifierBase,regime_classifier_contract_sha256:missingClassifierSha};
  const {soak_execution_manifest_sha256:_drop3,...manifestLoader3}=authorities.governedManifest as Record<string,unknown>;
  const missingManifestLoader={...manifestLoader3,regime_classifier_contract_sha256:missingClassifierSha};
  const missingManifest={...missingManifestLoader,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(missingManifestLoader),"utf8").digest("hex")};
  const spec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};
  const missingBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===manifestPath)return JSON.stringify(missingManifestLoader);
    if(path===classifierPath)return missingLoaderBytes;
    if(path==="docs/roadmap/semantic/absent-definition.json")throw new Error("not found");
    if(path==="docs/roadmap/semantic/evidence.json")return JSON.stringify({schema_version:1,evidence:[]});
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  assert.throws(()=>productionEffectsWithBus(missingBus).resolveSemanticCompletion(spec,candidate),/definition not materialized|canonical regime classifier contract invalid/i);
});

test("Q6 PLACEHOLDER execution source_sha fails closed",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  // A manifest with an all-zeros placeholder source_sha (the PRE-remediation
  // canonical state) must fail closed structurally at the resolver.
  const spec={...parentSpec,roadmap_id:"BRAIN-101",roadmap_item_id:"R15",semantic_completion:{requirements_path:"docs/roadmap/semantic/requirements.json",evidence_path:"docs/roadmap/semantic/evidence.json"}};
  const rawManifest=JSON.parse(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/soak_execution_manifest.json`],{encoding:"utf8"}));
  const evidenceWithCohort={schema_version:1,evidence:[{...canonicalEvidence,requirement_id:"REQ-BRAIN-101-R15-SOAK-DURATION",evidence_kind:"RUNTIME_OBSERVATION",evidence_level:"L8_SOAK" as const,source_sha:candidate,certified_implementation_sha:candidate,artifact_path:artifactPath,artifact_sha256:sha(artifact),environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",observed_at_utc:"2026-09-10T00:00:00.000Z",producer_id:"p",assertion_type:"OBSERVATION" as const,soak_execution_id:rawManifest.soak_execution_id,observation:{duration_seconds:2592000,sample_size:30},verifier:{verifier_id:"v",source_sha:candidate,independent:true}}]};
  const hostileBus={setMutationGuard:()=>{},fileAt:(path:string,ref:string)=>{
    if(path===manifestPath)return JSON.stringify({...rawManifest,source_sha:"0".repeat(40)});
    if(path==="docs/roadmap/semantic/evidence.json")return JSON.stringify(evidenceWithCohort);
    if(path===artifactPath)return artifact;
    return execFileSync("git",["show",`${ref}:${path}`],{encoding:"utf8"});
  }} as any;
  assert.throws(()=>productionEffectsWithBus(hostileBus).resolveSemanticCompletion(spec,candidate),/canonical soak execution manifest invalid/i);
});

test("Q6b REAL canonical manifest binds the actual evaluation source_sha",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const rawManifest=JSON.parse(execFileSync("git",["show",`${candidate}:docs/roadmap/semantic/soak_execution_manifest.json`],{encoding:"utf8"}));
  assert.notEqual(rawManifest.source_sha,"0".repeat(40),"the canonical manifest must no longer declare a placeholder source");
  assert.match(rawManifest.source_sha,/^[0-9a-f]{40}$/);
});

test("Q8 EXECUTION_SOURCE AUTHORITY: manifest source_sha must equal the evaluated source for cohort evidence",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  // COMPLETED governed soak, coherent classifier, perfect evidence bound to
  // the CANDIDATE source — but the manifest declares a DIFFERENT valid source
  // SHA. The execution authority chain (evidence.source_sha ↔ input source ↔
  // manifest.source_sha) is broken: must BLOCK, not authorize.
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const foreignSource="9".repeat(40);
  const foreignManifestBase={...authorities.governedManifest,source_sha:foreignSource};
  const foreignManifest={...foreignManifestBase,soak_execution_manifest_sha256:createHash("sha256").update(JSON.stringify(foreignManifestBase),"utf8").digest("hex")};
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const decision=evaluateSemanticCompletion(authoritativeInput(candidate,evidence),artifacts,undefined,foreignManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"BLOCK","cohort evidence cannot be authorized by a soak bound to a different execution source");
  assert.ok(decision.reason_codes.includes("EVIDENCE_COHORT_AUTHORITY_MISMATCH"),"the manifest's execution source must match the evaluated source");
});

test("Q7 REGIME_IDENTITY trigger is governed by the kind contract, not the kind string",()=>{
  const candidate=execFileSync("git",["rev-parse","HEAD"],{encoding:"utf8"}).trim();
  const authorities=syntheticGovernedAuthorities("COMPLETED");
  const {evidence,artifacts}=authoritativeEvidenceSet(candidate,{regimeIds:index=>index===1?["REGIME-A","REGIME-B"]:undefined,authorities:{manifest:authorities.governedManifest,classifier:authorities.governedClassifier}});
  const input=authoritativeInput(candidate,evidence);
  // Contract set WITHOUT regime-identity requirement: the same REGIME_COVERAGE
  // evidence must NOT be subjected to regime authority checks — decoupling
  // proven: the trigger comes from the contract flag, not the kind name.
  const contractsWithoutRegime={schema_version:1 as const,roadmap_id:"BRAIN-101",calendar_day_policy:"UTC_24H_DAY" as const,minimum_regime_count_for_multiple:2,kinds:Object.fromEntries(Object.entries({
    RUNTIME_OBSERVATION:{assertion_contract:"a",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true},
    REGIME_COVERAGE:{assertion_contract:"a",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true},
    BYPASS_AUDIT:{assertion_contract:"a",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true},
    LEDGER_RECONCILIATION:{assertion_contract:"a",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true},
    DUPLICATE_ORDER_AUDIT:{assertion_contract:"a",attestation_model:"artifact bytes + independent verifier",zero_condition:true,tested_runtime_execution:true},
    KILL_SWITCH_TEST:{assertion_contract:"a",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true},
    RECOVERY_TEST:{assertion_contract:"a",attestation_model:"artifact bytes + independent verifier",zero_condition:false,tested_runtime_execution:true},
  }).map(([kind,contract])=>[kind,{...contract,requires_regime_identity:false}]))} as any;
  // The evidence REGIME record binds the governed classifier; with the
  // contract flag OFF the classifier check must not fire at all (PASS),
  // proving the trigger is contract-driven.
  const decision=evaluateSemanticCompletion(input,artifacts,contractsWithoutRegime,authorities.governedManifest,authorities.governedClassifier);
  assert.equal(decision.decision,"PASS","without the contract's regime-identity flag, no regime authority check fires");
});

// ---------------------------------------------------------------------------
// TASK 4 — SYNTHETIC AGENT LOOP CERTIFICATION (SR16).
// A bounded, in-memory, TEST-ONLY simulation of the Agent Loop integration:
// it routes a synthetic front through the REAL semantic completion path and
// asserts that a simulated 30-day claim can never close an L8 soak parent
// even when CI, review, and contracts all appear PASS. No worker, scheduler,
// GitHub, broker, provider, network, filesystem runtime, or deployment is
// imported or started; the loop is bounded and returns, never persistent.
// ---------------------------------------------------------------------------

/** Shape of the bounded synthetic Agent Loop result (test-only). */
interface SyntheticAgentLoopResult{
  semantic_completion:"PASS"|"BLOCK";
  closeout:"PASS"|"BLOCK";
  successor_authorization:"PASS"|"BLOCK";
  agent_loop_semantic_gate_certification:"PASS"|"BLOCK";
}

/** Builds a synthetic soak-parent requirement for the SR16 scenario. */
function srRequirement(minimumEvidenceLevel:"L8_SOAK"|"L4_SIMULATED_INTEGRATION"){
  return {requirement_id:"REQ-SR16-SOAK-PARENT",parent_phase:"R15",original_spec_path:"docs/roadmap/BRAIN_101_ROADMAP.md",
    original_spec_sha256:sha("sr16 roadmap bytes"),requirement_text_sha256:sha("SR16 synthetic soak parent"),
    minimum_evidence_level:minimumEvidenceLevel,required_evidence_kinds:["RUNTIME_OBSERVATION"],
    runtime_binding_required:true,deferment_policy:"FORBIDDEN" as const,parent_requirement_ids:[],
    required_environments:["PAPER_RUNTIME"],independent_verifier_required:true,
    minimum_duration_seconds:2592000,minimum_sample_size:1,cohort_group:undefined};
}

/**
 * TEST-ONLY bounded synthetic Agent Loop (SR16). Simulates the conceptual
 * integration of the autonomous flow — build → CI → review → contracts →
 * semantic completion → closeout → successor — entirely in memory, routing
 * the semantic decision through the REAL evaluateSemanticCompletion() gate.
 * No worker, scheduler, GitHub client, broker, provider, network call,
 * filesystem runtime, deployment, or persistent loop is involved: the loop
 * is a single bounded await that returns a result and terminates.
 *
 * The certification field means "the gate correctly prevented the false
 * completion", NOT that the requirement was satisfied.
 */
async function runBoundedSyntheticAgentLoop(scenario:{
  parent:ReturnType<typeof srRequirement>;
  child:{evidence_level:"L8_SOAK"|"L4_SIMULATED_INTEGRATION";environment:"PAPER_RUNTIME"|"SIMULATOR";duration_seconds?:number};
  ci:"PASS"|"BLOCK";review:"PASS"|"BLOCK";contracts:"PASS"|"BLOCK";
}):Promise<SyntheticAgentLoopResult>{
  // In-memory synthetic artifact bytes for the child claim.
  const artifactBytes=JSON.stringify({claim:"SR16 synthetic child evidence",level:scenario.child.evidence_level,environment:scenario.child.environment,duration_seconds:scenario.child.duration_seconds??2592000});
  const artifacts=new Map([["docs/roadmap/semantic/sr16-child.json",artifactBytes]]);
  const sourceSha="a".repeat(40);
  const now="2026-09-10T00:00:00.000Z";
  // Build the semantic input entirely in memory around the synthetic parent.
  const input={schema_version:1 as const,phase_or_item_id:"R15",source_sha:sourceSha,evaluated_at_utc:now,
    requirements:[scenario.parent],
    expected_requirement_ids:[scenario.parent.requirement_id],
    expected_requirements:[{...scenario.parent}],
    evidence:[{evidence_id:"EVIDENCE-SR16-CHILD",requirement_id:scenario.parent.requirement_id,evidence_kind:"RUNTIME_OBSERVATION",
      evidence_level:scenario.child.evidence_level,source_sha:sourceSha,certified_implementation_sha:sourceSha,
      artifact_path:"docs/roadmap/semantic/sr16-child.json",artifact_sha256:createHash("sha256").update(artifactBytes,"utf8").digest("hex"),
      environment:scenario.child.environment,runtime_binding:"paper-runtime:v1",
      observed_at_utc:now,producer_id:"synthetic-agent-loop",assertion_type:"OBSERVATION" as const,
      observation:{duration_seconds:scenario.child.duration_seconds??2592000,sample_size:1},
      verifier:{verifier_id:"independent-synthetic-verifier",source_sha:sourceSha,independent:true}}],
    deferments:[],deferment_authorizations:[]};
  // THE semantic authority: the single gate decides PASS/BLOCK. CI, review,
  // and contracts being "PASS" are deliberately ignored by the gate — the
  // loop routes its closeout and successor decisions through it.
  const decision=evaluateSemanticCompletion(input,artifacts);
  const semanticCompletion:SyntheticAgentLoopResult["semantic_completion"]=decision.decision;
  // Closeout may only proceed when the semantic decision is PASS.
  const closeout:SyntheticAgentLoopResult["closeout"]=semanticCompletion==="PASS"&&scenario.ci==="PASS"&&scenario.review==="PASS"&&scenario.contracts==="PASS"?"PASS":"BLOCK";
  // Successor authorization may only proceed after closeout PASS.
  const successorAuthorization:SyntheticAgentLoopResult["successor_authorization"]=closeout==="PASS"?"PASS":"BLOCK";
  // The certification PASSes when the gate outcome was correctly enforced
  // end-to-end: BLOCK prevented closeout and successor; PASS allowed them.
  const certification:SyntheticAgentLoopResult["agent_loop_semantic_gate_certification"]=
    (semanticCompletion==="BLOCK"&&closeout==="BLOCK"&&successorAuthorization==="BLOCK")||
    (semanticCompletion==="PASS"&&closeout==="PASS"&&successorAuthorization==="PASS")?"PASS":"BLOCK";
  return {semantic_completion:semanticCompletion,closeout,successor_authorization:successorAuthorization,agent_loop_semantic_gate_certification:certification};
}

test("SR16 simulated 30D cannot close an L8 soak parent",async()=>{
  const result=await runBoundedSyntheticAgentLoop({
    parent:srRequirement("L8_SOAK"),
    child:{evidence_level:"L4_SIMULATED_INTEGRATION",environment:"SIMULATOR"},
    ci:"PASS",review:"PASS",contracts:"PASS",
  });
  assert.equal(result.semantic_completion,"BLOCK");
  assert.equal(result.closeout,"BLOCK");
  assert.equal(result.successor_authorization,"BLOCK");
  assert.equal(result.agent_loop_semantic_gate_certification,"PASS");
});

test("SR16 positive control: genuinely eligible evidence is not blocked by the certification",async()=>{
  const result=await runBoundedSyntheticAgentLoop({
    parent:srRequirement("L8_SOAK"),
    child:{evidence_level:"L8_SOAK",environment:"PAPER_RUNTIME",duration_seconds:2592000},
    ci:"PASS",review:"PASS",contracts:"PASS",
  });
  assert.equal(result.semantic_completion,"PASS");
  assert.equal(result.closeout,"PASS");
  assert.equal(result.successor_authorization,"PASS");
  assert.equal(result.agent_loop_semantic_gate_certification,"PASS");
});
