import {join} from "node:path";
import {GitHubBus} from "./github_bus.js";
import {sequenceRoadmap} from "./roadmap_sequencer.js";
import {LifecycleStore} from "./lifecycle_store.js";
import {AutonomousFlow} from "./autonomous_flow.js";
import {ProductionEffects} from "./production_effects.js";
import {Ledger} from "./decision_ledger.js";
import {RequestCoordinator} from "./request_coordinator.js";

export function runAutonomousRoadmapTick(bus:GitHubBus,root:string,reviewerRepo:string){
  const sequenced=sequenceRoadmap(bus);const store=new LifecycleStore(join(root,"lifecycle"));const ledgerRoot=join(root,"decisions");const coordinator=new RequestCoordinator(join(root,"coordination"));
  const effects=new ProductionEffects(bus,new Ledger(ledgerRoot),reviewerRepo,root,coordinator);const flow=new AutonomousFlow(store,effects);let persisted=store.load(sequenced.spec.front_id!);
  if(persisted?.state==="ESCALATED"&&persisted.last_error==="LOCAL_PRIVILEGE_REQUIRED"&&persisted.head_sha&&coordinator.install(persisted.head_sha)==="PASS")persisted=flow.resumePrivilegedInstall(persisted.front_id);
  let state=flow.step(sequenced.spec);for(let i=0;i<24;i++){if(["CI_PENDING","BUILDING","RUNTIME_PILOT_RUNNING","CLOSEOUT_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=flow.step(sequenced.spec);}
  return state;
}
