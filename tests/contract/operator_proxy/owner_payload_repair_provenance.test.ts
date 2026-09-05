import test from "node:test";
import assert from "node:assert/strict";
import {verifyOwnerPayloadRepairAdoption} from "../../../scripts/operator_proxy/lineage.js";
import {dispatchOwnerAuthorizedPayloadRepair,ownerPayloadRepairBuilderInput,parseOwnerPayloadRepairCommitReceipt} from "../../../scripts/operator_proxy/governed_builder.js";
import {parseCorrectionPayloadV1} from "../../../scripts/operator_proxy/correction_payload.js";
import type {OwnerAuthorizedPayloadRepairGrant,ProxySpec} from "../../../scripts/operator_proxy/types.js";
import type {CandidateExecutionAdapter} from "../../../scripts/operator_proxy/candidate_execution.js";

const base="a".repeat(40),failed="b".repeat(40),head="c".repeat(40);
const spec:ProxySpec={schema_version:1,authorization_id:"AUTH-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1",roadmap_item_id:"R3.5",expected_base_sha:base,executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:[],test_commands:["git diff --check"],deployment_allowed:false,work_branch:"control-plane/owner-repair",front_id:"BRAIN-101-R3-OWNER-01",deployment_mode:"NO_DEPLOY"};
const payload={schema_version:1 as const,requirements:[{requirement_id:"r",instruction:"fix"}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]};
const parsedPayload=parseCorrectionPayloadV1(payload);
const grant:OwnerAuthorizedPayloadRepairGrant={schema_version:1,authorization_id:"AUTH-01",grant_key:"d".repeat(64),owner_principal:"cesarmanuel8102",repository:spec.repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id!,issue:1,pr:2,work_branch:spec.work_branch!,canonical_base_sha:base,failed_head_sha:failed,eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:parsedPayload.payload,correction_payload_sha256:parsedPayload.sha256,owner_comment_id:"1",authorization_body_sha256:"f".repeat(64)};
const observed=()=>({spec,grant,new_head_sha:head,remote_branch_head:head,pr:{number:2,head,base,identity:{author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:base,headRefName:spec.work_branch,headRefOid:head,headRepository:{nameWithOwner:spec.repository},isCrossRepository:false,isDraft:true,state:"OPEN",files:[{path:"docs/x.md"}]},trustedAuthor:true,pathsInScope:true},provenance:{authorization_id:grant.authorization_id,grant_key:grant.grant_key,build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64)},consumed_event_sha256:"2".repeat(64),build_attempt_id:"1".repeat(64),isAncestor:(older:string,newer:string)=>older===failed&&newer===head||older===base&&newer===head});

test("owner adoption requires exact descendant head, PR identity, paths, and all four provenance anchors",()=>{
  assert.equal(verifyOwnerPayloadRepairAdoption(observed()),true);
  for(const mutate of [
    (x:any)=>x.provenance.authorization_id="other",(x:any)=>x.provenance.grant_key="0".repeat(64),(x:any)=>x.provenance.build_attempt_id="0".repeat(64),(x:any)=>x.provenance.consumed_event_sha256="0".repeat(64),
    (x:any)=>x.pr.identity.headRefOid=failed,(x:any)=>x.remote_branch_head=failed,(x:any)=>x.pr.identity.headRefName="other",(x:any)=>x.pr.identity.baseRefOid=failed,(x:any)=>x.pr.identity.files=[{path:"trading/x.py"}],
    (x:any)=>x.isAncestor=()=>false,(x:any)=>x.provenance.consumed_event_sha256="3".repeat(64),
  ]) {const value=observed();mutate(value);assert.equal(verifyOwnerPayloadRepairAdoption(value),false);}
});

test("exceptional builder input is typed, anchored, and contains no free-form owner body",()=>{
  const input=ownerPayloadRepairBuilderInput(grant,{build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64),correction_payload:grant.correction_payload});
  assert.deepEqual(input.provenance,{authorization_id:grant.authorization_id,grant_key:grant.grant_key,build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64)});
  assert.equal(JSON.stringify(input).includes("owner_comment"),false);
  assert.throws(()=>ownerPayloadRepairBuilderInput(grant,{build_attempt_id:"1".repeat(64),consumed_event_sha256:"future",correction_payload:grant.correction_payload}),/consumed/);
});

test("dedicated owner dispatcher sends one typed logical attempt without ordinary repair semantics",async()=>{
  const seen:any[]=[],receipts:string[]=[];
  const publication:CandidateExecutionAdapter={prepare:()=>({worktree:"C:/owner",starting_head:failed}),validateExistingDraftPr:()=>{},invokeProvider:async request=>{seen.push(request);return {executor_role:"codex_control_plane",builder_backend:"opencode_ollama",builder_model:"ollama-cloud/kimi-k2.7-code",builder_session:"provider-session",provider_session:"provider-correlation",base_sha:failed,head_sha:head,branch:spec.work_branch!};},changedPaths:()=>["docs/x.md"],runDeclaredTests:()=>{},diffCheck:()=>{},commit:(_worktree,receipt)=>{receipts.push(receipt);return head;},push:()=>{},remoteHead:()=>head,existingDraftPr:()=>({number:grant.pr,repository:grant.repository,issue:grant.issue,work_branch:grant.work_branch,base_sha:base,head_sha:head,is_draft:true,is_open:true,same_repository:true,non_fork:true,author_login:"cesarmanuel8102",base_ref_name:"codex/own-capital-sustainable-return",base_ref_oid:base,head_ref_name:grant.work_branch,head_ref_oid:head,changed_paths:["docs/x.md"]}),createDraftPr:()=>{throw new Error("unexpected PR");},bindPrToIssue:()=>{}};
  const context={spec,grant,issue:grant.issue,build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64),correction_payload:parsedPayload.payload,publication,owner_comment:"untrusted free-form instruction"} as any;
  const first=await dispatchOwnerAuthorizedPayloadRepair(context);
  const retry=await dispatchOwnerAuthorizedPayloadRepair(context);
  assert.equal(seen.length,2);
  assert.equal(seen[0].idempotency_key,context.build_attempt_id);
  assert.equal(seen[1].idempotency_key,context.build_attempt_id);
  assert.equal(seen[0].repair_cycle,undefined);
  assert.equal(seen[0].prompt.includes("owner_comment"),false);
  assert.equal(seen[0].prompt.includes(context.owner_comment),false);
  for(const anchor of ["OWNER_AUTHORIZATION_ID=AUTH-01",`OWNER_GRANT_KEY=${grant.grant_key}`,`OWNER_BUILD_ATTEMPT_ID=${context.build_attempt_id}`,`OWNER_CONSUMED_EVENT_SHA256=${context.consumed_event_sha256}`])assert.match(receipts[0],new RegExp(anchor));
  assert.deepEqual(first.provenance,retry.provenance);
  assert.deepEqual(first.provenance,{authorization_id:grant.authorization_id,grant_key:grant.grant_key,build_attempt_id:context.build_attempt_id,consumed_event_sha256:context.consumed_event_sha256});
});

test("owner recovery parses only an exact immutable publication receipt",()=>{
  const message=[`fix(control-plane): owner payload repair ${spec.front_id}`,"",`OWNER_AUTHORIZATION_ID=${grant.authorization_id}`,`OWNER_GRANT_KEY=${grant.grant_key}`,`OWNER_BUILD_ATTEMPT_ID=${"1".repeat(64)}`,`OWNER_CONSUMED_EVENT_SHA256=${"2".repeat(64)}`,"BUILDER_BACKEND=opencode_ollama","BUILDER_MODEL=ollama-cloud/kimi-k2.7-code","PROVIDER_SESSION=provider-session"].join("\n");
  assert.deepEqual(parseOwnerPayloadRepairCommitReceipt(message,spec.front_id!),{provenance:{authorization_id:grant.authorization_id,grant_key:grant.grant_key,build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64)},builder_backend:"opencode_ollama",builder_session:"provider-session",provider_session:"provider-session",builder_model:"ollama-cloud/kimi-k2.7-code"});
  assert.throws(()=>parseOwnerPayloadRepairCommitReceipt(message.replace("PROVIDER_SESSION=provider-session","PROVIDER_SESSION=provider-session\nPROVIDER_SESSION=other"),spec.front_id!),/owner repair commit receipt invalid/);
  assert.throws(()=>parseOwnerPayloadRepairCommitReceipt(message.replace(`OWNER_GRANT_KEY=${grant.grant_key}`,"OWNER_GRANT_KEY=not-a-sha"),spec.front_id!),/owner repair commit receipt invalid/);
});

test("dedicated owner dispatcher rejects mismatched grant identity and protected control paths before transport",async()=>{
  let calls=0;
  const publication:any={invokeProvider:async()=>{calls++;throw new Error("must not run");}};
  const context:any={spec,grant,issue:grant.issue,build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64),correction_payload:parsedPayload.payload,publication};
  await assert.rejects(()=>dispatchOwnerAuthorizedPayloadRepair({...context,issue:99}),/issue/);
  await assert.rejects(()=>dispatchOwnerAuthorizedPayloadRepair({...context,spec:{...spec,allowed_paths:["scripts\/operator_proxy\/authority\/"]}}),/owner repair path/);
  await assert.rejects(()=>dispatchOwnerAuthorizedPayloadRepair({...context,spec:{...spec,allowed_paths:["scripts/"]}}),/owner repair path/);
  await assert.rejects(()=>dispatchOwnerAuthorizedPayloadRepair({...context,publication:{...publication,validateExistingDraftPr:()=>{throw new Error("owner repair existing Draft PR identity invalid");}}}),/existing Draft PR identity invalid/);
  await assert.rejects(()=>dispatchOwnerAuthorizedPayloadRepair({...context,correction_payload:{...parsedPayload.payload,requirements:[{requirement_id:"r",instruction:"other"}]}}),/correction payload/);
  assert.equal(calls,0);
});

test("dedicated owner dispatcher rejects every mismatched provenance anchor before transport",async()=>{
  let calls=0;
  const publication:any={invokeProvider:async()=>{calls++;throw new Error("must not run");}};
  const context:any={spec,grant,issue:grant.issue,build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64),correction_payload:parsedPayload.payload,publication};
  const cases=[
    {...context,spec:{...spec,authorization_id:"OTHER"}},
    {...context,spec:{...spec,work_branch:"control-plane/other"}},
    {...context,build_attempt_id:"A".repeat(64)},
    {...context,consumed_event_sha256:"A".repeat(64)},
    {...context,grant:{...grant,grant_key:"A".repeat(64)}},
  ];
  for(const value of cases)await assert.rejects(()=>dispatchOwnerAuthorizedPayloadRepair(value),/owner repair/);
  assert.equal(calls,0);
});
