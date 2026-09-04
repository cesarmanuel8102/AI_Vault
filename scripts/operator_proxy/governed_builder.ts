import {execFileSync as rawExecFileSync} from "node:child_process";
import {existsSync,lstatSync,mkdirSync,readFileSync,readdirSync,realpathSync,rmSync} from "node:fs";
import {join,posix,resolve,sep} from "node:path";
import {randomUUID} from "node:crypto";
import type {LifecycleRecord,ProxySpec,OwnerAuthorizedPayloadRepairGrant,CorrectionPayloadV1} from "./types.js";
import {BuilderBackendError,ELIGIBLE_FALLBACK_FAILURES,type BuilderInput,type BuilderResult} from "./builder_backend.js";
import type {EffectAssertion,OwnerPayloadRepairTransportCapability} from "./external_effect_guard.js";
import {redactedError} from "./redaction.js";
import {routeControlPlaneBuild,routePreparedCandidateBuild} from "./builder_router.js";
import {BuilderAttemptProvenance,LEGACY_NEUTRALIZATION_TRAILER,PRIOR_UNATTESTED_HEAD_TRAILER,RESET_BASE_TRAILER,LEGACY_REBUILD_TRAILER,NEUTRALIZATION_HEAD_TRAILER,FRESH_BUILDER_HEAD_TRAILER} from "./builder_attempt_provenance.js";
import {canonicalCorrectionPayloadBytes,parseCorrectionPayloadV1} from "./correction_payload.js";
import {CandidateExecutionKernel,type CandidateExecutionAdapter,type CandidatePublicationResult,type PreparedCandidateAttempt} from "./candidate_execution.js";

export interface BuilderBus {
  findPrByBranch(branch:string):{number:number;head_sha:string}|undefined;
  remoteBranchHead(branch:string):string|undefined;
  createDraftPr(branch:string,base:string,title:string,body:string):number;
  bindPrToIssue(issue:number,pr:number):void;
  repairPrompt(issue:number):string;
  prIdentity(pr:number):any;
}
export interface OwnerPayloadRepairBuilderInput {front_id:string;work_branch:string;failed_head_sha:string;correction_payload:CorrectionPayloadV1;provenance:{authorization_id:string;grant_key:string;build_attempt_id:string;consumed_event_sha256:string}}
export interface OwnerPayloadRepairTransportRequest extends OwnerPayloadRepairBuilderInput {repository:string;roadmap_id:string;roadmap_item_id:string;issue:number;pr:number;canonical_base_sha:string;idempotency_key:string;prompt:string}
export interface OwnerPayloadRepairDispatchContext {spec:ProxySpec;grant:OwnerAuthorizedPayloadRepairGrant;issue:number;build_attempt_id:string;consumed_event_sha256:string;correction_payload:CorrectionPayloadV1;publication:CandidateExecutionAdapter}
export interface OwnerPayloadRepairCandidate {candidate:CandidatePublicationResult;provenance:OwnerPayloadRepairBuilderInput["provenance"]}

function exact64(value:string){return /^[0-9a-f]{64}$/.test(value);}
function exceptionalPathDenied(path:string){return path==="scripts/operator_proxy"||path.startsWith("scripts/operator_proxy/")||path.endsWith("/")&&("scripts/operator_proxy".startsWith(path)||".github".startsWith(path))||path===".github"||path.startsWith(".github/");}
function validateOwnerPayloadRepairDispatch(context:OwnerPayloadRepairDispatchContext):OwnerPayloadRepairBuilderInput {
  const {spec,grant,issue,build_attempt_id,consumed_event_sha256,correction_payload}=context;
  if(issue!==grant.issue)throw new Error("owner repair issue invalid");
  if(!spec.front_id||!spec.work_branch||spec.repository!==grant.repository||spec.authorization_id!==grant.authorization_id||spec.roadmap_id!==grant.roadmap_id||spec.roadmap_item_id!==grant.roadmap_item_id||spec.front_id!==grant.front_id||spec.work_branch!==grant.work_branch||spec.expected_base_sha!==grant.canonical_base_sha||!exact64(grant.grant_key)||!exact64(build_attempt_id)||!exact64(consumed_event_sha256))throw new Error("owner repair dispatch identity invalid");
  if(spec.allowed_paths.some(exceptionalPathDenied)||spec.forbidden_paths.some(path=>path==="scripts/operator_proxy/authority"||path.startsWith("scripts/operator_proxy/authority/")))throw new Error("owner repair path scope invalid");
  const parsed=parseCorrectionPayloadV1(correction_payload);
  if(parsed.sha256!==grant.correction_payload_sha256)throw new Error("owner repair correction payload invalid");
  return ownerPayloadRepairBuilderInput(grant,{build_attempt_id,consumed_event_sha256,correction_payload:parsed.payload});
}
function ownerPayloadRepairPrompt(request:OwnerPayloadRepairTransportRequest):string {
  return [
    "Execute one governed owner-authorized payload repair.",
    `REPOSITORY=${request.repository}`,
    `ROADMAP_ID=${request.roadmap_id}`,
    `ROADMAP_ITEM_ID=${request.roadmap_item_id}`,
    `FRONT_ID=${request.front_id}`,
    `ISSUE=${request.issue}`,
    `PR=${request.pr}`,
    `WORK_BRANCH=${request.work_branch}`,
    `CANONICAL_BASE_SHA=${request.canonical_base_sha}`,
    `FAILED_HEAD_SHA=${request.failed_head_sha}`,
    `AUTHORIZATION_ID=${request.provenance.authorization_id}`,
    `GRANT_KEY=${request.provenance.grant_key}`,
    `BUILD_ATTEMPT_ID=${request.provenance.build_attempt_id}`,
    `CONSUMED_EVENT_SHA256=${request.provenance.consumed_event_sha256}`,
    "Apply only this typed correction payload and preserve its invariants:",
    canonicalCorrectionPayloadBytes(request.correction_payload).trimEnd(),
  ].join("\n");
}

function ownerPayloadRepairReceipt(request:OwnerPayloadRepairTransportRequest,provider:{builder_backend:string;builder_model:string;provider_session:string;fallback_reason?:string}):string {
  return [`fix(control-plane): owner payload repair ${request.front_id}`,"",`OWNER_AUTHORIZATION_ID=${request.provenance.authorization_id}`,`OWNER_GRANT_KEY=${request.provenance.grant_key}`,`OWNER_BUILD_ATTEMPT_ID=${request.provenance.build_attempt_id}`,`OWNER_CONSUMED_EVENT_SHA256=${request.provenance.consumed_event_sha256}`,`BUILDER_BACKEND=${provider.builder_backend}`,`BUILDER_MODEL=${provider.builder_model}`,`PROVIDER_SESSION=${provider.provider_session}`,...(provider.fallback_reason?[`FALLBACK_REASON=${provider.fallback_reason}`]:[])].join("\n");
}

/** Validates the immutable receipt written by the exceptional publication path. */
export function parseOwnerPayloadRepairCommitReceipt(message:string,frontId:string):{provenance:OwnerPayloadRepairBuilderInput["provenance"];builder_session:string;builder_model:string}{
  const lines=message.replace(/\r\n/g,"\n").trimEnd().split("\n");
  if(lines[0]!==`fix(control-plane): owner payload repair ${frontId}`)throw new Error("owner repair commit receipt invalid");
  const value=(name:string)=>{const values=lines.filter(line=>line.startsWith(`${name}=`)).map(line=>line.slice(name.length+1));if(values.length!==1)return undefined;return values[0];};
  const authorization_id=value("OWNER_AUTHORIZATION_ID"),grant_key=value("OWNER_GRANT_KEY"),build_attempt_id=value("OWNER_BUILD_ATTEMPT_ID"),consumed_event_sha256=value("OWNER_CONSUMED_EVENT_SHA256"),builder_backend=value("BUILDER_BACKEND"),builder_model=value("BUILDER_MODEL"),provider_session=value("PROVIDER_SESSION"),fallback=lines.filter(line=>line.startsWith("FALLBACK_REASON="));
  const allowedLines=new Set([lines[0],"",`OWNER_AUTHORIZATION_ID=${authorization_id}`,`OWNER_GRANT_KEY=${grant_key}`,`OWNER_BUILD_ATTEMPT_ID=${build_attempt_id}`,`OWNER_CONSUMED_EVENT_SHA256=${consumed_event_sha256}`,`BUILDER_BACKEND=${builder_backend}`,`BUILDER_MODEL=${builder_model}`,`PROVIDER_SESSION=${provider_session}`,...fallback]);
  const allowedBackends=new Set(["codex_cli_openai","opencode_github_copilot","opencode_ollama"]);
  if(!authorization_id||!exact64(grant_key??"")||!exact64(build_attempt_id??"")||!exact64(consumed_event_sha256??"")||!builder_backend||!allowedBackends.has(builder_backend)||!builder_model||!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(builder_model)||!provider_session||!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(provider_session)||fallback.length>1||fallback.length===1&&!ELIGIBLE_FALLBACK_FAILURES.has(fallback[0]!.slice("FALLBACK_REASON=".length))||!lines.every(line=>allowedLines.has(line)))throw new Error("owner repair commit receipt invalid");
  return {provenance:{authorization_id,grant_key:grant_key!,build_attempt_id:build_attempt_id!,consumed_event_sha256:consumed_event_sha256!},builder_session:provider_session,builder_model:builder_model!};
}
/** Dispatches the one logical exceptional attempt. Receipt and lifecycle mutations are owned by Tasks 6/8. */
export async function dispatchOwnerAuthorizedPayloadRepair(context:OwnerPayloadRepairDispatchContext):Promise<OwnerPayloadRepairCandidate> {
  const input=validateOwnerPayloadRepairDispatch(context);
  const request:OwnerPayloadRepairTransportRequest={...input,repository:context.grant.repository,roadmap_id:context.grant.roadmap_id,roadmap_item_id:context.grant.roadmap_item_id,issue:context.grant.issue,pr:context.grant.pr,canonical_base_sha:context.grant.canonical_base_sha,idempotency_key:input.provenance.build_attempt_id,prompt:""};
  request.prompt=ownerPayloadRepairPrompt(request);
  if(context.spec.executor!=="codex_control_plane")throw new Error("owner repair executor invalid");
  const candidate=await new CandidateExecutionKernel(context.publication).publish({repository:request.repository,front_id:request.front_id,roadmap_item_id:request.roadmap_item_id,issue:request.issue,work_branch:request.work_branch,expected_base_sha:request.canonical_base_sha,starting_head_sha:request.failed_head_sha,observed_head_sha:request.failed_head_sha,allowed_paths:context.spec.allowed_paths,forbidden_paths:context.spec.forbidden_paths,test_commands:context.spec.test_commands,provider_request:{prompt:request.prompt,executor_role:"codex_control_plane"},provider_idempotency_key:request.idempotency_key,publication_receipt:{kind:"OWNER_AUTHORIZED_PAYLOAD_REPAIR",render:provider=>ownerPayloadRepairReceipt(request,provider)},require_existing_draft_pr:true});
  if(candidate.base_sha!==request.canonical_base_sha||candidate.work_branch!==request.work_branch||! /^[0-9a-f]{40}$/.test(candidate.head_sha)||candidate.head_sha===request.failed_head_sha)throw new Error("owner repair candidate invalid");
  return {candidate,provenance:input.provenance};
}
/** Constructs the only exceptional-builder payload; raw owner comment text is never accepted. */
export function ownerPayloadRepairBuilderInput(grant:OwnerAuthorizedPayloadRepairGrant,input:{build_attempt_id:string;consumed_event_sha256:string;correction_payload:CorrectionPayloadV1}):OwnerPayloadRepairBuilderInput {
  const parsed=parseCorrectionPayloadV1(input.correction_payload);
  if(!exact64(input.build_attempt_id)||!exact64(input.consumed_event_sha256)||parsed.sha256!==grant.correction_payload_sha256)throw new Error("owner repair consumed provenance invalid");
  return {front_id:grant.front_id,work_branch:grant.work_branch,failed_head_sha:grant.failed_head_sha,correction_payload:parsed.payload,provenance:{authorization_id:grant.authorization_id,grant_key:grant.grant_key,build_attempt_id:input.build_attempt_id,consumed_event_sha256:input.consumed_event_sha256}};
}

function native(file:string,args:string[],options:any={}){try{return rawExecFileSync(file,args,{...options,encoding:"utf8",stdio:"pipe"});}catch(error){throw new Error(redactedError(error));}}
const git=(repo:string,args:string[])=>native(process.env.GIT_PATH??"git",["-C",repo,...args],{encoding:"utf8",timeout:120000,windowsHide:true}).trim();
function ensureCommit(repo:string,sha:string){
  if(!/^[a-f0-9]{40}$/.test(sha))throw new Error("builder base commit identity invalid");
  try{git(repo,["cat-file","-e",`${sha}^{commit}`]);return;}catch{}
  try{git(repo,["fetch","--no-tags","--no-write-fetch-head","origin",sha]);git(repo,["cat-file","-e",`${sha}^{commit}`]);}
  catch{throw new Error("builder base commit unavailable");}
}
const allowed=(path:string,spec:ProxySpec)=>spec.allowed_paths.some(p=>p.endsWith("/")?path.startsWith(p):path===p)&&!spec.forbidden_paths.some(p=>path===p||path.startsWith(p.endsWith("/")?p:`${p}/`));
function changed(repo:string){const tracked=git(repo,["diff","--name-only","HEAD"]);const staged=git(repo,["diff","--cached","--name-only"]);const untracked=git(repo,["ls-files","--others","--exclude-standard"]);return [...new Set([tracked,staged,untracked].flatMap(x=>x?x.split(/\r?\n/):[]).filter(Boolean))].sort();}
function committed(repo:string,base:string){const output=git(repo,["diff","--name-only",`${base}..HEAD`]);return output?output.split(/\r?\n/).filter(Boolean).sort():[];}
function validateFiles(files:string[],spec:ProxySpec){if(files.length===0)throw new Error("builder produced no changes");if(!files.every(path=>allowed(path,spec)))throw new Error("builder changed path outside scope");}
function builderReceiptMessage(front:string,result:Pick<BuilderResult,"builder_backend"|"builder_model"|"provider_session"|"fallback_reason">){return `feat(control-plane): complete ${front}\n\nBUILDER_BACKEND=${result.builder_backend}\nBUILDER_MODEL=${result.builder_model}\nPROVIDER_SESSION=${result.provider_session}${result.fallback_reason?`\nFALLBACK_REASON=${result.fallback_reason}`:""}`;}
function validateBuilderReceipt(repo:string,head:string,front:string){
  const lines=git(repo,["show","-s","--format=%B",head]).replace(/\r\n/g,"\n").trimEnd().split("\n");
  if(lines[0]!==`feat(control-plane): complete ${front}`)throw new Error("recovered builder commit subject mismatch");
  const values=(prefix:string)=>lines.filter(line=>line.startsWith(prefix)).map(line=>line.slice(prefix.length));
  const backend=values("BUILDER_BACKEND="),model=values("BUILDER_MODEL="),provider=values("PROVIDER_SESSION="),fallback=values("FALLBACK_REASON=");
  if(backend.length!==1||!["codex_cli_openai","opencode_github_copilot","opencode_ollama"].includes(backend[0])||model.length!==1||!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(model[0])||provider.length!==1||!/^[a-z0-9][a-z0-9._:/-]{2,127}$/.test(provider[0])||fallback.length>1||fallback.length===1&&!ELIGIBLE_FALLBACK_FAILURES.has(fallback[0]))throw new Error("recovered builder receipt invalid");
}
export function synchronizedRepairReceipt(repo:string,head:string,front:string){
  let current=head;const visited=new Set<string>();
  for(let depth=0;depth<64;depth++){
    if(visited.has(current))throw new BuilderBackendError("recovered repair synchronization cycle detected","RECOVERY_SYNC_CHAIN_INVALID");
    visited.add(current);
    const subject=git(repo,["show","-s","--format=%s",current]);
    if(subject!==`chore(control-plane): synchronize ${front} base`){validateBuilderReceipt(repo,current,front);return current;}
    const parents=git(repo,["rev-list","--parents","-n","1",current]).split(/\s+/);
    if(parents.length!==3||parents[0]!==current)throw new BuilderBackendError("recovered repair synchronization invalid","RECOVERY_SYNC_CHAIN_INVALID");
    current=parents[1];
  }
  throw new BuilderBackendError("recovered repair synchronization depth exceeded","RECOVERY_SYNC_DEPTH_EXCEEDED");
}
function validatePublishedPr(spec:ProxySpec,existing:{number:number;head_sha:string},identity:any,head:string,files:string[]){
  const prFiles=(identity.files??[]).map((item:any)=>String(item.path)).sort();
  if(existing.head_sha!==head||identity.author?.login!=="cesarmanuel8102"||identity.baseRefName!=="codex/own-capital-sustainable-return"||identity.baseRefOid!==spec.expected_base_sha||identity.headRefName!==spec.work_branch||identity.headRefOid!==head||identity.headRepository?.nameWithOwner!=="cesarmanuel8102/AI_Vault"||identity.isCrossRepository!==false||identity.isDraft!==true||identity.state!=="OPEN"||JSON.stringify(prFiles)!==JSON.stringify(files))throw new Error("published builder PR identity invalid");
}
export function validateAgentSyncChain(repo:string,rootHead:string,remoteHead:string,expectedBase:string,files:string[],front:string){let current=remoteHead,depth=0;const bases:string[]=[];while(current!==rootHead){if(++depth>8)throw new Error("blocked CI Agent Loop synchronization chain too deep");const parts=git(repo,["rev-list","--parents","-n","1",current]).split(/\s+/);if(parts.length!==3||parts[0]!==current||git(repo,["show","-s","--format=%s",current])!==`chore(control-plane): synchronize ${front} base`)throw new Error("blocked CI Agent Loop synchronization chain invalid");try{git(repo,["merge-base","--is-ancestor",expectedBase,parts[2]]);}catch{try{git(repo,["merge-base","--is-ancestor",parts[2],expectedBase]);}catch{throw new Error("blocked CI Agent Loop synchronization base invalid");}}const candidate=git(repo,["diff","--name-only",`${parts[2]}..${current}`]).split(/\r?\n/).filter(Boolean).sort();if(JSON.stringify(candidate)!==JSON.stringify(files)||git(repo,["diff","--name-only",`${rootHead}..${current}`,"--",...files]))throw new Error("blocked CI Agent Loop synchronized candidate changed");bases.push(parts[2]);current=parts[1];}return bases;}
export function parseTestCommand(command:string):[string,string[]]{if(/[;&|><`$]/.test(command))throw new Error("test command contains shell syntax");const argv=command.match(/(?:[^\s"]+|"[^"]*")+/g)?.map(x=>x.startsWith('"')?x.slice(1,-1):x)??[];const [file,...args]=argv;const exe=(file??"").toLowerCase();const safeArg=(x:string)=>!x.includes("..")&&!/^[A-Za-z]:[\\/]/.test(x)&&!x.includes("\\");if(!args.every(safeArg))throw new Error("test argument path denied");if(["git","git.exe"].includes(exe)&&args.length===2&&args[0]==="diff"&&args[1]==="--check")return [file,args];if(["npm","npm.cmd"].includes(exe)&&(args.length===1&&args[0]==="test"||args.length===2&&args[0]==="run"&&/^[a-z0-9:_-]+$/i.test(args[1])))return [file,args];if(["python","python.exe"].includes(exe)){if(args[0]==="-m"&&args[1]==="pytest"&&args.slice(2).every(x=>x.startsWith("tests/")||["-q","-v","--maxfail=1"].includes(x)))return [file,args];if(/^tests\/[A-Za-z0-9_./-]+\.py$/.test(args[0]??"")&&args.slice(1).every(x=>/^[A-Za-z0-9_.:/=-]+$/.test(x)))return [file,args];}if(["pwsh","pwsh.exe","powershell","powershell.exe"].includes(exe)){const index=args.findIndex(x=>x.toLowerCase()==="-file");if(index>=0&&args.slice(0,index).every(x=>["-NoProfile","-NonInteractive"].includes(x))&&/^tests\/[A-Za-z0-9_./-]+\.ps1$/.test(args[index+1]??"")&&args.slice(index+2).every(x=>/^[A-Za-z0-9_.:/=-]+$/.test(x)))return [file,args];}throw new Error("test command denied");}
export function expandDeclaredTestArgs(repo:string,args:string[]){
  const root=realpathSync(repo),rootPrefix=`${root}${sep}`.toLowerCase();
  return args.flatMap(arg=>{
    if(arg.includes("?"))throw new Error("declared test glob denied");
    if(!arg.includes("*"))return [arg];
    if(!arg.startsWith("tests/")||arg.includes("**")||(arg.match(/\*/g)?.length??0)!==1)throw new Error("declared test glob denied");
    const directory=posix.dirname(arg),pattern=posix.basename(arg);
    if(directory.includes("*")||!/^[A-Za-z0-9_.-]*\*[A-Za-z0-9_.-]*\.py$/.test(pattern))throw new Error("declared test glob denied");
    const absoluteDirectory=resolve(root,directory),canonicalDirectory=realpathSync(absoluteDirectory);
    if(!canonicalDirectory.toLowerCase().startsWith(rootPrefix))throw new Error("declared test glob escaped repository");
    const expression=new RegExp(`^${pattern.split("*").map(part=>part.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")).join(".*")}$`);
    const matches=readdirSync(canonicalDirectory,{withFileTypes:true}).filter(entry=>entry.isFile()&&expression.test(entry.name)).map(entry=>`${directory}/${entry.name}`).sort();
    if(matches.length===0)throw new Error("declared test glob matched no files");
    return matches;
  });
}
export function runDeclaredTests(repo:string,commands:string[]){for(const command of commands){const [file,args]=parseTestCommand(command);native(file,expandDeclaredTestArgs(repo,args),{cwd:repo,stdio:"inherit",timeout:900000,windowsHide:true});}}
export function builderPrompt(spec:ProxySpec,repairCycle:number,repair=""){
  const manifestContract=spec.allowed_paths.includes("docs/roadmap/BRAIN_101_MANIFEST.json")?"Any AUTHORIZED_ACTIVE roadmap item must satisfy the current sequencer contract exactly: executor is agent_loop or codex_control_plane; agent_loop requires a matching agent/* work branch, test_profile, and max_executor_cycles from 1 through 3; every active item requires complete valid closeout metadata. Do not invent executor aliases.":"";
  return [`Build governed front ${spec.front_id}.`,`Objective: ${spec.objective}`,`Repair cycle: ${repairCycle}.`,repair?`Correct only these independent-review findings:\n${repair}`:"",`Allowed paths only: ${spec.allowed_paths.join(", ")}.`,`Forbidden paths: ${spec.forbidden_paths.join(", ")}.`,`Acceptance: ${spec.acceptance.join(" | ")}.`,manifestContract,`Do not commit, push, open a PR, merge, deploy, or inspect paths outside this worktree.`,`After edits and checks, run git rev-parse HEAD and include exactly one final receipt line HEAD_SHA=<the exact 40-character lowercase result>. The runner, not you, commits the validated changes.`].filter(Boolean).join("\n");
}

function isLegacyUnattestedPr(spec:ProxySpec,existing:{number:number;head_sha:string}|undefined,bus:BuilderBus,worktree:string,observedHead:string):boolean{
  if(!existing||!spec.work_branch||existing.head_sha===spec.expected_base_sha||observedHead!==existing.head_sha)return false;
  const remote=bus.remoteBranchHead(spec.work_branch);if(remote!==existing.head_sha)return false;
  if(observedHead===spec.expected_base_sha)return false;
  try{git(worktree,["merge-base","--is-ancestor",spec.expected_base_sha!,observedHead]);}catch{return false;}
  let receiptValid=false;try{validateBuilderReceipt(worktree,observedHead,spec.front_id!);receiptValid=true;}catch{receiptValid=false;}
  if(receiptValid)return false;
  const subject=git(worktree,["show","-s","--format=%s",observedHead]);
  if(subject===`chore(control-plane): synchronize ${spec.front_id!} base`)return false;
  const files=committed(worktree,spec.expected_base_sha!);
  try{validateFiles(files,spec);}catch{return false;}
  return true;
}
function treeOf(repo:string,sha:string):string{return git(repo,["rev-parse",`${sha}^{tree}`]);}
function commitTree(repo:string,tree:string,parents:string[],message:string):string{
  const args=["commit-tree",tree];for(const p of parents)args.push("-p",p);args.push("-m",message);const sha=git(repo,args);if(!/^[0-9a-f]{40}$/.test(sha))throw new Error("commit-tree produced invalid sha");return sha;
}
function neutralizationMessage(front:string,legacyHead:string,baseSha:string){return `chore(control-plane): neutralize ${front} legacy baseline\n\n${LEGACY_NEUTRALIZATION_TRAILER}=true\n${PRIOR_UNATTESTED_HEAD_TRAILER}=${legacyHead}\n${RESET_BASE_TRAILER}=${baseSha}`;}
function legacyBridgeMessage(front:string,neutralizationHead:string,freshHead:string,baseSha:string){return `feat(control-plane): complete ${front}\n\n${LEGACY_REBUILD_TRAILER}=true\n${NEUTRALIZATION_HEAD_TRAILER}=${neutralizationHead}\n${FRESH_BUILDER_HEAD_TRAILER}=${freshHead}\n${RESET_BASE_TRAILER}=${baseSha}`;}
function diffEmpty(repo:string,a:string,b:string):boolean{try{git(repo,["diff","--quiet",`${a}..${b}`]);return true;}catch{return false;}}
const synchronizationMergeability=(value:unknown)=>value==="MERGEABLE"||value==="UNKNOWN";
export function waitForRemoteBranchHead(bus:BuilderBus,branch:string,expected:string):void{
  for(let attempt=0;attempt<5;attempt++){
    if(bus.remoteBranchHead(branch)===expected)return;
    if(attempt<4)Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,1000);
  }
  throw new Error("blocked CI branch push readback failed");
}

export class GovernedBuilder {
  constructor(readonly sourceRepo:string,readonly worktreeRoot:string,readonly bus:BuilderBus,readonly assertEffect:EffectAssertion,readonly codex=process.env.CODEX_PATH??"codex"){}
  /**
   * Builds the transport adapter for the single Owner-authorized attempt.
   * The caller owns receipt/lifecycle semantics; this adapter only publishes.
   */
  ownerPayloadRepairPublicationAdapter(spec:ProxySpec, grant:OwnerAuthorizedPayloadRepairGrant, capability:OwnerPayloadRepairTransportCapability, assertCapability:()=>void):CandidateExecutionAdapter {
    if(!spec.front_id||!spec.work_branch||grant.front_id!==spec.front_id||grant.work_branch!==spec.work_branch||grant.canonical_base_sha!==spec.expected_base_sha||grant.issue<1||grant.pr<1)throw new Error("owner repair publication identity invalid");
    ensureCommit(this.sourceRepo,spec.expected_base_sha);ensureCommit(this.sourceRepo,grant.failed_head_sha);
    try{git(this.sourceRepo,["merge-base","--is-ancestor",spec.expected_base_sha,grant.failed_head_sha]);}catch{throw new Error("owner repair failed head lineage invalid");}
    mkdirSync(this.worktreeRoot,{recursive:true});const root=realpathSync(this.worktreeRoot);
    if(lstatSync(root).isSymbolicLink())throw new Error("owner repair worktree root symlink denied");
    const worktree=resolve(root,`${spec.front_id}-owner-${capability.build_attempt_id.slice(0,12)}`);
    if(!worktree.startsWith(`${root}\\`)&&!worktree.startsWith(`${root}/`))throw new Error("owner repair worktree escaped root");
    if(!existsSync(worktree)){
      assertCapability();this.assertEffect("branch_create",{issue:grant.issue});
      native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","--detach",worktree,grant.failed_head_sha],{stdio:"inherit",timeout:120000,windowsHide:true});
    }
    if(realpathSync(worktree).toLowerCase()!==worktree.toLowerCase()||git(worktree,["branch","--show-current"])!==""||git(worktree,["rev-parse","HEAD"])!==grant.failed_head_sha||git(worktree,["status","--porcelain","--untracked-files=all"]))throw new Error("owner repair worktree state invalid");
    const assert = (effect:"builder_execute"|"commit_create"|"push"|"issue_modify") => {assertCapability();this.assertEffect(effect,{issue:grant.issue,pr:grant.pr});};
    return {
      prepare:()=>({worktree,starting_head:grant.failed_head_sha}),
      validateExistingDraftPr:()=>{const identity=this.bus.prIdentity(grant.pr),files=(identity.files??[]).map((file:any)=>String(file.path));if(identity.author?.login!==spec.repository.split("/",1)[0]||identity.baseRefName!=="codex/own-capital-sustainable-return"||identity.baseRefOid!==grant.canonical_base_sha||identity.headRefName!==spec.work_branch||identity.headRefOid!==grant.failed_head_sha||identity.headRepository?.nameWithOwner!==spec.repository||identity.isCrossRepository!==false||identity.isDraft!==true||identity.state!=="OPEN"||files.length===0||!files.every((path:string)=>allowed(path,spec))||this.bus.remoteBranchHead(spec.work_branch!)!==grant.failed_head_sha)throw new Error("owner repair existing Draft PR identity invalid");},
      invokeProvider:async request=>{assert("builder_execute");return routePreparedCandidateBuild({repository:spec.repository,worktree,front_id:spec.front_id!,issue:grant.issue,base_sha:grant.failed_head_sha,work_branch:spec.work_branch!,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,acceptance:spec.acceptance,test_commands:spec.test_commands,risk:spec.risk,deployment_mode:spec.deployment_mode??"NO_DEPLOY",prompt:request.prompt,session:`owner-${capability.build_attempt_id}`,logical_attempt_id:capability.build_attempt_id});},
      changedPaths:(_prepared,base,head)=>head===base?changed(worktree):committed(worktree,base),
      runDeclaredTests:()=>runDeclaredTests(worktree,spec.test_commands),
      diffCheck:(_prepared,base,head)=>native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",...(head===base?[]:[`${base}..${head}`])],{stdio:"inherit",timeout:120000,windowsHide:true}),
      commit:(_prepared,receipt,paths,provider)=>{assert("commit_create");if(provider.head_sha!==grant.failed_head_sha)native(process.env.GIT_PATH??"git",["-C",worktree,"commit","--allow-empty","-m",receipt],{stdio:"inherit",timeout:120000,windowsHide:true});else{native(process.env.GIT_PATH??"git",["-C",worktree,"add","--",...paths],{stdio:"inherit",timeout:120000,windowsHide:true});native(process.env.GIT_PATH??"git",["-C",worktree,"commit","-m",receipt],{stdio:"inherit",timeout:120000,windowsHide:true});}const head=git(worktree,["rev-parse","HEAD"]);if(head===grant.failed_head_sha)throw new Error("owner repair produced no changes");return head;},
      push:(_attempt,head)=>{assert("push");native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`HEAD:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});},
      remoteHead:branch=>this.readPublishedBranchHead(worktree,branch),
      existingDraftPr:(_attempt,_head,_paths)=>{const identity=this.bus.prIdentity(grant.pr),files=(identity.files??[]).map((file:any)=>String(file.path));return {number:grant.pr,repository:identity.headRepository?.nameWithOwner,issue:grant.issue,work_branch:identity.headRefName,base_sha:identity.baseRefOid,head_sha:identity.headRefOid,is_draft:identity.isDraft===true,is_open:identity.state==="OPEN",same_repository:identity.headRepository?.nameWithOwner===spec.repository,non_fork:identity.isCrossRepository===false,author_login:identity.author?.login,base_ref_name:identity.baseRefName,base_ref_oid:identity.baseRefOid,head_ref_name:identity.headRefName,head_ref_oid:identity.headRefOid,changed_paths:files};},
      createDraftPr:()=>{throw new Error("owner repair requires existing Draft PR");},
      bindPrToIssue:(issue,pr)=>{if(issue!==grant.issue||pr!==grant.pr)throw new Error("owner repair Issue binding invalid");assert("issue_modify");this.bus.bindPrToIssue(issue,pr);},
    };
  }
  synchronizeBlockedCiBase(spec:ProxySpec,state:LifecycleRecord){
    if(state.state!=="BLOCKED"||state.last_error!=="CI_FAILED"||!state.issue||!state.pr||!state.head_sha||!state.builder_session||!Number.isInteger(state.repair_cycles)||state.repair_cycles<0||state.repair_cycles>2||state.reviewer_session||state.decision_id||!spec.work_branch||state.base_sha===spec.expected_base_sha)throw new Error("blocked CI branch synchronization denied");
    const pr=this.bus.prIdentity(state.pr),files=(pr.files??[]).map((x:any)=>String(x.path)).sort();
    // GitHub may expose either the PR's original base OID or the advanced target OID.
    // This operation only synchronizes the trusted Draft branch; merge dispatch still requires MERGEABLE.
    if(pr.author?.login!=="cesarmanuel8102"||pr.baseRefName!=="codex/own-capital-sustainable-return"||pr.headRefName!==spec.work_branch||pr.headRepository?.nameWithOwner!=="cesarmanuel8102/AI_Vault"||pr.isCrossRepository!==false||pr.isDraft!==true||pr.state!=="OPEN"||!synchronizationMergeability(pr.mergeable)||files.length===0||!files.every((path:string)=>allowed(path,spec)))throw new Error("blocked CI PR identity invalid");
    const remote=this.bus.remoteBranchHead(spec.work_branch);if(!remote||!/^[a-f0-9]{40}$/.test(remote)||pr.headRefOid!==remote)throw new Error("blocked CI remote branch missing or inconsistent");
    mkdirSync(this.worktreeRoot,{recursive:true});const root=realpathSync(this.worktreeRoot),historicalWorktree=resolve(root,spec.front_id!);if(!historicalWorktree.startsWith(`${root}\\`)&&!historicalWorktree.startsWith(`${root}/`))throw new Error("blocked CI worktree identity invalid");
    native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"fetch","origin","codex/own-capital-sustainable-return",spec.work_branch],{stdio:"inherit",timeout:120000,windowsHide:true});
    // A signed synchronization chain is executor-neutral evidence. Only the
    // exact synchronization receipt activates this path; ordinary candidates
    // retain the direct base contract and are never interpreted as a chain.
    const syncBases=git(this.sourceRepo,["show","-s","--format=%s",remote])===`chore(control-plane): synchronize ${spec.front_id!} base`?validateAgentSyncChain(this.sourceRepo,state.head_sha,remote,spec.expected_base_sha,files,spec.front_id!):[];if(!([state.base_sha,spec.expected_base_sha,...syncBases].includes(pr.baseRefOid)))throw new Error("blocked CI PR base identity invalid");
    // Never clean or move a historical worktree. A dirty one is forensic state, so recovery uses
    // a deterministic detached workspace keyed by the immutable remote candidate.
    let worktree=historicalWorktree;
    if(!existsSync(historicalWorktree))native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","--detach",historicalWorktree,remote],{stdio:"inherit",timeout:120000,windowsHide:true});
    else if(realpathSync(historicalWorktree).toLowerCase()!==historicalWorktree.toLowerCase()||git(historicalWorktree,["status","--porcelain","--untracked-files=all"])){
      const recoveryWorktree=resolve(root,`${spec.front_id}-blocked-ci-recovery-${remote.slice(0,12)}`);
      if(!recoveryWorktree.startsWith(`${root}\\`)&&!recoveryWorktree.startsWith(`${root}/`))throw new Error("blocked CI recovery worktree identity invalid");
      if(!existsSync(recoveryWorktree))native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","--detach",recoveryWorktree,remote],{stdio:"inherit",timeout:120000,windowsHide:true});
      if(realpathSync(recoveryWorktree).toLowerCase()!==recoveryWorktree.toLowerCase()||git(recoveryWorktree,["status","--porcelain","--untracked-files=all"])||git(recoveryWorktree,["branch","--show-current"])!=="")throw new Error("blocked CI recovery worktree state invalid");
      worktree=recoveryWorktree;
    }
    if(realpathSync(worktree).toLowerCase()!==worktree.toLowerCase()||git(worktree,["status","--porcelain","--untracked-files=all"]))throw new Error("blocked CI worktree state invalid");const localHeadBefore=git(worktree,["rev-parse","HEAD"]),localBranch=git(worktree,["branch","--show-current"]);
    if(localBranch!==spec.work_branch&&(localBranch!==""||!([state.head_sha,remote].includes(localHeadBefore))))throw new Error("blocked CI worktree state invalid");
    try{git(worktree,["merge-base","--is-ancestor",state.base_sha,spec.expected_base_sha]);git(worktree,["merge-base","--is-ancestor",state.base_sha,state.head_sha]);}catch{throw new Error("blocked CI ancestry invalid");}
    let unpublishedRepair:string|undefined;
    if(localHeadBefore===state.head_sha){const priorFiles=committed(worktree,state.base_sha);validateFiles(priorFiles,spec);if(spec.executor==="agent_loop"&&JSON.stringify(priorFiles)!==JSON.stringify(files))throw new Error("blocked CI Agent Loop candidate files inconsistent");}
    else if(localHeadBefore!==remote){
      let localAhead=false;try{git(worktree,["merge-base","--is-ancestor",remote,localHeadBefore]);localAhead=true;}catch{}
      // A local head strictly behind the remote branch is not drift: the
      // published candidate advanced and the worktree fast-forwards later.
      if(!localAhead){let remoteAhead=false;try{git(worktree,["merge-base","--is-ancestor",localHeadBefore,remote]);remoteAhead=true;}catch{}
        if(!remoteAhead)throw new Error("blocked CI local branch drift");}
      else{validateBuilderReceipt(worktree,localHeadBefore,spec.front_id!);const repairFiles=committed(worktree,remote);validateFiles(repairFiles,spec);runDeclaredTests(worktree,spec.test_commands);native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",`${remote}..${localHeadBefore}`],{stdio:"inherit",timeout:120000,windowsHide:true});unpublishedRepair=localHeadBefore;}
    }
    let nextHead=remote;const remoteParents=remote===state.head_sha?[]:git(worktree,["rev-list","--parents","-n","1",remote]).split(/\s+/);
    if(unpublishedRepair||remote===state.head_sha||remoteParents[2]!==spec.expected_base_sha){
      const firstParent=unpublishedRepair??remote,tree=git(worktree,["merge-tree","--write-tree",firstParent,spec.expected_base_sha]);if(!/^[0-9a-f]{40}$/.test(tree))throw new Error("blocked CI merge tree invalid");
      nextHead=git(worktree,["commit-tree",tree,"-p",firstParent,"-p",spec.expected_base_sha,"-m",`chore(control-plane): synchronize ${spec.front_id} base`]);if(!/^[0-9a-f]{40}$/.test(nextHead))throw new Error("blocked CI merge commit invalid");
    }
    const parents=git(worktree,["rev-list","--parents","-n","1",nextHead]).split(/\s+/);if(spec.executor==="agent_loop")validateAgentSyncChain(worktree,state.head_sha,nextHead,spec.expected_base_sha,files,spec.front_id!);else if(parents.length!==3||parents[0]!==nextHead||parents[1]!==unpublishedRepair&&parents[1]!==remote&&parents[1]!==state.head_sha||parents[2]!==spec.expected_base_sha)throw new Error("blocked CI merge parents invalid");
    const nextFiles=git(worktree,["diff","--name-only",`${spec.expected_base_sha}..${nextHead}`]).split(/\r?\n/).filter(Boolean).sort();validateFiles(nextFiles,spec);
    // Agent Loop must preserve the existing candidate bytes until its mandatory receipt repair creates a new head.
    if(spec.executor==="agent_loop"){if(JSON.stringify(nextFiles)!==JSON.stringify(files))throw new Error("blocked CI Agent Loop tree changed during synchronization");}else native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",`${spec.expected_base_sha}..${nextHead}`],{stdio:"inherit",timeout:120000,windowsHide:true});
    if(nextHead!==remote){this.assertEffect("push",{issue:state.issue,expected_head:nextHead,...(remote!==state.head_sha?{observed_head:remote}:{})});native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`${nextHead}:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});waitForRemoteBranchHead(this.bus,spec.work_branch,nextHead);}
    const localHead=git(worktree,["rev-parse","HEAD"]);if(localHead!==nextHead){try{git(worktree,["merge-base","--is-ancestor",localHead,nextHead]);}catch{throw new Error("blocked CI local branch drift");}native(process.env.GIT_PATH??"git",["-C",worktree,"merge","--ff-only",nextHead],{stdio:"inherit",timeout:120000,windowsHide:true});}
    if(git(worktree,["rev-parse","HEAD"])!==nextHead||git(worktree,["status","--porcelain","--untracked-files=all"]))throw new Error("blocked CI worktree synchronization failed");return nextHead;
  }
  private governedBaselineRestore(worktree:string,baseSha:string,provenance:BuilderAttemptProvenance,input:BuilderInput):void{
    const paths=provenance.quarantinedPaths(worktree,baseSha);
    for(const path of paths.untracked){
      const inScope=input.allowed_paths.some(p=>p.endsWith("/")?path.startsWith(p):path===p)&&!input.forbidden_paths.some(p=>path===p||path.startsWith(p.endsWith("/")?p:`${p}/`));
      if(!inScope)throw new Error(`quarantined untracked path outside scope: ${path}`);
      rmSync(join(worktree,path),{recursive:true,force:true});
    }
    native(process.env.GIT_PATH??"git",["-C",worktree,"reset","--hard",baseSha],{stdio:"inherit",timeout:120000,windowsHide:true});
    if(git(worktree,["rev-parse","HEAD"])!==baseSha)throw new Error("builder baseline reset failed");
    const remaining=git(worktree,["status","--porcelain","--untracked-files=all"]);
    if(remaining)throw new Error("governed baseline restore left unexpected files");
  }

  private readPublishedBranchHead(worktree:string,branch:string):string|undefined{
    let observed:string|undefined;try{observed=this.bus.remoteBranchHead(branch);}catch{}
    if(observed!==undefined&&!/^[0-9a-f]{40}$/.test(observed))return undefined;
    let line="";try{line=git(worktree,["ls-remote","--heads","origin",`refs/heads/${branch}`]).split(/\s+/)[0]??"";}catch{return observed;}
    if(/^[0-9a-f]{40}$/.test(line))return observed===undefined||observed===line?line:undefined;
    return observed;
  }

  private async publishOrdinaryCleanCandidate(spec:ProxySpec,issue:number,session:string,repairCycle:number,retryReason:"BUILDER_FAILURE"|undefined,worktree:string,baseSha:string,observedHead:string,existing:{number:number;head_sha:string}|undefined){
    if(!spec.front_id||!spec.work_branch)throw new Error("builder metadata missing");
    const requestedRepair=repairCycle>0?this.bus.repairPrompt(issue):"";
    const repair=requestedRepair||(retryReason==="BUILDER_FAILURE"&&repairCycle>0?"Previous builder execution failed before producing a candidate. Re-run the approved objective exactly; do not infer reviewer findings or broaden scope.":"");
    if(repairCycle>0&&!repair)throw new Error("repair findings missing");
    const prompt=builderPrompt(spec,repairCycle,repair);
    const adapter:CandidateExecutionAdapter={
      prepare:()=>({worktree,starting_head:baseSha}),
      invokeProvider:async request=>{this.assertEffect("builder_execute",{issue});return await routeControlPlaneBuild(spec,issue,request.prompt,repairCycle,{baseSha},worktree);},
      changedPaths:(_prepared,_base,providerHead)=>providerHead===baseSha?changed(worktree):committed(worktree,baseSha),
      runDeclaredTests:()=>runDeclaredTests(worktree,spec.test_commands),
      diffCheck:(_prepared,_base,providerHead)=>native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",...(providerHead===baseSha?[]:[`${baseSha}..${providerHead}`])],{stdio:"inherit",timeout:120000,windowsHide:true}),
      commit:(_prepared,receipt,paths,provider)=>{this.assertEffect("commit_create",{issue});if(provider.head_sha!==baseSha)native(process.env.GIT_PATH??"git",["-C",worktree,"commit","--allow-empty","-m",receipt],{stdio:"inherit",timeout:120000,windowsHide:true});else{native(process.env.GIT_PATH??"git",["-C",worktree,"add","--",...paths],{stdio:"inherit",timeout:120000,windowsHide:true});native(process.env.GIT_PATH??"git",["-C",worktree,"commit","-m",receipt],{stdio:"inherit",timeout:120000,windowsHide:true});}const head=git(worktree,["rev-parse","HEAD"]);validateBuilderReceipt(worktree,head,spec.front_id!);return head;},
      push:(_attempt,head)=>{this.assertEffect("push",{issue,expected_head:head,...(repairCycle>0?{observed_head:observedHead}:{})});native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`HEAD:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});},
      remoteHead:branch=>this.readPublishedBranchHead(worktree,branch),
      existingDraftPr:()=>existing?.number,
      createDraftPr:()=>this.bus.createDraftPr(spec.work_branch!,"codex/own-capital-sustainable-return",`feat(control-plane): ${spec.objective}`,`FRONT_ID: ${spec.front_id}\n\nRoadmap item: ${spec.roadmap_item_id}\n\nBuilder session: ${session}\n\nNo auto-merge.`),
      bindPrToIssue:(boundIssue,pr)=>this.bus.bindPrToIssue(boundIssue,pr),
    };
    const attempt:PreparedCandidateAttempt={repository:spec.repository,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,issue,work_branch:spec.work_branch,expected_base_sha:baseSha,observed_head_sha:observedHead,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,test_commands:spec.test_commands,provider_request:{prompt,executor_role:"codex_control_plane"},publication_receipt:{kind:"ORDINARY",render:provider=>builderReceiptMessage(spec.front_id!,provider)}};
    const result=await new CandidateExecutionKernel(adapter).publish(attempt);
    return {pr:result.pr,head_sha:result.head_sha,session};
  }

  async build(spec:ProxySpec,issue:number,session:string,repairCycle:number,retryReason?:"BUILDER_FAILURE"){
    if(!spec.front_id||!spec.work_branch||!spec.objective)throw new Error("builder metadata missing");
    const existing=this.bus.findPrByBranch(spec.work_branch),orphanHead=!existing&&repairCycle===0?this.bus.remoteBranchHead(spec.work_branch):undefined,publishedHead=repairCycle===0?(existing?.head_sha??orphanHead):undefined;
    ensureCommit(this.sourceRepo,spec.expected_base_sha);
    mkdirSync(this.worktreeRoot,{recursive:true});const root=realpathSync(this.worktreeRoot);if(lstatSync(root).isSymbolicLink())throw new Error("worktree root symlink denied");
    let worktree=resolve(root,spec.front_id);if(!worktree.startsWith(`${root}\\`)&&!worktree.startsWith(`${root}/`))throw new Error("worktree escaped root");
    if(!existsSync(worktree)){this.assertEffect("branch_create",{issue});if(publishedHead){native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"fetch","origin",spec.work_branch],{stdio:"inherit",timeout:120000,windowsHide:true});native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","--detach",worktree,publishedHead],{stdio:"inherit",timeout:120000,windowsHide:true});}else if(existing){native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"fetch","origin",spec.work_branch],{stdio:"inherit",timeout:120000,windowsHide:true});try{native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add",worktree,spec.work_branch],{stdio:"inherit",timeout:120000,windowsHide:true});}catch{native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","-b",spec.work_branch,worktree,`origin/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});}}else native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","-b",spec.work_branch,worktree,spec.expected_base_sha],{stdio:"inherit",timeout:120000,windowsHide:true});}
    let recoveryDetached=false;
    // Historical dirty worktrees are forensic evidence. A repair resumes from a
    // clean detached checkout of the published candidate instead of deleting it.
    if(spec.executor==="codex_control_plane"&&repairCycle>0&&existing&&git(worktree,["status","--porcelain","--untracked-files=all"])){
      const remote=this.bus.remoteBranchHead(spec.work_branch);
      if(!remote||remote!==existing.head_sha||!/^[a-f0-9]{40}$/.test(remote))throw new Error("repair candidate branch identity invalid");
      const recovery=resolve(root,`${spec.front_id}-builder-recovery-${remote.slice(0,12)}`);
      if(!recovery.startsWith(`${root}\\`)&&!recovery.startsWith(`${root}/`))throw new Error("builder recovery worktree escaped root");
      if(!existsSync(recovery))native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","--detach",recovery,remote],{stdio:"inherit",timeout:120000,windowsHide:true});
      if(realpathSync(recovery).toLowerCase()!==recovery.toLowerCase()||git(recovery,["branch","--show-current"])!==""||git(recovery,["rev-parse","HEAD"])!==remote||git(recovery,["status","--porcelain","--untracked-files=all"]))throw new Error("builder recovery worktree state invalid");
      worktree=recovery;recoveryDetached=true;
    }
    if(realpathSync(worktree).toLowerCase()!==worktree.toLowerCase())throw new Error("worktree path identity mismatch");const branch=git(worktree,["branch","--show-current"]);if(branch!==spec.work_branch&&(branch!==""||!publishedHead&&!recoveryDetached))throw new Error("worktree branch mismatch");let initialStatus=git(worktree,["status","--porcelain","--untracked-files=all"]);let initialHead=git(worktree,["rev-parse","HEAD"]);
    const legacyMode=existing&&isLegacyUnattestedPr(spec,existing,this.bus,worktree,initialHead);
    const expectedHead=legacyMode?spec.expected_base_sha:(existing?.head_sha??spec.expected_base_sha);
    if(publishedHead&&!legacyMode){
      const remote=this.bus.remoteBranchHead(spec.work_branch);if(remote!==publishedHead||initialHead!==publishedHead||initialStatus)throw new Error("published builder branch identity invalid");
      try{git(worktree,["merge-base","--is-ancestor",spec.expected_base_sha,publishedHead]);}catch{throw new Error("published builder ancestry invalid");}
      validateBuilderReceipt(worktree,publishedHead,spec.front_id);const files=committed(worktree,spec.expected_base_sha);validateFiles(files,spec);runDeclaredTests(worktree,spec.test_commands);native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",`${spec.expected_base_sha}..${publishedHead}`],{stdio:"inherit",timeout:120000,windowsHide:true});
      if(existing)validatePublishedPr(spec,existing,this.bus.prIdentity(existing.number),publishedHead,files);
      const pr=existing?.number??this.bus.createDraftPr(spec.work_branch,"codex/own-capital-sustainable-return",`feat(control-plane): ${spec.objective}`,`FRONT_ID: ${spec.front_id}\n\nRoadmap item: ${spec.roadmap_item_id}\n\nRecovered published builder branch.\n\nNo auto-merge.`);this.bus.bindPrToIssue(issue,pr);return {pr,head_sha:publishedHead,session};
    }
    if(spec.executor==="codex_control_plane"&&initialStatus){
      const provenance=new BuilderAttemptProvenance(process.env);
      const provenanceConfigured=provenance.isConfigured();
      const attemptInput={repository:spec.repository,worktree,front_id:spec.front_id,issue,base_sha:expectedHead,work_branch:spec.work_branch,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,acceptance:spec.acceptance,test_commands:spec.test_commands,repair_cycle:repairCycle,risk:spec.risk,deployment_mode:spec.deployment_mode??"NO_DEPLOY",prompt:"",session};
      if(provenanceConfigured){
        const recoverable=provenance.findRecoverableStartedAttempt(attemptInput);
        if(recoverable){
          const receipt=recoverable.receipt;
          if(!receipt.provider_correlation_id)throw new Error("BUILDER_PROVENANCE_RECOVERY_REQUIRED: durable provider correlation missing");
          const files=changed(worktree);validateFiles(files,spec);
          runDeclaredTests(worktree,spec.test_commands);native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check"],{stdio:"inherit",timeout:120000,windowsHide:true});
          this.assertEffect("commit_create",{issue});
          native(process.env.GIT_PATH??"git",["-C",worktree,"add","--",...files],{stdio:"inherit",timeout:120000,windowsHide:true});
          const syntheticResult:BuilderResult={executor_role:"codex_control_plane",builder_backend:receipt.backend,builder_model:receipt.model,builder_session:receipt.builder_session,provider_session:receipt.provider_correlation_id,base_sha:receipt.base_sha,head_sha:initialHead,branch:spec.work_branch,commit:"",pr:0,started_utc:receipt.created_utc,completed_utc:new Date().toISOString()};
          native(process.env.GIT_PATH??"git",["-C",worktree,"commit","-m",builderReceiptMessage(spec.front_id,syntheticResult)],{stdio:"inherit",timeout:120000,windowsHide:true});
          const head=git(worktree,["rev-parse","HEAD"]);if(head===initialHead)throw new Error("builder produced no changes");
          validateBuilderReceipt(worktree,head,spec.front_id);
          this.assertEffect("push",{issue,expected_head:head,...(repairCycle>0?{observed_head:expectedHead}:{})});native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`HEAD:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});
          const prNumber:number=(existing as any)?.number??this.bus.createDraftPr(spec.work_branch,"codex/own-capital-sustainable-return",`feat(control-plane): ${spec.objective}`,`FRONT_ID: ${spec.front_id}\n\nRoadmap item: ${spec.roadmap_item_id}\n\nBuilder session: ${receipt.builder_session}\n\nNo auto-merge.`);
          this.bus.bindPrToIssue(issue,prNumber);
          provenance.recordAttemptCompleted(receipt.receipt_id,spec.front_id,head,files,syntheticResult.provider_session);
          return {pr:prNumber,head_sha:head,session,recovered_dirty:true as const};
        }
        provenance.recordQuarantine(attemptInput,initialHead,expectedHead,"BUILDER_PROVENANCE_RECOVERY_REQUIRED");
        this.governedBaselineRestore(worktree,expectedHead,provenance,attemptInput);
      }
      if(legacyMode){
        return await this.rebuildLegacyPr(spec,issue,session,repairCycle,worktree,expectedHead,existing!,initialHead);
      }
      const repair=repairCycle>0?this.bus.repairPrompt(issue):"";if(repairCycle>0&&!repair)throw new Error("repair findings missing");
      const prompt=builderPrompt(spec,repairCycle,repair);
      this.assertEffect("builder_execute",{issue});
      const result=await routeControlPlaneBuild(spec,issue,prompt,repairCycle,{baseSha:expectedHead},worktree);
      if(result.executor_role!=="codex_control_plane"||!result.builder_backend||!result.builder_model||!result.builder_session||!result.provider_session||result.base_sha!==expectedHead||!/^[0-9a-f]{40}$/.test(result.head_sha))throw new Error("builder router result contract invalid");
      const head=result.head_sha,currentHead=git(worktree,["rev-parse","HEAD"]);if(currentHead!==head)throw new Error("builder router head mismatch");
      const backendCommitted=head!==expectedHead,files=backendCommitted?committed(worktree,expectedHead):changed(worktree);validateFiles(files,spec);
      if(backendCommitted&&git(worktree,["status","--porcelain","--untracked-files=all"]))throw new Error("builder committed head left dirty worktree");
      runDeclaredTests(worktree,spec.test_commands);native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",...(backendCommitted?[`${expectedHead}..${head}`]:[])],{stdio:"inherit",timeout:120000,windowsHide:true});
      this.assertEffect("commit_create",{issue});
      if(backendCommitted)native(process.env.GIT_PATH??"git",["-C",worktree,"commit","--allow-empty","-m",builderReceiptMessage(spec.front_id,result)],{stdio:"inherit",timeout:120000,windowsHide:true});
      else {native(process.env.GIT_PATH??"git",["-C",worktree,"add","--",...files],{stdio:"inherit",timeout:120000,windowsHide:true});native(process.env.GIT_PATH??"git",["-C",worktree,"commit","-m",builderReceiptMessage(spec.front_id,result)],{stdio:"inherit",timeout:120000,windowsHide:true});}
      const committedHead=git(worktree,["rev-parse","HEAD"]);
      if(committedHead===expectedHead)throw new Error("builder produced no changes");
      validateBuilderReceipt(worktree,committedHead,spec.front_id);
      this.assertEffect("push",{issue,expected_head:committedHead,observed_head:initialHead});native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`HEAD:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});
      const prNumber=existing?.number??this.bus.createDraftPr(spec.work_branch,"codex/own-capital-sustainable-return",`feat(control-plane): ${spec.objective}`,`FRONT_ID: ${spec.front_id}\n\nRoadmap item: ${spec.roadmap_item_id}\n\nBuilder session: ${session}\n\nNo auto-merge.`);this.bus.bindPrToIssue(issue,prNumber);
      return {pr:prNumber,head_sha:committedHead,session,recovered_clean:true as const};
    }
    if(!existing&&initialHead!==expectedHead&&!initialStatus){let canFastForward=false;try{git(worktree,["merge-base","--is-ancestor",initialHead,expectedHead]);canFastForward=true;}catch{}if(canFastForward){native(process.env.GIT_PATH??"git",["-C",worktree,"merge","--ff-only",expectedHead],{stdio:"inherit",timeout:120000,windowsHide:true});initialHead=git(worktree,["rev-parse","HEAD"]);initialStatus=git(worktree,["status","--porcelain","--untracked-files=all"]);if(initialHead!==expectedHead||initialStatus)throw new Error("builder worktree base fast-forward failed");}}
    if(initialHead!==expectedHead){if(initialStatus)throw new Error("advanced builder worktree is dirty");try{git(worktree,["merge-base","--is-ancestor",expectedHead,initialHead]);}catch{throw new Error("builder worktree head is not a descendant of expected head");}
      let receiptValid=false;try{validateBuilderReceipt(worktree,initialHead,spec.front_id);receiptValid=true;}catch{receiptValid=false;}
      if(receiptValid){validateFiles(committed(worktree,expectedHead),spec);runDeclaredTests(worktree,spec.test_commands);native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",`${expectedHead}..${initialHead}`],{stdio:"inherit",timeout:120000,windowsHide:true});this.assertEffect("push",{issue,expected_head:initialHead,...(repairCycle>0?{observed_head:expectedHead}:{})});native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`HEAD:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});const pr=existing?.number??this.bus.createDraftPr(spec.work_branch,"codex/own-capital-sustainable-return",`feat(control-plane): ${spec.objective}`,`FRONT_ID: ${spec.front_id}\n\nRoadmap item: ${spec.roadmap_item_id}\n\nRecovered local builder commit.\n\nNo auto-merge.`);this.bus.bindPrToIssue(issue,pr);return {pr,head_sha:initialHead,session};}
      const provenance=new BuilderAttemptProvenance(process.env);
      const attemptInput={repository:spec.repository,worktree,front_id:spec.front_id,issue,base_sha:expectedHead,work_branch:spec.work_branch,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,acceptance:spec.acceptance,test_commands:spec.test_commands,repair_cycle:repairCycle,risk:spec.risk,deployment_mode:spec.deployment_mode??"NO_DEPLOY",prompt:"",session};
      if(provenance.isConfigured()){
        provenance.recordQuarantine(attemptInput,initialHead,expectedHead,"BUILDER_PROVENANCE_RECOVERY_REQUIRED");
        this.governedBaselineRestore(worktree,expectedHead,provenance,attemptInput);
      }
      if(legacyMode){
        return await this.rebuildLegacyPr(spec,issue,session,repairCycle,worktree,expectedHead,existing!,initialHead);
      }
      const repair=repairCycle>0?this.bus.repairPrompt(issue):"";if(repairCycle>0&&!repair)throw new Error("repair findings missing");
      const prompt=builderPrompt(spec,repairCycle,repair);
      this.assertEffect("builder_execute",{issue});
      const result=await routeControlPlaneBuild(spec,issue,prompt,repairCycle,{baseSha:expectedHead},worktree);
      if(result.executor_role!=="codex_control_plane"||!result.builder_backend||!result.builder_model||!result.builder_session||!result.provider_session||result.base_sha!==expectedHead||!/^[0-9a-f]{40}$/.test(result.head_sha))throw new Error("builder router result contract invalid");
      const head=result.head_sha,currentHead=git(worktree,["rev-parse","HEAD"]);if(currentHead!==head)throw new Error("builder router head mismatch");
      const backendCommitted=head!==expectedHead,files=backendCommitted?committed(worktree,expectedHead):changed(worktree);validateFiles(files,spec);
      if(backendCommitted&&git(worktree,["status","--porcelain","--untracked-files=all"]))throw new Error("builder committed head left dirty worktree");
      runDeclaredTests(worktree,spec.test_commands);native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",...(backendCommitted?[`${expectedHead}..${head}`]:[])],{stdio:"inherit",timeout:120000,windowsHide:true});
      this.assertEffect("commit_create",{issue});
      if(backendCommitted)native(process.env.GIT_PATH??"git",["-C",worktree,"commit","--allow-empty","-m",builderReceiptMessage(spec.front_id,result)],{stdio:"inherit",timeout:120000,windowsHide:true});
      else {native(process.env.GIT_PATH??"git",["-C",worktree,"add","--",...files],{stdio:"inherit",timeout:120000,windowsHide:true});native(process.env.GIT_PATH??"git",["-C",worktree,"commit","-m",builderReceiptMessage(spec.front_id,result)],{stdio:"inherit",timeout:120000,windowsHide:true});}
      const committedHead=git(worktree,["rev-parse","HEAD"]);
      if(committedHead===expectedHead)throw new Error("builder produced no changes");
      validateBuilderReceipt(worktree,committedHead,spec.front_id);
      this.assertEffect("push",{issue,expected_head:committedHead,observed_head:initialHead});native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`HEAD:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});
      const prNumber=existing?.number??this.bus.createDraftPr(spec.work_branch,"codex/own-capital-sustainable-return",`feat(control-plane): ${spec.objective}`,`FRONT_ID: ${spec.front_id}\n\nRoadmap item: ${spec.roadmap_item_id}\n\nBuilder session: ${session}\n\nNo auto-merge.`);this.bus.bindPrToIssue(issue,prNumber);
      return {pr:prNumber,head_sha:committedHead,session,recovered_clean:true as const};}
    if(repairCycle>0&&existing&&git(worktree,["show","-s","--format=%s",initialHead])===`chore(control-plane): synchronize ${spec.front_id} base`){
      try{synchronizedRepairReceipt(worktree,initialHead,spec.front_id);const files=committed(worktree,spec.expected_base_sha);validateFiles(files,spec);runDeclaredTests(worktree,spec.test_commands);native(process.env.GIT_PATH??"git",["-C",worktree,"diff","--check",`${spec.expected_base_sha}..${initialHead}`],{stdio:"inherit",timeout:120000,windowsHide:true});validatePublishedPr(spec,existing,this.bus.prIdentity(existing.number),initialHead,files);this.bus.bindPrToIssue(issue,existing.number);return {pr:existing.number,head_sha:initialHead,session,recovered_repair:true as const};}
      catch(error){
        if(!(error instanceof Error)||!new Set(["recovered builder receipt invalid","recovered builder commit subject mismatch"]).has(error.message))throw error;
        // A synchronized candidate with an intervening metadata commit is not a
        // validated receipt at its current head. Rebuild it rather than accepting it.
      }
    }
    if(!initialStatus){
      if(spec.executor==="codex_control_plane"){
        const useRouter=process.env.OPERATOR_PROXY_BUILDER_ROUTER!=="disabled";
        if(useRouter)return await this.publishOrdinaryCleanCandidate(spec,issue,session,repairCycle,retryReason,worktree,initialHead,initialHead,existing);
        throw new Error("codex builder direct mode disabled; use router");
      } else throw new Error("agent_loop builder adapter unavailable");
    }
    throw new Error("BUILDER_PROVENANCE_RECOVERY_REQUIRED: dirty worktree without recoverable provenance");
  }

  private async rebuildLegacyPr(spec:ProxySpec,issue:number,session:string,repairCycle:number,worktree:string,baseSha:string,existing:{number:number;head_sha:string},legacyHead:string):Promise<{pr:number;head_sha:string;session:string;recovered_legacy:true}>{
    const identity=this.bus.prIdentity(existing.number);
    const prFiles=(identity.files??[]).map((item:any)=>String(item.path)).sort();
    if(!spec.front_id||!spec.work_branch)throw new Error("builder metadata missing");
    if(identity.author?.login!=="cesarmanuel8102"||identity.baseRefName!=="codex/own-capital-sustainable-return"||identity.baseRefOid!==baseSha||identity.headRefName!==spec.work_branch||identity.headRefOid!==legacyHead||identity.headRepository?.nameWithOwner!=="cesarmanuel8102/AI_Vault"||identity.isCrossRepository!==false||identity.isDraft!==true||identity.state!=="OPEN")throw new Error("legacy PR identity invalid for neutralization");
    try{git(worktree,["merge-base","--is-ancestor",baseSha,legacyHead]);}catch{throw new Error("legacy PR ancestry invalid");}
    const files=(()=>{const output=git(worktree,["diff","--name-only",`${baseSha}..${legacyHead}`]);return output?output.split(/\r?\n/).filter(Boolean).sort():[];})();
    if(JSON.stringify(prFiles)!==JSON.stringify(files))throw new Error("legacy PR file scope mismatch");
    try{validateFiles(files,spec);}catch{throw new Error("legacy PR files out of scope");}

    const baseTree=treeOf(worktree,baseSha);
    const n=commitTree(worktree,baseTree,[legacyHead],neutralizationMessage(spec.front_id,legacyHead,baseSha));
    if(!diffEmpty(worktree,baseSha,n)||git(worktree,["rev-parse",`${n}^`])!==legacyHead)throw new Error("legacy neutralization commit invalid");
    this.assertEffect("push",{issue,expected_head:n,observed_head:legacyHead});
    native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`${n}:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});
    waitForRemoteBranchHead(this.bus,spec.work_branch,n);

    const tempWorktree=join(this.worktreeRoot,`${spec.front_id}-legacy-${randomUUID()}`);
    native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","add","--detach",tempWorktree,baseSha],{stdio:"inherit",timeout:120000,windowsHide:true});
    try{
      const repair=repairCycle>0?this.bus.repairPrompt(issue):"";if(repairCycle>0&&!repair)throw new Error("repair findings missing");
      const prompt=builderPrompt(spec,repairCycle,repair);
      this.assertEffect("builder_execute",{issue});
      const result=await routeControlPlaneBuild(spec,issue,prompt,repairCycle,{baseSha},tempWorktree);
      if(result.executor_role!=="codex_control_plane"||!result.builder_backend||!result.builder_model||!result.builder_session||!result.provider_session||result.base_sha!==baseSha||!/^[0-9a-f]{40}$/.test(result.head_sha))throw new Error("legacy builder router result contract invalid");
      const r=result.head_sha;
      const freshReceipt=git(tempWorktree,["show","-s","--format=%B",r]);
      if(freshReceipt.split("\n",1)[0]!==`feat(control-plane): complete ${spec.front_id}`)throw new Error("legacy fresh receipt subject invalid");

      const mTree=treeOf(tempWorktree,r);
      const m=commitTree(worktree,mTree,[n,r],legacyBridgeMessage(spec.front_id,n,r,baseSha));
      if(!diffEmpty(worktree,r,m))throw new Error("legacy bridge tree must equal fresh builder tree");
      if(git(worktree,["rev-parse",`${m}^1`])!==n||git(worktree,["rev-parse",`${m}^2`])!==r)throw new Error("legacy bridge parents invalid");
      this.assertEffect("push",{issue,expected_head:m,observed_head:n});
      native(process.env.GIT_PATH??"git",["-C",worktree,"push","origin",`${m}:refs/heads/${spec.work_branch}`],{stdio:"inherit",timeout:120000,windowsHide:true});
      waitForRemoteBranchHead(this.bus,spec.work_branch,m);
      this.bus.bindPrToIssue(issue,existing.number);
      return {pr:existing.number,head_sha:m,session,recovered_legacy:true as const};
    }finally{
      native(process.env.GIT_PATH??"git",["-C",this.sourceRepo,"worktree","remove",tempWorktree],{stdio:"inherit",timeout:120000,windowsHide:true});
    }
  }
}
