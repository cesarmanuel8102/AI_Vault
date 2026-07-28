import {existsSync} from "node:fs";
import {join} from "node:path";
import type {LifecycleRecord,ProxySpec} from "./types.js";
import type {GitHubBus} from "./github_bus.js";
import {AUTH,REPO} from "./policy_engine.js";

export const EXTERNAL_EFFECT_REGISTRY=["issue_create","issue_modify","label_modify","comment_publish","branch_create","builder_execute","commit_create","push","pr_create","workflow_dispatch","reviewer_execute","decision_persist","findings_publish","repair_request","merge","installation_request","installation_receipt","pilot_request","pilot_receipt","closeout_create","next_item_activate"] as const;
export type ExternalEffect=typeof EXTERNAL_EFFECT_REGISTRY[number];
export interface EffectContext {issue?:number;pr?:number;expected_head?:string}
export type EffectAssertion=(effect:ExternalEffect,context?:EffectContext)=>void;

interface BlockedCiRecovery {
  frontId:string;issue:number;pr:number;oldBase:string;newBase:string;oldHead:string;nextHead?:string;
}

const POST_MERGE=new Set(["MERGED","INSTALL_PENDING","INSTALLING","RUNTIME_PILOT_PENDING","RUNTIME_PILOT_RUNNING","RUNTIME_VERIFIED","CLOSEOUT_PENDING","CLOSEOUT_MERGED","TERMINAL_COMPLETED"]);

export class ExternalEffectBoundary {
  private spec?:ProxySpec;private lifecycle?:LifecycleRecord;
  private blockedCiRecovery?:BlockedCiRecovery;
  constructor(readonly root:string,readonly bus:GitHubBus,readonly leaseOwned:()=>boolean){}
  bind(spec:ProxySpec,lifecycle:LifecycleRecord){this.spec=spec;this.lifecycle=lifecycle;this.blockedCiRecovery=undefined;}
  beginBlockedCiRecovery(spec:ProxySpec,state:LifecycleRecord){
    const exact=state.state==="BLOCKED"&&state.last_error==="CI_FAILED"&&Number.isInteger(state.issue)&&state.issue!>0&&Number.isInteger(state.pr)&&state.pr!>0&&state.repair_cycles===0&&!!state.builder_session&&!state.reviewer_session&&!state.decision_id&&/^[0-9a-f]{40}$/.test(state.base_sha)&&/^[0-9a-f]{40}$/.test(state.head_sha??"")&&state.base_sha!==spec.expected_base_sha&&state.completed_effects.length===2&&state.completed_effects[0]===`issue:${state.issue}`&&state.completed_effects[1]===`build:${state.head_sha}`;
    if(!exact||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("blocked CI recovery boundary denied");
    this.bind(spec,state);this.blockedCiRecovery={frontId:state.front_id,issue:state.issue!,pr:state.pr!,oldBase:state.base_sha,newBase:spec.expected_base_sha,oldHead:state.head_sha!};
  }
  bindBlockedCiRecoveryHead(nextHead:string){if(!this.blockedCiRecovery||!/^[0-9a-f]{40}$/.test(nextHead)||nextHead===this.blockedCiRecovery.oldHead)throw new Error("blocked CI recovery head denied");this.blockedCiRecovery.nextHead=nextHead;}
  endBlockedCiRecovery(){this.blockedCiRecovery=undefined;}
  bindPostMerge(merge:string){if(!this.lifecycle||!/^[0-9a-f]{40}$/.test(merge))throw new Error("post-merge boundary evidence invalid");this.lifecycle={...this.lifecycle,state:"MERGED",head_sha:merge};}
  assert(effect:ExternalEffect,context:EffectContext={}){
    if(!EXTERNAL_EFFECT_REGISTRY.includes(effect))throw new Error("external effect is not registered");
    const spec=this.spec,state=this.lifecycle;if(!spec||!state)throw new Error("external effect context missing");
    if(!this.leaseOwned())throw new Error("external effect lease lost");
    if(existsSync(join(this.root,"state","PAUSE")))throw new Error("external effect paused locally");
    if(spec.authorization_id!==AUTH||spec.repository!==REPO||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("external effect authorization invalid");
    if(state.state==="BLOCKED"){
      const recovery=this.blockedCiRecovery;
      if(!recovery||recovery.frontId!==state.front_id||recovery.issue!==state.issue||recovery.pr!==state.pr||recovery.oldBase!==state.base_sha||recovery.newBase!==spec.expected_base_sha||recovery.oldHead!==state.head_sha)throw new Error("external effect denied by lifecycle state");
      if(this.bus.branchHead("codex/own-capital-sustainable-return")!==recovery.newBase)throw new Error("external effect base changed");
      if((context.issue??state.issue)!==recovery.issue||(context.pr??state.pr)!==recovery.pr||this.bus.issuePaused(recovery.issue))throw new Error("blocked CI recovery identity changed");
      const current=this.bus.prIdentity(recovery.pr);
      if(effect==="push"&&!recovery.nextHead&&/^[0-9a-f]{40}$/.test(context.expected_head??"")&&context.expected_head!==recovery.oldHead&&current.headRefOid===recovery.oldHead)return;
      if(effect==="issue_modify"&&recovery.nextHead&&(!context.expected_head||context.expected_head===recovery.nextHead)&&current.headRefOid===recovery.nextHead)return;
      throw new Error("external effect denied by lifecycle state");
    }
    if(state.state==="ESCALATED")throw new Error("external effect denied by lifecycle state");
    const expectedBase=POST_MERGE.has(state.state)&&state.head_sha?state.head_sha:spec.expected_base_sha;
    if(this.bus.branchHead("codex/own-capital-sustainable-return")!==expectedBase)throw new Error("external effect base changed");
    const issue=context.issue??state.issue;if(issue&&this.bus.issuePaused(issue))throw new Error("external effect paused by GitHub label");
    const pr=context.pr??state.pr;const expectedHead=context.expected_head??(!POST_MERGE.has(state.state)?state.head_sha:undefined);
    if(pr&&expectedHead){const current=this.bus.prIdentity(pr);if(current.headRefOid!==expectedHead)throw new Error("external effect head changed");}
  }
}
