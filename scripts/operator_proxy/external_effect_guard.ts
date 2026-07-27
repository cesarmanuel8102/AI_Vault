import {existsSync} from "node:fs";
import {join} from "node:path";
import type {LifecycleRecord,ProxySpec} from "./types.js";
import type {GitHubBus} from "./github_bus.js";
import {AUTH,REPO} from "./policy_engine.js";

export const EXTERNAL_EFFECT_REGISTRY=["issue_create","issue_modify","label_modify","comment_publish","branch_create","builder_execute","commit_create","push","pr_create","workflow_dispatch","reviewer_execute","decision_persist","findings_publish","repair_request","merge","installation_request","installation_receipt","pilot_request","pilot_receipt","closeout_create","next_item_activate"] as const;
export type ExternalEffect=typeof EXTERNAL_EFFECT_REGISTRY[number];
export interface EffectContext {issue?:number;pr?:number;expected_head?:string}
export type EffectAssertion=(effect:ExternalEffect,context?:EffectContext)=>void;

const POST_MERGE=new Set(["MERGED","INSTALL_PENDING","INSTALLING","RUNTIME_PILOT_PENDING","RUNTIME_PILOT_RUNNING","RUNTIME_VERIFIED","CLOSEOUT_PENDING","CLOSEOUT_MERGED","TERMINAL_COMPLETED"]);

export class ExternalEffectBoundary {
  private spec?:ProxySpec;private lifecycle?:LifecycleRecord;
  constructor(readonly root:string,readonly bus:GitHubBus,readonly leaseOwned:()=>boolean){}
  bind(spec:ProxySpec,lifecycle:LifecycleRecord){this.spec=spec;this.lifecycle=lifecycle;}
  assert(effect:ExternalEffect,context:EffectContext={}){
    if(!EXTERNAL_EFFECT_REGISTRY.includes(effect))throw new Error("external effect is not registered");
    const spec=this.spec,state=this.lifecycle;if(!spec||!state)throw new Error("external effect context missing");
    if(!this.leaseOwned())throw new Error("external effect lease lost");
    if(existsSync(join(this.root,"state","PAUSE")))throw new Error("external effect paused locally");
    if(state.state==="BLOCKED"||state.state==="ESCALATED")throw new Error("external effect denied by lifecycle state");
    if(spec.authorization_id!==AUTH||spec.repository!==REPO||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id)throw new Error("external effect authorization invalid");
    const expectedBase=POST_MERGE.has(state.state)&&state.head_sha?state.head_sha:spec.expected_base_sha;
    if(this.bus.branchHead("codex/own-capital-sustainable-return")!==expectedBase)throw new Error("external effect base changed");
    const issue=context.issue??state.issue;if(issue&&this.bus.issuePaused(issue))throw new Error("external effect paused by GitHub label");
    const pr=context.pr??state.pr;const expectedHead=context.expected_head??(!POST_MERGE.has(state.state)?state.head_sha:undefined);
    if(pr&&expectedHead){const current=this.bus.prIdentity(pr);if(current.headRefOid!==expectedHead)throw new Error("external effect head changed");}
  }
}
