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
import type {LifecycleRecord, ProxySpec} from "./types.js";

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

// The single reconciliation entry point. The pre-consolidation architecture
// dispatched the same domain states through two parallel if-chains
// (reconcilePersistedRoadmapState and reconcileCloseoutState), each with its
// own incident-shaped ordering. Both now delegate to the one
// snapshot -> lineage -> invariants -> plan pipeline in ProductionEffects.
export function reconcilePersistedRoadmapState(bus:GitHubBus,effects:ProductionEffects,store:LifecycleStore,spec:ProxySpec,persisted?:LifecycleRecord){
  if(!persisted)return persisted;
  // Blocked and escalated lifecycles still need recovery at a matching base.
  if(persisted.base_sha===spec.expected_base_sha&&persisted.state!=="BLOCKED"&&persisted.state!=="ESCALATED")return persisted;
  if(persisted.state==="ESCALATED"&&persisted.last_error==="LOCAL_PRIVILEGE_REQUIRED")return persisted;
  // Effect-free admission is a pure local rebind: no external state is involved.
  if(["DISCOVERED","ADMITTED"].includes(persisted.state)&&!persisted.issue&&!persisted.pr&&!persisted.head_sha&&!persisted.builder_session&&!persisted.reviewer_session&&!persisted.decision_id&&persisted.completed_effects.length===0)return store.rebindUnstartedBase(persisted,spec.expected_base_sha);
  return reconcileUntilStable(effects,store,spec,persisted).state;
}

export type ReconciliationClosureStatus="FLOW_ENTERABLE"|"WAIT_EXTERNAL"|"TERMINAL"|"OWNER_ESCALATION"|"FAIL_CLOSED"|"RECONCILIATION_BUDGET_EXHAUSTED";
export type ReconciliationClosure={state:LifecycleRecord,status:ReconciliationClosureStatus,moves:string[]};

function flowEnterable(spec:ProxySpec,state:LifecycleRecord){
  return state.roadmap_item_id===spec.roadmap_item_id&&state.base_sha===spec.expected_base_sha;
}

function closureSignature(state:LifecycleRecord,plan:any){
  const {updated_utc,state_writer_control_plane_version,...durable}=state as any;
  return JSON.stringify({durable,move:plan?.plan?.move??plan?.move});
}

function closureStatus(state:LifecycleRecord):ReconciliationClosureStatus|undefined{
  if(state.state==="TERMINAL_COMPLETED")return "TERMINAL";
  return undefined;
}

/** Close chained durable recovery moves before handing a state to the flow. */
export function reconcileUntilStable(effects:any,store:LifecycleStore,spec:ProxySpec,persisted:LifecycleRecord,budget=4):ReconciliationClosure{
  let state=persisted;const moves:string[]=[];const seen=new Set<string>();
  for(let iteration=0;iteration<budget;iteration++){
    const terminal=closureStatus(state);if(terminal)return {state,status:terminal,moves};
    if(flowEnterable(spec,state))return {state,status:"FLOW_ENTERABLE",moves};
    if(typeof effects.dryRun!=="function"){
      const updated=effects.reconcile(spec,state,store);return {state:updated,status:flowEnterable(spec,updated)?"FLOW_ENTERABLE":closureStatus(updated)??"WAIT_EXTERNAL",moves};
    }
    const preview=effects.dryRun(spec,state);
    if(preview?.invariants?.violations?.length)throw new Error("reconciliation invariants violated: "+preview.invariants.violations.join(", "));
    const plan=preview?.plan;if(!plan?.move)throw new Error("reconciliation plan missing");
    const signature=closureSignature(state,plan);if(seen.has(signature))throw new Error("reconciliation made no progress");seen.add(signature);
    moves.push(plan.move);
    const returned=effects.reconcile(spec,state,store);
    const reloaded=store.load(spec.front_id!)??returned;
    if(!reloaded)throw new Error("reconciliation state missing after apply");
    if(closureSignature(reloaded,plan)===signature)throw new Error("reconciliation made no progress");
    state=reloaded;
  }
  if(flowEnterable(spec,state))return {state,status:"FLOW_ENTERABLE",moves};
  throw new Error("reconciliation budget exhausted");
}

export async function runAutonomousRoadmapTick(bus:GitHubBus,root:string,reviewerRepo:string,boundary:ExternalEffectBoundary){
  const sequenced=sequenceRoadmap(bus);const store=new LifecycleStore(join(root,"lifecycle"));const ledgerRoot=join(root,"decisions");const coordinator=new RequestCoordinator(join(root,"coordination"),boundary.assert.bind(boundary));
  const effects=new ProductionEffects(bus,new Ledger(ledgerRoot),reviewerRepo,root,boundary,coordinator);const flow=new AutonomousFlow(store,effects);let persisted=store.load(sequenced.spec.front_id!);
  if(persisted)persisted=reconcileUntilStable(effects,store,sequenced.spec,persisted).state;
  if(persisted?.state==="ESCALATED"&&persisted.last_error==="LOCAL_PRIVILEGE_REQUIRED")persisted=resumePrivilegedInstall(bus,boundary,coordinator,flow,sequenced.spec,persisted);
  let state=await flow.step(sequenced.spec);for(let i=0;i<24;i++){if(["CI_PENDING","BUILDING","RUNTIME_PILOT_RUNNING","CLOSEOUT_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=await flow.step(sequenced.spec);}
  return state;
}
