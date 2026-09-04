import {randomUUID} from "node:crypto";
import type {LifecycleRecord, ProxySpec, ReviewerOutput} from "./types.js";
import {LifecycleStore} from "./lifecycle_store.js";
import {isEligibleFallback} from "./builder_backend.js";
import {redactString} from "./redaction.js";

export interface BuildResult {pr:number;head_sha:string;session:string;recovered_repair?:true}
export type CiResult="PENDING"|"PASS"|"FAIL";
export interface PolicyResult {outcome:"APPROVE"|"REPAIR"|"BLOCK"|"ESCALATE_TO_OWNER";decision_id:string;consummated_payload_repairs?:number}
export interface ReviewResult {output:ReviewerOutput;session:string}
export interface AutonomousEffects {
  bindLifecycle(spec:ProxySpec,state:LifecycleRecord):void;
  ensureIssue(spec:ProxySpec):number;
  ensureBuild(spec:ProxySpec,issue:number,session:string,repairCycle:number,previousHead?:string,retryReason?:"BUILDER_FAILURE"):Promise<BuildResult|"PENDING">;
  /** Dedicated Owner path; ordinary BUILDING never calls this operation. */
  resumeOwnerPayloadRepair?(spec:ProxySpec,state:LifecycleRecord,store:LifecycleStore):Promise<LifecycleRecord|"PENDING">;
  /** Dedicated Owner path; ordinary policy execution never calls this operation. */
  resumeOwnerCriticalMerge?(spec:ProxySpec,state:LifecycleRecord,store:LifecycleStore):Promise<LifecycleRecord|"PENDING">;
  ci(pr:number,head:string):CiResult;
  review(pr:number,head:string,session:string):ReviewResult;
  policy(spec:ProxySpec,issue:number,pr:number,head:string,review:ReviewerOutput,builderSession:string,reviewerSession:string,repairCycles:number):PolicyResult;
  ensureMerge(pr:number,head:string,base:string,decisionId:string):string;
  ensureInstall(spec:ProxySpec,merge:string):"PASS"|"LOCAL_PRIVILEGE_REQUIRED";
  ensureRuntimePilot(spec:ProxySpec,merge:string):"PASS"|"PENDING";
  ensureCloseout(spec:ProxySpec,merge:string):Promise<"PASS"|"PENDING">;
  discoverNext(completedItem:string):void;
}

export function newLifecycle(spec:ProxySpec):LifecycleRecord {
  if(!spec.front_id||!spec.deployment_mode)throw new Error("autonomous spec metadata missing");
  return {schema_version:1,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,state:"DISCOVERED",base_sha:spec.expected_base_sha,repair_cycles:0,deployment_mode:spec.deployment_mode,completed_effects:[],updated_utc:new Date().toISOString()};
}

function builderFailureDetail(error: unknown): string {
  const message=redactString(error instanceof Error?error.message:String(error));
  const known:[RegExp,string][]=[
    [/builder worktree base mismatch/i,"WORKTREE_BASE_MISMATCH"],
    [/base override does not match clean worktree HEAD/i,"BASE_OVERRIDE_MISMATCH"],
    [/builder worktree dirty/i,"WORKTREE_DIRTY"],
    [/builder recovery worktree state invalid/i,"RECOVERY_WORKTREE_INVALID"],
    [/recovered repair synchronization invalid/i,"RECOVERY_SYNC_INVALID"],
    [/recovered repair synchronization cycle detected/i,"RECOVERY_SYNC_CHAIN_INVALID"],
    [/recovered repair synchronization depth exceeded/i,"RECOVERY_SYNC_DEPTH_EXCEEDED"],
    [/recovered builder receipt invalid/i,"RECOVERY_RECEIPT_INVALID"],
    [/repair findings missing/i,"REPAIR_FINDINGS_MISSING"],
    [/external effect/i,"EXTERNAL_EFFECT_DENIED"],
    [/preferred builder backend invalid/i,"BUILDER_BACKEND_INVALID"],
    [/OPERATOR_PROXY_ROOT/i,"PROVENANCE_ROOT_INVALID"],
  ];
  return known.find(([pattern])=>pattern.test(message))?.[1]??"UNCLASSIFIED";
}

export class AutonomousFlow {
  constructor(readonly store:LifecycleStore,readonly effects:AutonomousEffects){}
  assertPrivilegedInstallState(expected:LifecycleRecord):LifecycleRecord {
    const state=this.store.load(expected.front_id);if(!state||JSON.stringify(state)!==JSON.stringify(expected)||state.state!=="ESCALATED"||state.last_error!=="LOCAL_PRIVILEGE_REQUIRED")throw new Error("privileged install resume not authorized by persisted state");return state;
  }
  resumePrivilegedInstall(expected:LifecycleRecord):LifecycleRecord {
    const state=this.assertPrivilegedInstallState(expected);
    return this.store.advance(state,"INSTALL_PENDING",{last_error:undefined});
  }
  async step(spec:ProxySpec):Promise<LifecycleRecord> {
    if(!spec.front_id)throw new Error("front id required");
    let state=this.store.load(spec.front_id)??newLifecycle(spec); if(!this.store.load(spec.front_id))this.store.save(state);
    if(state.base_sha!==spec.expected_base_sha||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("persisted lifecycle binding mismatch");this.effects.bindLifecycle(spec,state);
    switch(state.state){
      case "DISCOVERED": return this.store.advance(state,"ADMITTED");
      case "ADMITTED": {const issue=this.effects.ensureIssue(spec); state=this.store.effect(state,`issue:${issue}`); return this.store.advance(state,"ISSUE_CREATED",{issue});}
      case "ISSUE_CREATED":
      case "REPAIRING": return this.store.advance(state,"BUILDING");
      case "BLOCKED": {
        if(["CI_FAILED","REPAIR_LIMIT_REACHED"].includes(state.last_error??"")&&state.repair_cycles===2&&this.effects.resumeOwnerPayloadRepair){
          const resumed=await this.effects.resumeOwnerPayloadRepair(spec,state,this.store);
          return resumed==="PENDING"?state:resumed;
        }
        return state;
      }
      case "OWNER_REPAIR_AUTHORIZED": {
        if(!this.effects.resumeOwnerPayloadRepair)throw new Error("owner payload repair effect unavailable");
        const resumed=await this.effects.resumeOwnerPayloadRepair(spec,state,this.store);
        return resumed==="PENDING"?state:resumed;
      }
      case "ESCALATED": {
        if(state.last_error!=="OWNER_AUTHORITY_REQUIRED"||!this.effects.resumeOwnerCriticalMerge)return state;
        const resumed=await this.effects.resumeOwnerCriticalMerge(spec,state,this.store);
        return resumed==="PENDING"?state:resumed;
      }
      case "BUILDING": {if(state.owner_payload_repair){if(!this.effects.resumeOwnerPayloadRepair)throw new Error("owner payload repair effect unavailable");const resumed=await this.effects.resumeOwnerPayloadRepair(spec,state,this.store);return resumed==="PENDING"?state:resumed;}if(!state.issue)throw new Error("lifecycle issue missing");const session=`builder-${randomUUID()}`;let built:BuildResult|"PENDING";try{built=await this.effects.ensureBuild(spec,state.issue,session,state.repair_cycles,state.head_sha,state.builder_retry_reason);}catch(error){const {failure_class}=isEligibleFallback(error);return this.store.advance(state,"BLOCKED",{last_error:`BUILDER_FAILED:${failure_class}`,last_error_detail:builderFailureDetail(error),builder_retry_reason:state.repair_cycles>0&&state.builder_retry_reason===undefined?"BUILDER_FAILURE":undefined});}if(built==="PENDING")return state;const sameRepairHead=state.repair_cycles>0&&built.head_sha===state.head_sha;if(typeof built!=="object"||!built.session||!/^[0-9a-f]{40}$/.test(built.head_sha)||sameRepairHead&&built.recovered_repair!==true||!sameRepairHead&&built.recovered_repair===true)throw new Error("builder evidence invalid");if(!sameRepairHead)state=state.repair_cycles>0&&!!state.head_sha?this.store.repairBuild(state,built.head_sha):this.store.effect(state,`build:${built.head_sha}`);return this.store.advance(state,"PR_CREATED",{pr:built.pr,head_sha:built.head_sha,builder_session:built.session,builder_receipt_head_sha:undefined,builder_receipt_base_sha:undefined,decision_id:undefined,reviewer_session:undefined,builder_retry_reason:undefined,last_error_detail:undefined});}
      case "PR_CREATED": return this.store.advance(state,"CI_PENDING");
      case "CI_PENDING": {if(!state.pr||!state.head_sha)throw new Error("PR evidence missing");const ci=this.effects.ci(state.pr,state.head_sha);if(ci==="PENDING")return state;if(ci==="FAIL")return this.store.advance(state,"BLOCKED",{last_error:"CI_FAILED"});return this.store.advance(state,"REVIEWING");}
      case "REVIEWING": {if(!state.pr||!state.head_sha||!state.builder_session)throw new Error("review evidence missing");const requested=`reviewer-${randomUUID()}`;if(requested===state.builder_session)throw new Error("actor separation failed");const reviewed=this.effects.review(state.pr,state.head_sha,requested),review=reviewed.output,reviewer=reviewed.session;if(!reviewer||reviewer===state.builder_session)throw new Error("actor separation failed");if(review.head_sha!==state.head_sha)throw new Error("review head mismatch");const decision=this.effects.policy(spec,state.issue!,state.pr,state.head_sha,review,state.builder_session,reviewer,state.repair_cycles);if(!/^[0-9a-f-]{36}$/.test(decision.decision_id))throw new Error("policy decision id invalid");state={...state,reviewer_session:reviewer,decision_id:decision.decision_id};if(decision.outcome==="REPAIR"){const consummated=decision.consummated_payload_repairs;const nextCycle=Number.isInteger(consummated)&&consummated!>=0&&consummated!<2?consummated!+1:state.repair_cycles+1;return this.store.advance(state,"REPAIRING",{repair_cycles:nextCycle});}if(decision.outcome==="BLOCK")return this.store.advance(state,"BLOCKED",{last_error:"POLICY_BLOCK"});if(decision.outcome==="ESCALATE_TO_OWNER")return this.store.advance(state,"ESCALATED",{last_error:"OWNER_AUTHORITY_REQUIRED"});return this.store.advance(state,"READY_TO_MERGE");}
      case "READY_TO_MERGE": return this.store.advance(state,"MERGING");
      case "MERGING": {if(!state.pr||!state.head_sha||!state.decision_id)throw new Error("merge evidence missing");const merge=this.effects.ensureMerge(state.pr,state.head_sha,state.base_sha,state.decision_id);if(!/^[0-9a-f]{40}$/.test(merge))throw new Error("merge evidence invalid");state=this.store.effect(state,`merge:${merge}`);return this.store.advance(state,"MERGED",{head_sha:merge});}
      case "MERGED": if(spec.closeout_only)return this.store.advance(state,"TERMINAL_COMPLETED");else if(state.deployment_mode==="INSTALL_ONLY"||state.deployment_mode==="INSTALL_AND_RUNTIME_PILOT")return this.store.advance(state,"INSTALL_PENDING");else if(state.deployment_mode==="DOCUMENTATION_CLOSEOUT")return this.store.advance(state,"CLOSEOUT_PENDING");else return this.store.advance(state,"RUNTIME_VERIFIED");
      case "INSTALL_PENDING": {const result=this.effects.ensureInstall(spec,state.head_sha!);if(result==="LOCAL_PRIVILEGE_REQUIRED")return this.store.advance(state,"ESCALATED",{last_error:"LOCAL_PRIVILEGE_REQUIRED"});state=this.store.effect(state,`install:${state.head_sha}`);return this.store.advance(state,"INSTALLING");}
      case "INSTALLING": return this.store.advance(state,state.deployment_mode==="INSTALL_AND_RUNTIME_PILOT"?"RUNTIME_PILOT_PENDING":"RUNTIME_VERIFIED");
      case "RUNTIME_PILOT_PENDING": return this.store.advance(state,"RUNTIME_PILOT_RUNNING");
      case "RUNTIME_PILOT_RUNNING": {const result=this.effects.ensureRuntimePilot(spec,state.head_sha!);if(result==="PENDING")return state;state=this.store.effect(state,`pilot:${state.head_sha}`);return this.store.advance(state,"RUNTIME_VERIFIED");}
      case "RUNTIME_VERIFIED": return this.store.advance(state,"CLOSEOUT_PENDING");
      case "CLOSEOUT_PENDING": {const result=await this.effects.ensureCloseout(spec,state.head_sha!);if(result==="PENDING")return state;state=this.store.effect(state,`closeout:${state.roadmap_item_id}`);return this.store.advance(state,"CLOSEOUT_MERGED");}
      case "CLOSEOUT_MERGED": return this.store.advance(state,"TERMINAL_COMPLETED");
      case "TERMINAL_COMPLETED": this.effects.discoverNext(state.roadmap_item_id); return state;
      default:return state;
    }
  }
}
