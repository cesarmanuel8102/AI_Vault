import test from "node:test";
import assert from "node:assert/strict";
import {verifyOwnerPayloadRepairAdoption} from "../../../scripts/operator_proxy/lineage.js";
import type {OwnerAuthorizedPayloadRepairGrant,ProxySpec} from "../../../scripts/operator_proxy/types.js";

const base="a".repeat(40),failed="b".repeat(40),head="c".repeat(40);
const spec:ProxySpec={schema_version:1,authorization_id:"AUTH-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1",roadmap_item_id:"R3.5",expected_base_sha:base,executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:[],test_commands:[],deployment_allowed:false,work_branch:"control-plane/owner-repair",front_id:"BRAIN-101-R3-OWNER-01",deployment_mode:"NO_DEPLOY"};
const grant:OwnerAuthorizedPayloadRepairGrant={schema_version:1,authorization_id:"AUTH-01",grant_key:"d".repeat(64),owner_principal:"cesarmanuel8102",repository:spec.repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id!,issue:1,pr:2,work_branch:spec.work_branch!,canonical_base_sha:base,failed_head_sha:failed,eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:{schema_version:1,requirements:[{requirement_id:"r",instruction:"fix"}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]},correction_payload_sha256:"e".repeat(64),owner_comment_id:"1",authorization_body_sha256:"f".repeat(64)};
const observed=()=>({spec,grant,new_head_sha:head,remote_branch_head:head,pr:{number:2,head,base,identity:{author:{login:"cesarmanuel8102"},baseRefName:"codex/own-capital-sustainable-return",baseRefOid:base,headRefName:spec.work_branch,headRefOid:head,headRepository:{nameWithOwner:spec.repository},isCrossRepository:false,isDraft:true,state:"OPEN",files:[{path:"docs/x.md"}]},trustedAuthor:true,pathsInScope:true},provenance:{authorization_id:grant.authorization_id,grant_key:grant.grant_key,build_attempt_id:"1".repeat(64),consumed_event_sha256:"2".repeat(64)},consumed_event_sha256:"2".repeat(64),build_attempt_id:"1".repeat(64),isAncestor:(older:string,newer:string)=>older===failed&&newer===head||older===base&&newer===head});

test("owner adoption requires exact descendant head, PR identity, paths, and all four provenance anchors",()=>{
  assert.equal(verifyOwnerPayloadRepairAdoption(observed()),true);
  for(const mutate of [
    (x:any)=>x.provenance.authorization_id="other",(x:any)=>x.provenance.grant_key="0".repeat(64),(x:any)=>x.provenance.build_attempt_id="0".repeat(64),(x:any)=>x.provenance.consumed_event_sha256="0".repeat(64),
    (x:any)=>x.pr.identity.headRefOid=failed,(x:any)=>x.remote_branch_head=failed,(x:any)=>x.pr.identity.headRefName="other",(x:any)=>x.pr.identity.baseRefOid=failed,(x:any)=>x.pr.identity.files=[{path:"trading/x.py"}],
    (x:any)=>x.isAncestor=()=>false,(x:any)=>x.provenance.consumed_event_sha256="3".repeat(64),
  ]) {const value=observed();mutate(value);assert.equal(verifyOwnerPayloadRepairAdoption(value),false);}
});
