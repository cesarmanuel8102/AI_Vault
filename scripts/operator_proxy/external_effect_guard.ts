import {existsSync} from "node:fs";
import {join} from "node:path";
import type {LifecycleRecord,ProxySpec} from "./types.js";
import type {GitHubBus} from "./github_bus.js";
import {AUTH,REPO} from "./policy_engine.js";
import {validBlockedCiEffectChain,validPrivilegedInstallEffectChain} from "./lifecycle_store.js";

export const EXTERNAL_EFFECT_REGISTRY=["issue_create","issue_modify","label_modify","comment_publish","branch_create","builder_execute","commit_create","push","pr_create","workflow_dispatch","reviewer_execute","decision_persist","findings_publish","repair_request","merge","installation_request","installation_receipt","pilot_request","pilot_receipt","closeout_create","next_item_activate"] as const;
export type ExternalEffect=typeof EXTERNAL_EFFECT_REGISTRY[number];
export interface EffectContext {issue?:number;pr?:number;expected_head?:string;observed_head?:string}
export type EffectAssertion=(effect:ExternalEffect,context?:EffectContext)=>void;

interface BlockedCiRecovery {
  frontId:string;issue:number;pr:number;oldBase:string;newBase:string;oldHead:string;priorState:"BLOCKED"|"ESCALATED";observedHead?:string;nextHead?:string;
}

const POST_MERGE=new Set(["MERGED","INSTALL_PENDING","INSTALLING","RUNTIME_PILOT_PENDING","RUNTIME_PILOT_RUNNING","RUNTIME_VERIFIED","CLOSEOUT_PENDING","CLOSEOUT_MERGED","TERMINAL_COMPLETED"]);

export class ExternalEffectBoundary {
  private spec?:ProxySpec;private lifecycle?:LifecycleRecord;
  private blockedCiRecovery?:BlockedCiRecovery;
  private blockedCiRepair=false;
  private privilegedInstallResume=false;
  constructor(readonly root:string,readonly bus:GitHubBus,readonly leaseOwned:()=>boolean){}
  bind(spec:ProxySpec,lifecycle:LifecycleRecord){this.spec=spec;this.lifecycle=lifecycle;this.blockedCiRecovery=undefined;this.blockedCiRepair=false;this.privilegedInstallResume=false;}
  beginPrivilegedInstallResume(spec:ProxySpec,state:LifecycleRecord){
    const exact=state.state==="ESCALATED"&&state.last_error==="LOCAL_PRIVILEGE_REQUIRED"&&spec.install_target==="agent_loop_worker"&&["INSTALL_ONLY","INSTALL_AND_RUNTIME_PILOT"].includes(spec.deployment_mode??"")&&state.deployment_mode===spec.deployment_mode&&state.front_id===spec.front_id&&state.roadmap_item_id===spec.roadmap_item_id&&state.base_sha===spec.expected_base_sha&&Number.isInteger(state.issue)&&state.issue!>0&&Number.isInteger(state.pr)&&state.pr!>0&&state.repair_cycles===0&&!!state.builder_session&&!!state.reviewer_session&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(state.decision_id??"")&&/^[0-9a-f]{40}$/.test(state.head_sha??"")&&validPrivilegedInstallEffectChain(state);
    if(!exact)throw new Error("privileged install receipt boundary denied");
    if(this.bus.branchHead("codex/own-capital-sustainable-return")!==spec.expected_base_sha)throw new Error("external effect base changed");
    if(this.bus.issuePaused(state.issue!))throw new Error("external effect paused by GitHub label");
    this.bind(spec,state);this.privilegedInstallResume=true;
  }
  assertPrivilegedInstallResumeReady(){if(!this.privilegedInstallResume)throw new Error("privileged install receipt boundary denied");this.assert("installation_receipt");}
  endPrivilegedInstallResume(){this.privilegedInstallResume=false;}
  beginBlockedCiRecovery(spec:ProxySpec,state:LifecycleRecord){
    const exact=state.state==="BLOCKED"&&state.last_error==="CI_FAILED"&&Number.isInteger(state.issue)&&state.issue!>0&&Number.isInteger(state.pr)&&state.pr!>0&&Number.isInteger(state.repair_cycles)&&state.repair_cycles>=0&&state.repair_cycles<=2&&!!state.builder_session&&!state.reviewer_session&&!state.decision_id&&/^[0-9a-f]{40}$/.test(state.base_sha)&&/^[0-9a-f]{40}$/.test(state.head_sha??"")&&state.base_sha!==spec.expected_base_sha&&validBlockedCiEffectChain(state);
    if(!exact||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("blocked CI recovery boundary denied");
    this.bind(spec,state);this.blockedCiRecovery={frontId:state.front_id,issue:state.issue!,pr:state.pr!,oldBase:state.base_sha,newBase:spec.expected_base_sha,oldHead:state.head_sha!,priorState:"BLOCKED"};
  }
  beginNegatedRiskRecovery(spec:ProxySpec,state:LifecycleRecord){
    const exact=state.state==="ESCALATED"&&state.last_error==="OWNER_AUTHORITY_REQUIRED"&&Number.isInteger(state.issue)&&state.issue!>0&&Number.isInteger(state.pr)&&state.pr!>0&&state.repair_cycles===0&&!!state.builder_session&&!!state.reviewer_session&&!!state.decision_id&&/^[0-9a-f]{40}$/.test(state.base_sha)&&/^[0-9a-f]{40}$/.test(state.head_sha??"")&&state.base_sha!==spec.expected_base_sha&&validBlockedCiEffectChain(state);
    if(!exact||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("negated risk recovery boundary denied");
    this.bind(spec,state);this.blockedCiRecovery={frontId:state.front_id,issue:state.issue!,pr:state.pr!,oldBase:state.base_sha,newBase:spec.expected_base_sha,oldHead:state.head_sha!,priorState:"ESCALATED"};
  }
  bindBlockedCiRecoveryObservedHead(observedHead:string){
    const recovery=this.blockedCiRecovery,spec=this.spec;
    if(!recovery||!spec||!/^[0-9a-f]{40}$/.test(observedHead)||observedHead===recovery.oldHead||!spec.work_branch)throw new Error("blocked CI observed head denied");
    const current=this.bus.prIdentity(recovery.pr),files=(current.files??[]).map((entry:any)=>String(entry.path));
    const allowed=(path:string)=>spec.allowed_paths.some(prefix=>prefix.endsWith("/")?path.startsWith(prefix):path===prefix)&&!spec.forbidden_paths.some(prefix=>path===prefix||path.startsWith(prefix.endsWith("/")?prefix:`${prefix}/`));
    const exact=current.author?.login===REPO.split("/",1)[0]&&current.baseRefName==="codex/own-capital-sustainable-return"&&[recovery.oldBase,recovery.newBase].includes(current.baseRefOid)&&current.headRefName===spec.work_branch&&current.headRefOid===observedHead&&current.headRepository?.nameWithOwner===REPO&&current.isCrossRepository===false&&current.isDraft===true&&current.state==="OPEN"&&["MERGEABLE","UNKNOWN"].includes(current.mergeable)&&files.length>0&&files.every(allowed)&&this.bus.remoteBranchHead(spec.work_branch)===observedHead&&this.bus.isAncestor(recovery.oldHead,observedHead);
    if(!exact)throw new Error("blocked CI observed head identity invalid");
    recovery.observedHead=observedHead;
  }
  bindBlockedCiRecoveryHead(nextHead:string){if(!this.blockedCiRecovery||!/^[0-9a-f]{40}$/.test(nextHead)||nextHead===this.blockedCiRecovery.oldHead)throw new Error("blocked CI recovery head denied");this.blockedCiRecovery.nextHead=nextHead;}
  endBlockedCiRecovery(){this.blockedCiRecovery=undefined;}
  beginBlockedCiRepair(spec:ProxySpec,state:LifecycleRecord){
    const exact=state.state==="BLOCKED"&&state.last_error==="CI_FAILED"&&state.base_sha===spec.expected_base_sha&&Number.isInteger(state.issue)&&state.issue!>0&&Number.isInteger(state.pr)&&state.pr!>0&&Number.isInteger(state.repair_cycles)&&state.repair_cycles>=0&&state.repair_cycles<2&&!!state.builder_session&&!state.reviewer_session&&!state.decision_id&&/^[0-9a-f]{40}$/.test(state.head_sha??"")&&validBlockedCiEffectChain(state);
    if(!exact||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("blocked CI repair boundary denied");
    if(this.bus.branchHead("codex/own-capital-sustainable-return")!==spec.expected_base_sha||this.bus.issuePaused(state.issue!))throw new Error("blocked CI repair identity changed");
    const pr=this.bus.prIdentity(state.pr!);if(pr.headRefOid!==state.head_sha)throw new Error("blocked CI repair head changed");
    this.bind(spec,state);this.blockedCiRepair=true;
  }
  endBlockedCiRepair(){this.blockedCiRepair=false;}
  bindPostMerge(merge:string){if(!this.lifecycle||!/^[0-9a-f]{40}$/.test(merge))throw new Error("post-merge boundary evidence invalid");this.lifecycle={...this.lifecycle,state:"MERGED",head_sha:merge};}
  assert(effect:ExternalEffect,context:EffectContext={}){
    if(!EXTERNAL_EFFECT_REGISTRY.includes(effect))throw new Error("external effect is not registered");
    const spec=this.spec,state=this.lifecycle;if(!spec||!state)throw new Error("external effect context missing");
    if(!this.leaseOwned())throw new Error("external effect lease lost");
    if(existsSync(join(this.root,"state","PAUSE")))throw new Error("external effect paused locally");
    if(spec.authorization_id!==AUTH||spec.repository!==REPO||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("external effect authorization invalid");
    if(state.state==="BLOCKED"||state.state==="ESCALATED"){
      if(this.privilegedInstallResume&&state.state==="ESCALATED"&&state.last_error==="LOCAL_PRIVILEGE_REQUIRED"&&effect==="installation_receipt"){
        if(this.bus.branchHead("codex/own-capital-sustainable-return")!==spec.expected_base_sha)throw new Error("external effect base changed");
        if(state.issue&&this.bus.issuePaused(state.issue))throw new Error("external effect paused by GitHub label");
        return;
      }
      if(this.blockedCiRepair&&state.state==="BLOCKED"&&state.last_error==="CI_FAILED"){
        const allowed=new Set<ExternalEffect>(["decision_persist","findings_publish","repair_request","comment_publish","label_modify"]);
        if(!allowed.has(effect)||(context.issue!==undefined&&context.issue!==state.issue)||(context.pr!==undefined&&context.pr!==state.pr)||(context.expected_head!==undefined&&context.expected_head!==state.head_sha))throw new Error("external effect denied by blocked CI repair");
        if(this.bus.branchHead("codex/own-capital-sustainable-return")!==spec.expected_base_sha||state.issue&&this.bus.issuePaused(state.issue))throw new Error("blocked CI repair identity changed");
        if(state.pr&&this.bus.prIdentity(state.pr).headRefOid!==state.head_sha)throw new Error("blocked CI repair head changed");
        return;
      }
      const recovery=this.blockedCiRecovery;
      if(!recovery||recovery.priorState!==state.state||recovery.frontId!==state.front_id||recovery.issue!==state.issue||recovery.pr!==state.pr||recovery.oldBase!==state.base_sha||recovery.newBase!==spec.expected_base_sha||recovery.oldHead!==state.head_sha)throw new Error("external effect denied by lifecycle state");
      if(this.bus.branchHead("codex/own-capital-sustainable-return")!==recovery.newBase)throw new Error("external effect base changed");
      if((context.issue??state.issue)!==recovery.issue||(context.pr??state.pr)!==recovery.pr||this.bus.issuePaused(recovery.issue))throw new Error("blocked CI recovery identity changed");
      const current=this.bus.prIdentity(recovery.pr);
      if(effect==="push"&&!recovery.nextHead&&/^[0-9a-f]{40}$/.test(context.expected_head??"")&&context.expected_head!==recovery.oldHead){
        if(current.headRefOid===recovery.oldHead&&!context.observed_head)return;
        const observed=context.observed_head;
        const observedAuthorized=spec.executor==="agent_loop"||recovery.observedHead===observed;
        if(observedAuthorized&&/^[0-9a-f]{40}$/.test(observed??"")&&observed!==context.expected_head&&current.headRefOid===observed&&this.bus.isAncestor(recovery.oldHead,observed!))return;
      }
      if(effect==="issue_modify"&&recovery.nextHead&&context.expected_head===recovery.nextHead&&current.headRefOid===recovery.nextHead)return;
      throw new Error("external effect denied by lifecycle state");
    }
    const persistedMerge=POST_MERGE.has(state.state)&&!!state.head_sha&&state.completed_effects.includes(`merge:${state.head_sha}`);
    if(persistedMerge&&state.base_sha!==spec.expected_base_sha)throw new Error("external effect post-merge binding changed");
    const expectedBase=POST_MERGE.has(state.state)&&state.head_sha&&!persistedMerge?state.head_sha:spec.expected_base_sha;
    if(this.bus.branchHead("codex/own-capital-sustainable-return")!==expectedBase)throw new Error("external effect base changed");
    const issue=context.issue??state.issue;if(issue&&this.bus.issuePaused(issue))throw new Error("external effect paused by GitHub label");
    const pr=context.pr??state.pr;const expectedHead=context.expected_head??(!POST_MERGE.has(state.state)?state.head_sha:undefined);
    if(pr&&expectedHead){
      const current=this.bus.prIdentity(pr);
      const repairPush=effect==="push"&&state.state==="BUILDING"&&state.repair_cycles>0&&state.repair_cycles<=2&&context.issue===state.issue&&pr===state.pr&&!!state.head_sha&&!!state.reviewer_session&&!!state.decision_id&&context.observed_head===state.head_sha&&current.headRefOid===state.head_sha&&expectedHead!==state.head_sha&&/^[0-9a-f]{40}$/.test(expectedHead);
      if(effect==="push"&&state.state==="BUILDING"&&state.repair_cycles>0&&!repairPush)throw new Error("external effect head changed");
      if(!repairPush&&current.headRefOid!==expectedHead)throw new Error("external effect head changed");
    }
  }
}
