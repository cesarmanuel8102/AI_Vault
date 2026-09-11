import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {evaluateSemanticCompletion} from "../../../scripts/operator_proxy/semantic_completion_gate.js";
import type {SemanticCompletionInputV1} from "../../../scripts/operator_proxy/types.js";

const sha=(value:string)=>createHash("sha256").update(value).digest("hex");
const sourceSha="a".repeat(40),artifact="verified runtime observation",artifactSha=sha(artifact);

function validInput():SemanticCompletionInputV1{
  const requirement:SemanticCompletionInputV1["requirements"][number]={
    requirement_id:"REQ-R15-SOAK-001",parent_phase:"R15",original_spec_path:"docs/roadmap/BRAIN_101_ROADMAP.md",
    original_spec_sha256:sha("roadmap bytes"),requirement_text_sha256:sha("paper soak must be observed"),
    minimum_evidence_level:"L6_RUNTIME",required_evidence_kinds:["RUNTIME_OBSERVATION"],
    runtime_binding_required:true,deferment_policy:"FORBIDDEN",parent_requirement_ids:[],
    required_environments:["PAPER_RUNTIME"],independent_verifier_required:true,
    minimum_duration_seconds:60,minimum_sample_size:1,
  };
  return {
    schema_version:1,phase_or_item_id:"BR1",source_sha:sourceSha,evaluated_at_utc:"2026-09-10T00:00:00Z",expected_requirement_ids:[requirement.requirement_id],expected_requirements:[{...requirement}],deferment_authorizations:[],
    requirements:[requirement],deferments:[],evidence:[{
      evidence_id:"EVIDENCE-R15-001",requirement_id:requirement.requirement_id,evidence_kind:"RUNTIME_OBSERVATION",
      evidence_level:"L6_RUNTIME",source_sha:sourceSha,certified_implementation_sha:sourceSha,
      artifact_path:"docs/roadmap/evidence/runtime.json",artifact_sha256:artifactSha,
      environment:"PAPER_RUNTIME",runtime_binding:"paper-runtime:v1",observed_at_utc:"2026-09-10T00:00:00Z",producer_id:"runtime-probe",assertion_type:"OBSERVATION",
      observation:{duration_seconds:60,sample_size:1},verifier:{verifier_id:"independent-contract",source_sha:sourceSha,independent:true},
    }],
  };
}

function verifiedArtifacts():ReadonlyMap<string,string>{
  return new Map([["docs/roadmap/evidence/runtime.json",artifact]]);
}

function reasonFor(mutator:(input:SemanticCompletionInputV1)=>void){
  const input=validInput();mutator(input);
  const decision=evaluateSemanticCompletion(input,verifiedArtifacts());
  assert.equal(decision.decision,"BLOCK");
  return decision.reason_codes;
}

test("SR01 valid bound evidence produces PASS",()=>{
  const decision=evaluateSemanticCompletion(validInput(),verifiedArtifacts());
  assert.equal(decision.decision,"PASS");
  assert.equal(decision.requirements_total,1);
  assert.equal(decision.requirements_satisfied,1);
  assert.deepEqual(decision.reason_codes,[]);
  assert.match(decision.decision_artifact_sha256,/^[0-9a-f]{64}$/);
});

test("rejects unknown input fields",()=>{
  assert.throws(()=>evaluateSemanticCompletion({...validInput(),unknown:true} as any,verifiedArtifacts()),/unknown semantic completion field/);
});

test("rejects duplicate requirement identity",()=>{
  const input=validInput();
  input.requirements.push({...input.requirements[0]});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/duplicate semantic requirement/);
});

test("rejects persisted artifact bytes in an evidence reference",()=>{
  const input=validInput();
  Object.assign(input.evidence[0],{artifact_bytes:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/unknown semantic evidence field/);
});

test("rejects non-enumerable persisted artifact bytes in an evidence reference",()=>{
  const input=validInput();
  Object.defineProperty(input.evidence[0],"artifact_bytes",{value:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/unknown semantic evidence field/);
});

test("rejects evidence records with an inherited prototype",()=>{
  const input=validInput();
  Object.setPrototypeOf(input.evidence[0],{artifact_bytes:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/semantic evidence invalid/);
});

test("rejects symbol-keyed evidence fields",()=>{
  const input=validInput();
  Object.assign(input.evidence[0],{[Symbol("artifact_bytes")]:artifact});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/unknown semantic evidence field/);
});

test("returns a frozen immutable decision",()=>{
  const decision=evaluateSemanticCompletion(validInput(),verifiedArtifacts());
  assert.equal(Object.isFrozen(decision),true);
  assert.equal(Object.isFrozen(decision.reason_codes),true);
  assert.equal(Object.isFrozen(decision.original_requirement_refs),true);
  assert.equal(Object.isFrozen(decision.evidence_refs),true);
  (decision as any).decision="BLOCK";
  assert.equal(decision.decision,"PASS");
  assert.throws(()=>{(decision.original_requirement_refs as string[]).push("MUTATION");},TypeError);
  assert.throws(()=>{(decision.evidence_refs as string[]).push("MUTATION");},TypeError);
});

for(const [name,mutator,code] of [
  ["SR02 missing requirement",(input:SemanticCompletionInputV1)=>{input.expected_requirement_ids=["MISSING"];},"MISSING_REQUIREMENT"],
  ["SR03 missing evidence",(input:SemanticCompletionInputV1)=>{input.evidence=[];},"MISSING_EVIDENCE"],
  ["SR04 low level",(input:SemanticCompletionInputV1)=>{input.evidence[0].evidence_level="L4_SIMULATED_INTEGRATION";},"INSUFFICIENT_EVIDENCE_LEVEL"],
  ["SR05 wrong kind",(input:SemanticCompletionInputV1)=>{input.evidence[0].evidence_kind="OTHER";},"WRONG_EVIDENCE_KIND"],
  ["SR06 stale source",(input:SemanticCompletionInputV1)=>{input.evidence[0].source_sha="b".repeat(40);},"STALE_SOURCE_SHA"],
  ["SR07 no runtime binding",(input:SemanticCompletionInputV1)=>{input.evidence[0].runtime_binding="";},"RUNTIME_BINDING_MISSING"],
  ["SR08 naked boolean",(input:SemanticCompletionInputV1)=>{input.evidence[0].assertion_type="BOOLEAN";},"NAKED_BOOLEAN_ASSERTION"],
  ["SR09 self reference",(input:SemanticCompletionInputV1)=>{input.evidence[0].producer_id=input.evidence[0].verifier.verifier_id;},"SELF_REFERENTIAL_EVIDENCE"],
  ["SR12 independent audit absent",(input:SemanticCompletionInputV1)=>{input.evidence[0].verifier.independent=false;},"INDEPENDENT_AUDIT_MISSING"],
  ["SR13 wrong environment",(input:SemanticCompletionInputV1)=>{input.evidence[0].environment="SIMULATOR";},"WRONG_EVIDENCE_KIND"],
  ["SR14 stale implementation",(input:SemanticCompletionInputV1)=>{input.evidence[0].certified_implementation_sha="b".repeat(40);},"STALE_SOURCE_SHA"],
] as const)test(name,()=>assert.deepEqual(reasonFor(mutator),[code]));

test("SR15 tampered artifact blocks",()=>{
  const input=validInput();
  assert.deepEqual(evaluateSemanticCompletion(input,new Map([[input.evidence[0].artifact_path,"tampered"]])).reason_codes,["ARTIFACT_HASH_MISMATCH"]);
});

test("SR10 invalid deferment blocks",()=>{
  assert.deepEqual(reasonFor(input=>{input.deferments=[{deferment_id:"D1",requirement_id:input.requirements[0].requirement_id,authorization_source:"owner",reason:"later",successor_owner:"owner",scope:"BR1",expiration_or_revisit_condition:"next",evidence_refs:[]}];}),["INVALID_DEFERMENT"]);
});

test("SR11 unsatisfied parent blocks",()=>{
  assert.deepEqual(reasonFor(input=>{input.requirements[0].parent_requirement_ids=["PARENT"];input.expected_requirements=[{...input.requirements[0]}];}),["PARENT_REQUIREMENT_UNSATISFIED"]);
});

test("SR16 simulation cannot substitute for required soak",()=>{
  assert.deepEqual(reasonFor(input=>{input.requirements[0].minimum_evidence_level="L8_SOAK";input.expected_requirements=[{...input.requirements[0]}];input.evidence[0].evidence_level="L4_SIMULATED_INTEGRATION";}),["SIMULATION_SUBSTITUTION"]);
});

test("blocks a child when its existing parent is blocked",()=>{
  const input=validInput(),parent={...input.requirements[0],requirement_id:"PARENT",minimum_evidence_level:"L8_SOAK" as const,parent_requirement_ids:[]};
  input.requirements=[parent,{...input.requirements[0],parent_requirement_ids:[parent.requirement_id]}];
  input.expected_requirements=input.requirements.map(requirement=>({...requirement}));
  input.expected_requirement_ids=input.requirements.map(requirement=>requirement.requirement_id);
  input.evidence[0].requirement_id=parent.requirement_id;input.evidence[0].evidence_level="L4_SIMULATED_INTEGRATION";
  input.evidence.push({...input.evidence[0],evidence_id:"EVIDENCE-CHILD",requirement_id:"REQ-R15-SOAK-001",evidence_level:"L6_RUNTIME"});
  const decision=evaluateSemanticCompletion(input,verifiedArtifacts());
  assert.equal(decision.decision,"BLOCK");assert.ok(decision.reason_codes.includes("PARENT_REQUIREMENT_UNSATISFIED"));
});

test("rejects a material requirement identity mutation",()=>{
  const input=validInput();input.requirements[0].original_spec_path="docs/other.md";
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/requirement identity mismatch/);
});

test("rejects duplicate evidence identifiers",()=>{
  const input=validInput();input.evidence.push({...input.evidence[0]});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/duplicate semantic evidence/);
});

test("valid deferment requires bound authorization and evidence",()=>{
  const input=validInput();input.evidence=[];input.requirements[0].deferment_policy="EXPLICIT_AUTHORIZATION_REQUIRED";input.expected_requirements=[{...input.requirements[0]}];
  input.deferments=[{deferment_id:"D1",requirement_id:input.requirements[0].requirement_id,authorization_source:"AUTH-1",reason:"future work",successor_owner:"owner",scope:"BR1",expiration_or_revisit_condition:"next",evidence_refs:["EVIDENCE-R15-001"]}];
  const decision=evaluateSemanticCompletion(input,verifiedArtifacts());
  assert.equal(decision.decision,"BLOCK");assert.ok(decision.reason_codes.includes("INVALID_DEFERMENT"));
});

test("accepts a policy-allowed deferment with bound authorization and evidence",()=>{
  const input=validInput(),requirement=input.requirements[0];input.evidence=[{...input.evidence[0],evidence_id:"AUTH-E1",requirement_id:"AUTH-RECORD"}];
  requirement.deferment_policy="EXPLICIT_AUTHORIZATION_REQUIRED";input.expected_requirements=[{...requirement}];
  input.deferment_authorizations=[{authorization_id:"AUTH-1",requirement_id:requirement.requirement_id,authorization_source_sha:sha("owner authorization"),authorized_by:"owner",scope:"BR1",authorized_at_utc:"2026-09-10T00:00:00Z"}];
  input.deferments=[{deferment_id:"D1",requirement_id:requirement.requirement_id,authorization_source:"AUTH-1",reason:"deferred by authorization",successor_owner:"owner",scope:"BR1",expiration_or_revisit_condition:"next",evidence_refs:["AUTH-E1"]}];
  const decision=evaluateSemanticCompletion(input,verifiedArtifacts());
  assert.equal(decision.decision,"PASS");assert.equal(decision.requirements_deferred_valid,1);
});

test("rejects duplicate authoritative requirement identities",()=>{
  const input=validInput();input.expected_requirements.push({...input.expected_requirements[0]});
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/duplicate expected semantic requirement/);
});

test("rejects a cyclic requirement graph",()=>{
  const input=validInput(),a={...input.requirements[0],requirement_id:"A",parent_requirement_ids:["B"]},b={...input.requirements[0],requirement_id:"B",parent_requirement_ids:["A"]};
  input.requirements=[a,b];input.expected_requirements=[{...a},{...b}];input.expected_requirement_ids=["A","B"];input.evidence=[];
  const decision=evaluateSemanticCompletion(input,verifiedArtifacts());
  assert.equal(decision.decision,"BLOCK");assert.ok(decision.reason_codes.includes("CYCLIC_REQUIREMENT_DEPENDENCY" as any));
});

test("higher evidence level cannot replace a required evidence kind",()=>{
  const input=validInput();input.requirements[0].minimum_evidence_level="L3_CONTRACT";input.requirements[0].required_evidence_kinds=["BROKER_RECONCILIATION"];input.expected_requirements=[{...input.requirements[0]}];input.evidence[0].evidence_level="L8_SOAK";input.evidence[0].evidence_kind="SIMULATION";
  const decision=evaluateSemanticCompletion(input,verifiedArtifacts());
  assert.equal(decision.decision,"BLOCK");assert.deepEqual(decision.reason_codes,["WRONG_EVIDENCE_KIND"]);
});

test("repeated equivalent evaluation is byte-equivalent",()=>{
  const first=evaluateSemanticCompletion(validInput(),verifiedArtifacts()),second=evaluateSemanticCompletion(validInput(),verifiedArtifacts());
  assert.deepEqual(first,second);
});

test("canonicalizes semantically unordered requirement collections",()=>{
  const first=validInput(),second=validInput();
  first.requirements[0].required_evidence_kinds=["RUNTIME_OBSERVATION","SECONDARY"];
  first.expected_requirements=[{...first.requirements[0]}];
  second.requirements[0].required_evidence_kinds=["SECONDARY","RUNTIME_OBSERVATION"];
  second.expected_requirements=[{...second.requirements[0]}];
  assert.deepEqual(evaluateSemanticCompletion(first,verifiedArtifacts()),evaluateSemanticCompletion(second,verifiedArtifacts()));
});

for(const [name,mutate,pattern] of [
  ["rejects malformed input source sha",(input:SemanticCompletionInputV1)=>{input.source_sha="bad";},/semantic completion input invalid/],
  ["rejects malformed evidence source sha",(input:SemanticCompletionInputV1)=>{input.evidence[0].source_sha="bad";},/semantic evidence invalid/],
  ["rejects malformed certified implementation sha",(input:SemanticCompletionInputV1)=>{input.evidence[0].certified_implementation_sha="bad";},/semantic evidence invalid/],
  ["rejects malformed artifact sha",(input:SemanticCompletionInputV1)=>{input.evidence[0].artifact_sha256="bad";},/semantic evidence invalid/],
  ["rejects invalid evaluated timestamp",(input:SemanticCompletionInputV1)=>{input.evaluated_at_utc="never";},/timestamp invalid/],
  ["rejects invalid observed timestamp",(input:SemanticCompletionInputV1)=>{input.evidence[0].observed_at_utc="never";},/timestamp invalid/],
  ["rejects unknown evidence level",(input:SemanticCompletionInputV1)=>{(input.evidence[0] as any).evidence_level="L99";},/semantic evidence invalid/],
  ["rejects unknown deferment policy",(input:SemanticCompletionInputV1)=>{(input.requirements[0] as any).deferment_policy="MAYBE";input.expected_requirements=[{...input.requirements[0]}];},/semantic requirement invalid/],
] as const)test(name,()=>{const input=validInput();mutate(input);assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),pattern);});

test("rejects malformed authoritative requirement hashes directly",()=>{
  const input=validInput();input.expected_requirements[0].original_spec_sha256="bad";
  assert.throws(()=>evaluateSemanticCompletion(input,verifiedArtifacts()),/semantic requirement invalid/);
});

test("rejects ambiguous deferment evidence references",()=>{
  const input=validInput(),requirement=input.requirements[0];requirement.deferment_policy="EXPLICIT_AUTHORIZATION_REQUIRED";input.expected_requirements=[{...requirement}];input.evidence=[{...input.evidence[0],evidence_id:"E1",requirement_id:"OTHER"}];
  input.deferment_authorizations=[{authorization_id:"AUTH-1",requirement_id:requirement.requirement_id,authorization_source_sha:sha("owner authorization"),authorized_by:"owner",scope:"BR1",authorized_at_utc:"2026-09-10T00:00:00Z"}];
  input.deferments=[{deferment_id:"D1",requirement_id:requirement.requirement_id,authorization_source:"AUTH-1",reason:"deferred",successor_owner:"owner",scope:"BR1",expiration_or_revisit_condition:"next",evidence_refs:["E1","E1"]}];
  const decision=evaluateSemanticCompletion(input,verifiedArtifacts());assert.equal(decision.decision,"BLOCK");assert.ok(decision.reason_codes.includes("INVALID_DEFERMENT"));
});
