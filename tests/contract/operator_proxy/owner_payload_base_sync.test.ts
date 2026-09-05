import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdirSync,mkdtempSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {pathToFileURL} from "node:url";
import {CandidateExecutionKernel, type CandidateExecutionAdapter} from "../../../scripts/operator_proxy/candidate_execution.js";
import {dispatchOwnerAuthorizedPayloadRepair, ownerRepairCandidatePaths, parseOwnerPayloadRepairCommitReceipt} from "../../../scripts/operator_proxy/governed_builder.js";
import {GovernedBuilder} from "../../../scripts/operator_proxy/governed_builder.js";
import {ownerPayloadBaseSyncReceipt, verifyOwnerPayloadBaseSyncCommit} from "../../../scripts/operator_proxy/owner_payload_base_sync.js";
import * as governedBuilder from "../../../scripts/operator_proxy/governed_builder.js";
import {parseCorrectionPayloadV1} from "../../../scripts/operator_proxy/correction_payload.js";
import type {OwnerAuthorizedPayloadRepairGrant, ProxySpec} from "../../../scripts/operator_proxy/types.js";

const frozen="a".repeat(40),effective="b".repeat(40),synchronized="c".repeat(40),head="d".repeat(40);
const attempt="e".repeat(64),consumed="f".repeat(64),bindingEvent="1".repeat(64),dispatchEvent="2".repeat(64);
const spec:ProxySpec={schema_version:1,authorization_id:"AUTH-01",repository:"cesarmanuel8102/AI_Vault",roadmap_id:"BRAIN-101",roadmap_version:"1",roadmap_item_id:"R3.5",expected_base_sha:frozen,executor:"codex_control_plane",risk:"MEDIUM",allowed_paths:["docs/"],forbidden_paths:["trading/"],acceptance:[],test_commands:["git diff --check"],deployment_allowed:false,work_branch:"control-plane/owner-repair",front_id:"BRAIN-101-R3-OWNER-01",deployment_mode:"NO_DEPLOY"};
const payload=parseCorrectionPayloadV1({schema_version:1 as const,requirements:[{requirement_id:"r",instruction:"fix"}],preserved_invariants:["HUMAN_FINAL_AUTHORITY"]}).payload;
const grant:OwnerAuthorizedPayloadRepairGrant={schema_version:1,authorization_id:spec.authorization_id,grant_key:"3".repeat(64),owner_principal:"cesarmanuel8102",repository:spec.repository,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,front_id:spec.front_id!,issue:1,pr:2,work_branch:spec.work_branch!,canonical_base_sha:frozen,failed_head_sha:"4".repeat(40),eligible_failure_class:"CI_FAILED",max_extra_builds:1,correction_payload:payload,correction_payload_sha256:parseCorrectionPayloadV1(payload).sha256,owner_comment_id:"1",authorization_body_sha256:"5".repeat(64)};
const binding={grant_key:grant.grant_key,front_id:spec.front_id!,authorization_id:grant.authorization_id,build_attempt_id:attempt,frozen_base_sha:frozen,effective_base_sha:effective,failed_head_sha:grant.failed_head_sha,build_dispatched_event_sha256:dispatchEvent,canonical_branch:"codex/own-capital-sustainable-return",installed_runtime_sha:effective,event_sha256:bindingEvent};

test("effective-base provider scope is rejected before push",async()=>{
  let pushes=0;
  const adapter:CandidateExecutionAdapter={
    prepare:()=>({worktree:"C:/owner",starting_head:synchronized}),
    invokeProvider:async()=>({executor_role:"codex_control_plane",builder_backend:"opencode_ollama",builder_model:"ollama-cloud/kimi-k2.7-code",builder_session:"session",provider_session:"provider",base_sha:synchronized,head_sha:head,branch:spec.work_branch!}),
    changedPaths:(_worktree,base)=>base===synchronized?["docs/fix.md"]:["trading/forbidden.ts"],
    runDeclaredTests:()=>{},diffCheck:()=>{},commit:()=>head,push:()=>{pushes++;},remoteHead:()=>head,
    existingDraftPr:()=>undefined,createDraftPr:()=>1,bindPrToIssue:()=>{},
  };
  await assert.rejects(()=>new CandidateExecutionKernel(adapter).publish({repository:spec.repository,front_id:spec.front_id!,roadmap_item_id:spec.roadmap_item_id,issue:1,work_branch:spec.work_branch!,expected_base_sha:effective,starting_head_sha:synchronized,effective_base_sha:effective,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,test_commands:spec.test_commands,provider_request:{prompt:"test",executor_role:"codex_control_plane"},publication_receipt:{kind:"OWNER_AUTHORIZED_PAYLOAD_REPAIR",render:()=>"receipt"}} as any),/effective base|path/);
  assert.equal(pushes,0);
});

test("uncommitted provider correction survives equal effective and synchronized trees",async()=>{
  const repo=mkdtempSync(join(tmpdir(),"owner-candidate-paths-"));
  const git=(args:string[])=>execFileSync("git",args,{cwd:repo,encoding:"utf8"}).trim();
  git(["init"]);git(["config","user.name","test"]);git(["config","user.email","test@example.invalid"]);
  mkdirSync(join(repo,"docs"));writeFileSync(join(repo,"docs","seed.md"),"seed\n");git(["add","."]);git(["commit","-m","effective"]);const equalEffective=git(["rev-parse","HEAD"]);
  git(["commit","--allow-empty","-m","synchronized"]);const equalSynchronized=git(["rev-parse","HEAD"]);
  writeFileSync(join(repo,"docs","fix.md"),"fix\n");
  let published="",pushes=0;
  const adapter:CandidateExecutionAdapter={
    prepare:()=>({worktree:repo,starting_head:equalSynchronized}),
    invokeProvider:async()=>({executor_role:"codex_control_plane",builder_backend:"opencode_ollama",builder_model:"ollama-cloud/kimi-k2.7-code",builder_session:"session",provider_session:"provider",base_sha:equalSynchronized,head_sha:equalSynchronized,branch:spec.work_branch!}),
    changedPaths:(_worktree,base,providerHead)=>ownerRepairCandidatePaths(repo,base,providerHead,equalSynchronized),
    runDeclaredTests:()=>{},diffCheck:()=>{},commit:(_worktree,receipt,paths)=>{git(["add","--",...paths]);git(["commit","-m",receipt]);return git(["rev-parse","HEAD"]);},push:(_attempt,head)=>{pushes++;published=head;},remoteHead:()=>published,
    existingDraftPr:()=>undefined,createDraftPr:()=>1,bindPrToIssue:()=>{},
  };
  const result=await new CandidateExecutionKernel(adapter).publish({repository:spec.repository,front_id:spec.front_id!,roadmap_item_id:spec.roadmap_item_id,issue:1,work_branch:spec.work_branch!,expected_base_sha:equalEffective,starting_head_sha:equalSynchronized,effective_base_sha:equalEffective,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,test_commands:spec.test_commands,provider_request:{prompt:"test",executor_role:"codex_control_plane"},publication_receipt:{kind:"OWNER_AUTHORIZED_PAYLOAD_REPAIR",render:()=>"receipt"}} as any);
  assert.deepEqual(result.changed_paths,["docs/fix.md"]);assert.equal(pushes,1);
});

test("a committed exact candidate retries publication without reinvoking the provider",async()=>{
  let invokes=0,pushes=0;
  const adapter:CandidateExecutionAdapter={
    prepare:()=>({worktree:"C:/owner",starting_head:synchronized}),
    recoverCommittedCandidate:()=>({head_sha:head,provider:{executor_role:"codex_control_plane",builder_backend:"opencode_ollama",builder_model:"ollama-cloud/kimi-k2.7-code",builder_session:"session",provider_session:"provider",base_sha:synchronized,head_sha:head,branch:spec.work_branch!}}),
    invokeProvider:async()=>{invokes++;throw new Error("must not invoke");},changedPaths:()=>["docs/fix.md"],runDeclaredTests:()=>{},diffCheck:()=>{},commit:()=>{throw new Error("must not commit");},push:()=>{pushes++;},remoteHead:()=>head,
    existingDraftPr:()=>undefined,createDraftPr:()=>1,bindPrToIssue:()=>{},
  };
  const result=await new CandidateExecutionKernel(adapter).publish({repository:spec.repository,front_id:spec.front_id!,roadmap_item_id:spec.roadmap_item_id,issue:1,work_branch:spec.work_branch!,expected_base_sha:effective,starting_head_sha:synchronized,effective_base_sha:effective,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,test_commands:spec.test_commands,provider_request:{prompt:"test",executor_role:"codex_control_plane"},publication_receipt:{kind:"OWNER_AUTHORIZED_PAYLOAD_REPAIR",render:()=>"receipt"}} as any);
  assert.equal(result.head_sha,head);assert.equal(invokes,0);assert.equal(pushes,1);
});

test("governed builder exposes the bounded owner base synchronization API",()=>{
  const builder=new GovernedBuilder("C:/source","C:/worktrees",{} as any,()=>{});
  assert.equal(typeof (builder as any).synchronizeOwnerPayloadRepairBase,"function");
});

test("same-base synchronization retains deterministic two-parent evidence",()=>{
  const sameBase={...binding,effective_base_sha:frozen,installed_runtime_sha:frozen};
  const receipt=ownerPayloadBaseSyncReceipt(spec.front_id!,sameBase);
  assert.equal(verifyOwnerPayloadBaseSyncCommit(receipt,sameBase,synchronized,[grant.failed_head_sha,frozen]),true);
});

test("owner base sync retries create the same SHA and reject inherited forbidden payloads",()=>{
  const repo=mkdtempSync(join(tmpdir(),"owner-base-sync-"));
  const git=(args:string[],env:NodeJS.ProcessEnv={})=>execFileSync("git",args,{cwd:repo,encoding:"utf8",env:{...process.env,...env}}).trim();
  const commit=(message:string,time:number)=>{git(["add","."]);git(["commit","-m",message],{GIT_AUTHOR_NAME:"test",GIT_AUTHOR_EMAIL:"test@example.invalid",GIT_COMMITTER_NAME:"test",GIT_COMMITTER_EMAIL:"test@example.invalid",GIT_AUTHOR_DATE:`@${time} +0000`,GIT_COMMITTER_DATE:`@${time} +0000`});return git(["rev-parse","HEAD"]);};
  git(["init"]);git(["config","user.name","test"]);git(["config","user.email","test@example.invalid"]);
  writeFileSync(join(repo,"README.md"),"base\n");const base=commit("base",100);
  mkdirSync(join(repo,"docs"));writeFileSync(join(repo,"docs","owner.md"),"owner\n");const failed=commit("failed",110);
  git(["checkout","-q",base]);writeFileSync(join(repo,"canonical.md"),"effective\n");const effectiveHead=commit("effective",120);
  const tree=git(["merge-tree","--write-tree",failed,effectiveHead]);
  const runner=join(repo,"retry-sync.mjs");
  const governedBuilderUrl=pathToFileURL(join(__dirname,"../../../scripts/operator_proxy/governed_builder.ts")).href;
  const tsxLoader=pathToFileURL(join(__dirname,"../../../scripts/operator_proxy/node_modules/tsx/dist/loader.mjs")).href;
  writeFileSync(runner,`import {deterministicCommitTree} from ${JSON.stringify(governedBuilderUrl)};\nconst [repo,tree,failed,effective]=process.argv.slice(2);\nconsole.log(deterministicCommitTree(repo,tree,[failed,effective],"sync"));\n`);
  const runRetry=(author:string)=>execFileSync(process.execPath,["--import",tsxLoader,runner,repo,tree,failed,effectiveHead],{encoding:"utf8",env:{...process.env,GIT_AUTHOR_NAME:author,GIT_AUTHOR_EMAIL:`${author}@example.invalid`,GIT_COMMITTER_NAME:author,GIT_COMMITTER_EMAIL:`${author}@example.invalid`}}).trim();
  const first=runRetry("first-process");
  const retry=runRetry("second-process");
  assert.equal(first,retry);
  assert.equal(git(["show","-s","--format=%T",first]),tree);
  assert.equal(git(["show","-s","--format=%P",first]),`${failed} ${effectiveHead}`);
  assert.equal(git(["show","-s","--format=%an <%ae>|%cn <%ce>|%ct",first]),"operator-proxy <operator-proxy@ai-vault.invalid>|operator-proxy <operator-proxy@ai-vault.invalid>|121");
  assert.doesNotThrow(()=> (governedBuilder as any).validateOwnerPayloadBaseSyncScopes(repo,base,failed,effectiveHead,first,spec));
  git(["checkout","-q",base]);writeFileSync(join(repo,"trading-forbidden.ts"),"forbidden\n");const forbidden=commit("forbidden",130);
  const forbiddenTree=git(["merge-tree","--write-tree",forbidden,effectiveHead]);
  const forbiddenSync=execFileSync(process.execPath,["--import",tsxLoader,runner,repo,forbiddenTree,forbidden,effectiveHead],{encoding:"utf8"}).trim();
  assert.throws(()=> (governedBuilder as any).validateOwnerPayloadBaseSyncScopes(repo,base,forbidden,effectiveHead,forbiddenSync,spec),/scope/);
  const forbiddenBlob=execFileSync("git",["hash-object","-w","--stdin"],{cwd:repo,encoding:"utf8",input:"forbidden\n"}).trim();
  git(["read-tree",first]);git(["update-index","--add","--cacheinfo",`100644,${forbiddenBlob},trading-infrastructure.ts`]);
  const poisonedTree=git(["write-tree"]),poisonedSync=execFileSync(process.execPath,["--import",tsxLoader,runner,repo,poisonedTree,failed,effectiveHead],{encoding:"utf8"}).trim();
  assert.throws(()=> (governedBuilder as any).validateOwnerPayloadBaseSyncScopes(repo,base,failed,effectiveHead,poisonedSync,spec),/scope/);
});

test("effective owner dispatch preserves frozen authority and binds effective provenance",async()=>{
  const receipts:string[]=[];
  const adapter:CandidateExecutionAdapter={
    prepare:()=>({worktree:"C:/owner",starting_head:synchronized}),validateExistingDraftPr:()=>{},
    invokeProvider:async()=>({executor_role:"codex_control_plane",builder_backend:"codex_cli_openai",builder_model:"ollama-cloud/kimi-k2.7-code",builder_session:"session",provider_session:"provider",base_sha:synchronized,head_sha:head,branch:spec.work_branch!}),
    changedPaths:()=>["docs/fix.md"],runDeclaredTests:()=>{},diffCheck:()=>{},commit:(_worktree,receipt)=>{receipts.push(receipt);return head;},push:()=>{},remoteHead:()=>head,
    existingDraftPr:()=>({number:grant.pr,repository:spec.repository,issue:grant.issue,work_branch:spec.work_branch!,base_sha:effective,head_sha:head,is_draft:true,is_open:true,same_repository:true,non_fork:true,author_login:"cesarmanuel8102",base_ref_name:"codex/own-capital-sustainable-return",base_ref_oid:effective,head_ref_name:spec.work_branch!,head_ref_oid:head,changed_paths:["docs/fix.md"]}),createDraftPr:()=>{throw new Error("unexpected PR");},bindPrToIssue:()=>{},
  };
  const result=await dispatchOwnerAuthorizedPayloadRepair({spec,grant,issue:grant.issue,build_attempt_id:attempt,consumed_event_sha256:consumed,correction_payload:payload,publication:adapter,effective_base_binding:binding,synchronized_head_sha:synchronized} as any);
  assert.equal(result.candidate.base_sha,effective);
  assert.match(receipts[0]!,new RegExp(`OWNER_FROZEN_BASE_SHA=${frozen}`));
  assert.match(receipts[0]!,new RegExp(`OWNER_EFFECTIVE_BASE_SHA=${effective}`));
  assert.match(receipts[0]!,new RegExp(`OWNER_EFFECTIVE_BASE_BINDING_SHA256=${bindingEvent}`));
  assert.match(receipts[0]!,new RegExp(`OWNER_SYNCHRONIZED_HEAD_SHA=${synchronized}`));
  const parsed=parseOwnerPayloadRepairCommitReceipt(receipts[0]!,spec.front_id!);
  assert.equal(parsed.builder_backend,"codex_cli_openai");
  assert.deepEqual(parsed.effective_base,{frozen_base_sha:frozen,effective_base_sha:effective,binding_event_sha256:bindingEvent,synchronized_head_sha:synchronized});
});
