import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {parseCorrectionPayloadV1} from "../../../scripts/operator_proxy/correction_payload.js";
import {discoverOwnerAuthorizedPayloadRepairGrant,parseOwnerGrantEvidenceV1,parseOwnerPayloadRepairAuthorizationEnvelopeV1,verifyOwnerAuthorizedPayloadRepairGrant} from "../../../scripts/operator_proxy/owner_payload_repair_grant.js";
import {GitHubBus} from "../../../scripts/operator_proxy/github_bus.js";
import type {ProxySpec} from "../../../scripts/operator_proxy/types.js";

const repository="cesarmanuel8102/AI_Vault",owner="cesarmanuel8102",base="a".repeat(40),failed="b".repeat(40),grantKey="c".repeat(64);
const limits={HUMAN_FINAL_AUTHORITY:true,AUTO_MERGE:false,CANONICAL_LOCAL_SYNC:false,LIVE_TRADING:false,REAL_MONEY:false} as const;
const spec:ProxySpec={schema_version:1,authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository,roadmap_id:"BRAIN-101",roadmap_version:"1.0.0",roadmap_item_id:"R3.4",expected_base_sha:base,executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,objective:"repair",work_branch:"control-plane/owner-payload-repair",front_id:"BRAIN-101-R3-OWNER-PAYLOAD-REPAIR-01",deployment_mode:"NO_DEPLOY"};
const payload={schema_version:1,requirements:[{requirement_id:"repair-lifecycle",instruction:"Preserve the lifecycle recovery contract."}],preserved_invariants:["HUMAN_FINAL_AUTHORITY","AUTO_MERGE","CANONICAL_LOCAL_SYNC","LIVE_TRADING","REAL_MONEY"],evidence_references:[{kind:"ci_run",value:"12345"}]};
const sources={campaign_candidates:[],repository_candidates:[{repository,owner_principal:owner}]};
const canonicalize=(value:unknown):unknown=>Array.isArray(value)?value.map(canonicalize):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([key,child])=>[key,canonicalize(child)])):value;
const canonical=(value:Record<string,unknown>)=>`${JSON.stringify(canonicalize(value))}\n`;
const evidence=(overrides:Record<string,unknown>={})=>{const body={schema_version:1,marker:"OWNER_AUTHORIZED_PAYLOAD_REPAIR_V1",authorization_id:spec.authorization_id,grant_key:grantKey,repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id,issue:248,pr:249,work_branch:spec.work_branch,canonical_base_sha:base,failed_head_sha:failed,eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload_sha256:parseCorrectionPayloadV1(payload).sha256,hard_limits:limits,...overrides};return {...body,authorization_body_sha256:createHash("sha256").update(canonical(body),"utf8").digest("hex")};};
const input=(overrides:Record<string,unknown>={})=>({spec,issue:248,pr:249,failed_head_sha:failed,failure_class:"CI_FAILED",ordinary_payload_repairs:2,sources,comment:{comment_id:"5000000001",author_login:owner,evidence:evidence()},correction_payload:payload,...overrides});

test("CorrectionPayloadV1 preserves array order while canonicalizing object keys into hashed UTF-8 bytes",()=>{
  const parsed=parseCorrectionPayloadV1(payload);
  const expected='{"evidence_references":[{"kind":"ci_run","value":"12345"}],"preserved_invariants":["HUMAN_FINAL_AUTHORITY","AUTO_MERGE","CANONICAL_LOCAL_SYNC","LIVE_TRADING","REAL_MONEY"],"requirements":[{"instruction":"Preserve the lifecycle recovery contract.","requirement_id":"repair-lifecycle"}],"schema_version":1}\n';
  assert.equal(parsed.canonical_json,expected);
  assert.equal(parsed.sha256,createHash("sha256").update(expected,"utf8").digest("hex"));
  const reordered=parseCorrectionPayloadV1({...payload,requirements:[{requirement_id:"other",instruction:"Keep order."},...payload.requirements]});
  assert.notEqual(reordered.sha256,parsed.sha256);
});

test("CorrectionPayloadV1 rejects unknown fields invalid schema duplicate IDs malformed references and noncanonical strings",()=>{
  const cases=[
    {...payload,unknown:true},
    {...payload,schema_version:2},
    {...payload,requirements:[...payload.requirements,{...payload.requirements[0]}]},
    {...payload,evidence_references:[{kind:"other",value:"1"}]},
    {...payload,requirements:[{...payload.requirements[0],instruction:" padded "}]},
  ];
  for(const value of cases)assert.throws(()=>parseCorrectionPayloadV1(value),/correction payload/i);
});

test("Owner grant verifier accepts exactly bound CI_FAILED evidence after two ordinary repairs",()=>{
  const grant=verifyOwnerAuthorizedPayloadRepairGrant(input());
  assert.equal(grant.owner_principal,owner);
  assert.equal(grant.grant_key,grantKey);
  assert.equal(grant.correction_payload_sha256,parseCorrectionPayloadV1(payload).sha256);
  assert.deepEqual(grant.correction_payload,payload);
  assert.match(grant.authorization_body_sha256,/^[0-9a-f]{64}$/);
});

test("Owner grant verifier rejects mismatched principal invalid failure repair count comment binding and hard-limit assertions",()=>{
  const bad=[
    input({sources:{campaign_candidates:[],repository_candidates:[{repository,owner_principal:"different"}]}}),
    input({failure_class:"CI_CANCELLED"}),
    input({ordinary_payload_repairs:1}),
    input({comment:{comment_id:"5000000001",author_login:owner,evidence:evidence({front_id:"OTHER-FRONT-01"})}}),
    input({comment:{comment_id:"5000000001",author_login:owner,evidence:evidence({hard_limits:{...limits,AUTO_MERGE:true}})}}),
    input({comment:{comment_id:"5000000001",author_login:"attacker",evidence:evidence()}}),
  ];
  for(const value of bad)assert.throws(()=>verifyOwnerAuthorizedPayloadRepairGrant(value as any),/owner grant|owner authority|hard limit/i);
});

test("Owner grant evidence parser rejects omitted and unknown fields before verification",()=>{
  const valid=evidence();
  assert.deepEqual(parseOwnerGrantEvidenceV1(valid),valid);
  assert.throws(()=>parseOwnerGrantEvidenceV1({...valid,unexpected:true}),/owner grant evidence/i);
  const {grant_key,...missing}=valid;
  assert.throws(()=>parseOwnerGrantEvidenceV1(missing),/owner grant evidence/i);
});

test("Owner grant evidence requires the exact canonical authorization body hash",()=>{
  const valid=evidence();
  assert.doesNotThrow(()=>parseOwnerGrantEvidenceV1(valid));
  assert.throws(()=>parseOwnerGrantEvidenceV1({...valid,authorization_body_sha256:"0".repeat(64)}),/authorization body hash/i);
});

test("GitHubBus exposes Issue comments as read-only evidence and rejects incomplete responses",()=>{
  const bus=new GitHubBus("gh",repository);
  (bus as any).json=()=>({comments:[{id:1,body:"evidence"}]});
  assert.deepEqual(bus.issueComments(248),[{id:1,body:"evidence"}]);
  (bus as any).json=()=>({comments:{}});
  assert.throws(()=>bus.issueComments(248),/comments response invalid/);
});

const envelope=(authorization=evidence(),correction_payload=payload)=>`BRAIN_OWNER_PAYLOAD_REPAIR_V1\n${JSON.stringify({schema_version:1,kind:"OWNER_AUTHORIZED_PAYLOAD_REPAIR",authorization,correction_payload})}\nEND_BRAIN_OWNER_PAYLOAD_REPAIR_V1`;
test("Owner payload repair envelope accepts exactly one strict machine-only typed object",()=>{
  const parsed=parseOwnerPayloadRepairAuthorizationEnvelopeV1(envelope());
  assert.deepEqual(parsed.authorization,evidence());
  assert.deepEqual(parsed.correction_payload,payload);
});
test("Owner payload repair envelope rejects prose, duplicate keys, multiple blocks, and invalid typed content",()=>{
  const valid=envelope();
  const cases=[
    `prose\n${valid}`,
    `${valid}\nprose`,
    `${valid}\n${valid}`,
    "BRAIN_OWNER_PAYLOAD_REPAIR_V1\n{\"schema_version\":1,\"schema_version\":1}\nEND_BRAIN_OWNER_PAYLOAD_REPAIR_V1",
    envelope({...evidence(),repository:"other/repo"}),
    envelope(evidence(),{...payload,unknown:true} as any),
  ];
  for(const body of cases)assert.throws(()=>parseOwnerPayloadRepairAuthorizationEnvelopeV1(body),/owner payload repair envelope/i);
});
test("Owner payload repair discovery accepts one exact owner envelope and rejects competing claimed envelopes",()=>{
  const baseInput=input();
  const comments=[{id:5000000001,author:{login:owner},body:envelope()}];
  const grant=discoverOwnerAuthorizedPayloadRepairGrant({...baseInput,comments});
  assert.equal(grant.grant_key,grantKey);
  assert.throws(()=>discoverOwnerAuthorizedPayloadRepairGrant({...baseInput,comments:[...comments,{id:5000000002,author:{login:owner},body:envelope()}]}),/owner payload repair envelope/i);
  assert.throws(()=>discoverOwnerAuthorizedPayloadRepairGrant({...baseInput,comments:[{id:5000000001,author:{login:"attacker"},body:envelope()}]}),/owner grant/i);
});
