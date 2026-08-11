import {randomUUID} from "node:crypto";
import type {LifecycleRecord, ProxySpec, ReviewerOutput} from "./types.js";
import {LifecycleStore} from "./lifecycle_store.js";

export interface BuildResult {pr:number;head_sha:string;session:string}
export type CiResult="PENDING"|"PASS"|"FAIL";
export interface PolicyResult {outcome:"APPROVE"|"REPAIR"|"BLOCK"|"ESCALATE_TO_OWNER";decision_id:string}
export interface ReviewResult {output:ReviewerOutput;session:string}
export interface AutonomousEffects {
  bindLifecycle(spec:ProxySpec,state:LifecycleRecord):void;
  ensureIssue(spec:ProxySpec):number;
  ensureBuild(spec:ProxySpec,issue:number,session:string,repairCycle:number,previousHead?:string):Promise<BuildResult|"PENDING">;
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
      case "BUILDING": {if(!state.issue)throw new Error("lifecycle issue missing");const session=`builder-${randomUUID()}`;const built=await this.effects.ensureBuild(spec,state.issue,session,state.repair_cycles,state.head_sha);if(built==="PENDING")return state;if(typeof built!=="object"||!built.session||!/^[0-9a-f]{40}$/.test(built.head_sha)||state.repair_cycles>0&&built.head_sha===state.head_sha)throw new Error("builder evidence invalid");state=this.store.effect(state,`build:${built.head_sha}`);return this.store.advance(state,"PR_CREATED",{pr:built.pr,head_sha:built.head_sha,builder_session:built.session,decision_id:undefined,reviewer_session:undefined});}
      case "PR_CREATED": return this.store.advance(state,"CI_PENDING");
      case "CI_PENDING": {if(!state.pr||!state.head_sha)throw new Error("PR evidence missing");const ci=this.effects.ci(state.pr,state.head_sha);if(ci==="PENDING")return state;if(ci==="FAIL")return this.store.advance(state,"BLOCKED",{last_error:"CI_FAILED"});return this.store.advance(state,"REVIEWING");}
      case "REVIEWING": {if(!state.pr||!state.head_sha||!state.builder_session)throw new Error("review evidence missing");const requested=`reviewer-${randomUUID()}`;if(requested===state.builder_session)throw new Error("actor separation failed");const reviewed=this.effects.review(state.pr,state.head_sha,requested),review=reviewed.output,reviewer=reviewed.session;if(!reviewer||reviewer===state.builder_session)throw new Error("actor separation failed");if(review.head_sha!==state.head_sha)throw new Error("review head mismatch");const decision=this.effects.policy(spec,state.issue!,state.pr,state.head_sha,review,state.builder_session,reviewer,state.repair_cycles);if(!/^[0-9a-f-]{36}$/.test(decision.decision_id))throw new Error("policy decision id invalid");state={...state,reviewer_session:reviewer,decision_id:decision.decision_id};if(decision.outcome==="REPAIR"){if(state.repair_cycles>=2)return this.store.advance(state,"BLOCKED",{last_error:"REPAIR_LIMIT_REACHED"});return this.store.advance(state,"REPAIRING",{repair_cycles:state.repair_cycles+1});}if(decision.outcome==="BLOCK")return this.store.advance(state,"BLOCKED",{last_error:"POLICY_BLOCK"});if(decision.outcome==="ESCALATE_TO_OWNER")return this.store.advance(state,"ESCALATED",{last_error:"OWNER_AUTHORITY_REQUIRED"});return this.store.advance(state,"READY_TO_MERGE");}
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
