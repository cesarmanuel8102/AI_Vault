import type {BuilderTransport} from "./builder_backend.js";

const SHA40=/^[0-9a-f]{40}$/;

export interface CandidateProviderRequest {
  prompt:string;
  executor_role:"codex_control_plane"|"agent_loop";
}

export interface CandidateProviderResult {
  executor_role:"codex_control_plane"|"agent_loop";
  builder_backend:BuilderTransport;
  builder_model:string;
  builder_session:string;
  provider_session:string;
  fallback_reason?:string;
  base_sha:string;
  head_sha:string;
  branch:string;
}

export interface CandidatePublicationReceipt {
  kind:"ORDINARY"|"OWNER_AUTHORIZED_PAYLOAD_REPAIR";
  render(provider:CandidateProviderResult):string;
}

export interface PreparedCandidateAttempt {
  repository:string;
  front_id:string;
  roadmap_item_id:string;
  issue:number;
  work_branch:string;
  expected_base_sha:string;
  observed_head_sha?:string;
  allowed_paths:readonly string[];
  forbidden_paths:readonly string[];
  test_commands:readonly string[];
  provider_request:CandidateProviderRequest;
  provider_idempotency_key?:string;
  publication_receipt:CandidatePublicationReceipt;
  require_existing_draft_pr?:boolean;
}

export interface PreparedCandidateWorktree {
  worktree:string;
  starting_head:string;
}

export interface CandidateExistingDraftPr {
  number:number;
  repository:string;
  issue:number;
  work_branch:string;
  base_sha:string;
  head_sha:string;
  is_draft:boolean;
  is_open:boolean;
  same_repository:boolean;
  non_fork:boolean;
  changed_paths:readonly string[];
}

export interface CandidateExecutionAdapter {
  prepare(attempt:PreparedCandidateAttempt):PreparedCandidateWorktree;
  invokeProvider(request:CandidateProviderRequest&{idempotency_key?:string},worktree:PreparedCandidateWorktree):Promise<CandidateProviderResult>;
  changedPaths(worktree:PreparedCandidateWorktree,base_sha:string,head_sha:string):string[];
  runDeclaredTests(worktree:PreparedCandidateWorktree,commands:readonly string[]):void;
  diffCheck(worktree:PreparedCandidateWorktree,base_sha:string,head_sha:string):void;
  commit(worktree:PreparedCandidateWorktree,receipt:string,paths:readonly string[],provider:CandidateProviderResult):string;
  push(attempt:PreparedCandidateAttempt,head_sha:string):void;
  remoteHead(branch:string):string|undefined;
  existingDraftPr(attempt:PreparedCandidateAttempt,head_sha:string,paths:readonly string[]):number|CandidateExistingDraftPr|undefined;
  createDraftPr(attempt:PreparedCandidateAttempt,head_sha:string):number;
  bindPrToIssue(issue:number,pr:number):void;
}

export interface CandidatePublicationResult {
  pr:number;
  head_sha:string;
  base_sha:string;
  work_branch:string;
  changed_paths:readonly string[];
  builder_backend:string;
  builder_model:string;
  builder_session:string;
  provider_session:string;
  provider_idempotency_key?:string;
}

function pathAllowed(path:string,attempt:PreparedCandidateAttempt):boolean {
  const allowed=attempt.allowed_paths.some(prefix=>prefix.endsWith("/")?path.startsWith(prefix):path===prefix);
  const forbidden=attempt.forbidden_paths.some(prefix=>path===prefix||path.startsWith(prefix.endsWith("/")?prefix:`${prefix}/`));
  return allowed&&!forbidden;
}

function validateAttempt(attempt:PreparedCandidateAttempt):void {
  if(!attempt.repository||!attempt.front_id||!attempt.roadmap_item_id||!Number.isInteger(attempt.issue)||attempt.issue<1||!attempt.work_branch||!SHA40.test(attempt.expected_base_sha)||attempt.allowed_paths.length===0||attempt.test_commands.length===0||!attempt.provider_request.prompt||typeof attempt.publication_receipt.render!=="function")throw new Error("candidate attempt invalid");
  for(const forbidden of ["repair_cycle","repair_prompt","owner_comment_body","owner_principal","authorization_policy","receipt_ledger_mutation","lifecycle_mutation"]){if(Object.hasOwn(attempt,forbidden))throw new Error("candidate attempt contains semantic field");}
}

function validateProvider(attempt:PreparedCandidateAttempt,worktree:PreparedCandidateWorktree,provider:CandidateProviderResult):void {
  if(!worktree.worktree||worktree.starting_head!==attempt.expected_base_sha||provider.executor_role!==attempt.provider_request.executor_role||provider.base_sha!==attempt.expected_base_sha||provider.branch!==attempt.work_branch||!SHA40.test(provider.head_sha)||!provider.builder_backend||!provider.builder_model||!provider.builder_session||!provider.provider_session)throw new Error("candidate provider result invalid");
}

function validatedExistingPr(attempt:PreparedCandidateAttempt,head:string,paths:readonly string[],existing:number|CandidateExistingDraftPr|undefined):number|undefined {
  if(existing===undefined)return undefined;
  if(typeof existing==="number"){if(attempt.require_existing_draft_pr)throw new Error("candidate existing Draft PR identity invalid");return existing;}
  if(!Number.isInteger(existing.number)||existing.number<1||existing.repository!==attempt.repository||existing.issue!==attempt.issue||existing.work_branch!==attempt.work_branch||existing.base_sha!==attempt.expected_base_sha||existing.head_sha!==head||existing.is_draft!==true||existing.is_open!==true||existing.same_repository!==true||existing.non_fork!==true||JSON.stringify([...existing.changed_paths].sort())!==JSON.stringify([...paths].sort()))throw new Error("candidate existing Draft PR identity invalid");
  return existing.number;
}

export class CandidateExecutionKernel {
  constructor(private readonly adapter:CandidateExecutionAdapter){}

  async publish(attempt:PreparedCandidateAttempt):Promise<CandidatePublicationResult> {
    validateAttempt(attempt);
    const worktree=this.adapter.prepare(attempt);
    const provider=await this.adapter.invokeProvider({...attempt.provider_request,...(attempt.provider_idempotency_key?{idempotency_key:attempt.provider_idempotency_key}:{})},worktree);
    validateProvider(attempt,worktree,provider);
    const paths=[...new Set(this.adapter.changedPaths(worktree,attempt.expected_base_sha,provider.head_sha))].sort();
    if(paths.length===0||!paths.every(path=>pathAllowed(path,attempt)))throw new Error("candidate changed path outside scope");
    this.adapter.runDeclaredTests(worktree,attempt.test_commands);
    this.adapter.diffCheck(worktree,attempt.expected_base_sha,provider.head_sha);
    const receipt=attempt.publication_receipt.render(provider);
    if(!receipt.trim())throw new Error("candidate publication receipt invalid");
    const head=this.adapter.commit(worktree,receipt,paths,provider);
    if(!SHA40.test(head)||head===attempt.expected_base_sha)throw new Error("candidate commit invalid");
    this.adapter.push(attempt,head);
    if(this.adapter.remoteHead(attempt.work_branch)!==head)throw new Error("candidate remote head mismatch");
    let pr=validatedExistingPr(attempt,head,paths,this.adapter.existingDraftPr(attempt,head,paths));
    if(pr===undefined){if(attempt.require_existing_draft_pr)throw new Error("candidate existing Draft PR missing");pr=this.adapter.createDraftPr(attempt,head);}
    if(!Number.isInteger(pr)||pr<1)throw new Error("candidate Draft PR invalid");
    this.adapter.bindPrToIssue(attempt.issue,pr);
    return {pr,head_sha:head,base_sha:attempt.expected_base_sha,work_branch:attempt.work_branch,changed_paths:paths,builder_backend:provider.builder_backend,builder_model:provider.builder_model,builder_session:provider.builder_session,provider_session:provider.provider_session,...(attempt.provider_idempotency_key?{provider_idempotency_key:attempt.provider_idempotency_key}:{})};
  }
}
