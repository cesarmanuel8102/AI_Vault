import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {loadRepositoryAuthorization,resolveOwnerPrincipal} from "../../../scripts/operator_proxy/owner_principal_resolver.js";
import {validateSpec} from "../../../scripts/operator_proxy/spec_contract.js";
import type {ProxySpec} from "../../../scripts/operator_proxy/types.js";

const repository="cesarmanuel8102/AI_Vault";
const owner="cesarmanuel8102";
const authority=(value:unknown)=>{
  const path=join(mkdtempSync(join(tmpdir(),"owner-authority-")),"repository_authorization.v1.json");
  writeFileSync(path,typeof value==="string"?value:JSON.stringify(value));
  return path;
};
const record={schema_version:1,repository,owner_principal:owner};
const spec={authorization_id:"CESAR-BRAIN-101-OPERATOR-PROXY-20260722-01",repository};
const proxySpec=(allowed_paths:string[]):ProxySpec=>({schema_version:1,authorization_id:spec.authorization_id,repository,roadmap_id:"BRAIN-101",roadmap_version:"1.0.0",roadmap_item_id:"R1.1",expected_base_sha:"a".repeat(40),executor:"codex_control_plane",risk:"LOW",allowed_paths,forbidden_paths:["trading/"],acceptance:["pass"],test_commands:["git diff --check"],deployment_allowed:false,front_id:"BRAIN-101-R1-OWNER-AUTHORITY-01",deployment_mode:"NO_DEPLOY"});

test("loadRepositoryAuthorization accepts one exact versioned repository record",()=>{
  assert.deepEqual(loadRepositoryAuthorization(authority(record),repository),{repository,owner_principal:owner});
});

test("loadRepositoryAuthorization fails closed for missing malformed unknown wrong or blank authority data",()=>{
  assert.throws(()=>loadRepositoryAuthorization(join(tmpdir(),"missing-owner-authority.json"),repository),/authority.*missing/i);
  assert.throws(()=>loadRepositoryAuthorization(authority("{"),repository),/authority.*json/i);
  assert.throws(()=>loadRepositoryAuthorization(authority({...record,unexpected:true}),repository),/authority.*invalid/i);
  assert.throws(()=>loadRepositoryAuthorization(authority({...record,repository:"other/repository"}),repository),/authority.*repository/i);
  assert.throws(()=>loadRepositoryAuthorization(authority({...record,owner_principal:"  "}),repository),/authority.*principal/i);
});

test("resolveOwnerPrincipal uses a single repository candidate only when campaign authority is absent",()=>{
  assert.equal(resolveOwnerPrincipal(spec,{campaign_candidates:[],repository_candidates:[{repository,owner_principal:owner}]}),owner);
});

test("resolveOwnerPrincipal gives a valid campaign precedence only when it agrees with repository authority",()=>{
  const sources={campaign_candidates:[{authorization_id:spec.authorization_id,repository,owner_principal:owner}],repository_candidates:[{repository,owner_principal:owner}]};
  assert.equal(resolveOwnerPrincipal(spec,sources),owner);
});

test("resolveOwnerPrincipal fails closed for absent ambiguous malformed or disagreeing authority candidates",()=>{
  const repo={repository,owner_principal:owner};
  const campaign={authorization_id:spec.authorization_id,repository,owner_principal:owner};
  const cases=[
    {campaign_candidates:[],repository_candidates:[]},
    {campaign_candidates:[],repository_candidates:[repo,repo]},
    {campaign_candidates:[campaign,campaign],repository_candidates:[repo]},
    {campaign_candidates:[{...campaign,owner_principal:"other-owner"}],repository_candidates:[repo]},
    {campaign_candidates:[{...campaign,authorization_id:"wrong"}],repository_candidates:[repo]},
    {campaign_candidates:[],repository_candidates:[{...repo,owner_principal:""}]},
    {campaign_candidates:[],repository_candidates:[],github_comments:[{author:{login:owner},body:"authorize"}]},
  ];
  for(const sources of cases)assert.throws(()=>resolveOwnerPrincipal(spec,sources as any),/owner authority/i);
});

test("validateSpec forbids ordinary and exceptional allowlists from including the repository authority file or its directory",()=>{
  for(const path of [
    "scripts/operator_proxy/authority/repository_authorization.v1.json",
    "scripts/operator_proxy/authority/",
    "scripts/operator_proxy/authority/other.json",
    "scripts/operator_proxy/authority/../authority/repository_authorization.v1.json",
  ])assert.throws(()=>validateSpec(proxySpec([path])),/protected governance path|operator proxy path invalid/);
});
