import {join} from "node:path";
import {GitHubBus} from "./github_bus.js";
import {sequenceRoadmap} from "./roadmap_sequencer.js";
import {LifecycleStore} from "./lifecycle_store.js";
import {AutonomousFlow} from "./autonomous_flow.js";
import {ProductionEffects} from "./production_effects.js";
import {Ledger} from "./decision_ledger.js";
import {RequestCoordinator} from "./request_coordinator.js";
import {ExternalEffectBoundary} from "./external_effect_guard.js";

export function runAutonomousRoadmapTick(bus:GitHubBus,root:string,reviewerRepo:string,boundary:ExternalEffectBoundary){
  const sequenced=sequenceRoadmap(bus);const store=new LifecycleStore(join(root,"lifecycle"));const ledgerRoot=join(root,"decisions");const coordinator=new RequestCoordinator(join(root,"coordination"),boundary.assert.bind(boundary));
  const effects=new ProductionEffects(bus,new Ledger(ledgerRoot),reviewerRepo,root,boundary,coordinator);const flow=new AutonomousFlow(store,effects);let persisted=store.load(sequenced.spec.front_id!);
  if(persisted?.state==="BLOCKED"&&persisted.last_error==="CI_FAILED")persisted=persisted.base_sha!==sequenced.spec.expected_base_sha?effects.reconcileBlockedCiBase(sequenced.spec,persisted,store):effects.reconcileBlockedCiChecks(sequenced.spec,persisted,store);
  else if(persisted&&persisted.base_sha!==sequenced.spec.expected_base_sha){if(["CI_PENDING","REVIEWING"].includes(persisted.state)){persisted=store.invalidatePostBuildBase(persisted);persisted=effects.reconcileBlockedCiBase(sequenced.spec,persisted,store);}else if(persisted.state==="MERGING"){persisted=effects.invalidateFailedMerge(sequenced.spec,persisted,store);persisted=effects.reconcileBlockedCiBase(sequenced.spec,persisted,store);}else persisted=effects.reconcilePreBuildBase(sequenced.spec,persisted,store);}
  if(persisted?.state==="ESCALATED"&&persisted.last_error==="LOCAL_PRIVILEGE_REQUIRED"&&persisted.head_sha&&coordinator.install(persisted.head_sha)==="PASS")persisted=flow.resumePrivilegedInstall(persisted.front_id);
  let state=flow.step(sequenced.spec);for(let i=0;i<24;i++){if(["CI_PENDING","BUILDING","RUNTIME_PILOT_RUNNING","CLOSEOUT_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=flow.step(sequenced.spec);}
  return state;
}
