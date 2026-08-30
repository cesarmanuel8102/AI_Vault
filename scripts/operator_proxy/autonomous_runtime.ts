import {join} from "node:path";
import {createHash} from "node:crypto";
import {GitHubBus} from "./github_bus.js";
import {sequenceRoadmap} from "./roadmap_sequencer.js";
import {LifecycleStore} from "./lifecycle_store.js";
import {AutonomousFlow} from "./autonomous_flow.js";
import {ProductionEffects} from "./production_effects.js";
import {Ledger} from "./decision_ledger.js";
import {RequestCoordinator} from "./request_coordinator.js";
import {ExternalEffectBoundary} from "./external_effect_guard.js";
import type {LifecycleRecord,ProxySpec} from "./types.js";

const POST_MERGE_STATES=new Set(["MERGED","INSTALL_PENDING","INSTALLING","RUNTIME_PILOT_PENDING","RUNTIME_PILOT_RUNNING","RUNTIME_VERIFIED","CLOSEOUT_PENDING","CLOSEOUT_MERGED","TERMINAL_COMPLETED"]);

export function validatePostMergeBaseAdvance(spec:ProxySpec,state:LifecycleRecord,isAncestor:(oldSha:string,newSha:string)=>boolean){
  const privilegedInstallPending=state.state==="ESCALATED"&&state.last_error==="LOCAL_PRIVILEGE_REQUIRED";
  if(!POST_MERGE_STATES.has(state.state)&&!privilegedInstallPending)return false;
  if(!state.head_sha||!state.completed_effects.includes(`merge:${state.head_sha}`)||state.head_sha!==spec.expected_base_sha&&!isAncestor(state.head_sha,spec.expected_base_sha))throw new Error("post-merge base identity invalid");
  return true;
}

export function resumePrivilegedInstall(bus:GitHubBus,boundary:ExternalEffectBoundary,coordinator:RequestCoordinator,flow:AutonomousFlow,spec:ProxySpec,state:LifecycleRecord){
  boundary.beginPrivilegedInstallResume(spec,state);
  try{
    flow.assertPrivilegedInstallState(state);
    boundary.assertPrivilegedInstallResumeReady();
    if(!coordinator.validatedInstallReceiptDigest(spec,state.head_sha!))return state;
    const path=spec.install_target==="agent_loop_worker"?"scripts/agent_loop/local_worker/agent_worker.py":undefined;
    if(!path)throw new Error("install artifact target invalid");
    const artifactSha256=createHash("sha256").update(Buffer.from(bus.fileAt(path,state.head_sha!),"utf8")).digest("hex");
    return coordinator.install(spec,state.head_sha!,artifactSha256)==="PASS"?flow.resumePrivilegedInstall(state):state;
  }finally{boundary.endPrivilegedInstallResume();}
}

export function reconcilePersistedRoadmapState(bus:GitHubBus,effects:ProductionEffects,store:LifecycleStore,spec:ProxySpec,persisted?:LifecycleRecord){
  if(!persisted)return persisted;
  if(persisted.state==="ESCALATED"&&persisted.last_error==="OWNER_AUTHORITY_REQUIRED"&&persisted.base_sha!==spec.expected_base_sha)return effects.reconcileNegatedRiskEscalation(spec,persisted,store);
  if(persisted.state==="BLOCKED"&&persisted.last_error==="CI_FAILED")return persisted.base_sha!==spec.expected_base_sha?effects.reconcileBlockedCiBase(spec,persisted,store):effects.reconcileBlockedCiChecks(spec,persisted,store);
  if(persisted.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(persisted.last_error??"")&&persisted.pr&&persisted.head_sha&&typeof (effects as any).reconcileExternallyMergedBuilderFailure==="function"){const reconciled=(effects as any).reconcileExternallyMergedBuilderFailure(spec,persisted,store);if(reconciled)return reconciled;}
  if(persisted.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(persisted.last_error??"")&&persisted.repair_cycles===0&&persisted.base_sha!==spec.expected_base_sha){if(!bus.isAncestor(persisted.base_sha,spec.expected_base_sha))throw new Error("initial builder failure base ancestry invalid");return store.resumeInitialBuilderFailureAtAdvancedBase(persisted,spec.expected_base_sha);}
  if(persisted.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(persisted.last_error??"")&&persisted.base_sha!==spec.expected_base_sha)return effects.reconcileBuilderFailureBase(spec,persisted,store);
  if(persisted.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(persisted.last_error??"")&&persisted.base_sha===spec.expected_base_sha&&persisted.repair_cycles===0)return store.resumeInitialBuilderFailure(persisted);
  if(persisted.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(persisted.last_error??"")&&persisted.base_sha===spec.expected_base_sha&&persisted.builder_retry_reason==="BUILDER_FAILURE")return store.resumeRecordedBuilderRetry(persisted);
  if(persisted.base_sha===spec.expected_base_sha)return persisted;
  if(["DISCOVERED","ADMITTED"].includes(persisted.state))return store.rebindUnstartedBase(persisted,spec.expected_base_sha);
  if(["CI_PENDING","REVIEWING"].includes(persisted.state))return effects.reconcileCloseoutState(spec,persisted,store);
  if(persisted.state==="MERGING")return effects.reconcileBlockedCiBase(spec,effects.invalidateFailedMerge(spec,persisted,store),store);
  if(persisted.state==="BUILDING"&&persisted.repair_cycles===1&&persisted.builder_retry_reason==="BUILDER_FAILURE"&&!persisted.pr&&!persisted.head_sha)return effects.reconcileInitialRetryPublishedCandidate(spec,persisted,store);
  if(persisted.state==="BUILDING"&&persisted.repair_cycles>0)return effects.reconcileRepairBase(spec,persisted,store);
  if(validatePostMergeBaseAdvance(spec,persisted,((oldSha,newSha)=>bus.isAncestor(oldSha,newSha))))return store.rebindPostMergeBase(persisted,spec.expected_base_sha);
  return effects.reconcilePreBuildBase(spec,persisted,store);
}

export async function runAutonomousRoadmapTick(bus:GitHubBus,root:string,reviewerRepo:string,boundary:ExternalEffectBoundary){
  const sequenced=sequenceRoadmap(bus);const store=new LifecycleStore(join(root,"lifecycle"));const ledgerRoot=join(root,"decisions");const coordinator=new RequestCoordinator(join(root,"coordination"),boundary.assert.bind(boundary));
  const effects=new ProductionEffects(bus,new Ledger(ledgerRoot),reviewerRepo,root,boundary,coordinator);const flow=new AutonomousFlow(store,effects);let persisted=store.load(sequenced.spec.front_id!);
  persisted=reconcilePersistedRoadmapState(bus,effects,store,sequenced.spec,persisted);
  if(persisted?.state==="ESCALATED"&&persisted.last_error==="LOCAL_PRIVILEGE_REQUIRED")persisted=resumePrivilegedInstall(bus,boundary,coordinator,flow,sequenced.spec,persisted);
  let state=await flow.step(sequenced.spec);for(let i=0;i<24;i++){if(["CI_PENDING","BUILDING","RUNTIME_PILOT_RUNNING","CLOSEOUT_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=await flow.step(sequenced.spec);}
  return state;
}
