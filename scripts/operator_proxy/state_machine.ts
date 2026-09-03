import type {LifecycleState} from "./types.js";

export type State="queued"|"building"|"reviewing"|"repairing"|"blocked"|"escalated"|"completed";
export function transition(s:State,n:State){const ok:Record<State,State[]>={queued:["building","blocked"],building:["reviewing","blocked"],reviewing:["repairing","blocked","escalated","completed"],repairing:["building","blocked"],blocked:[],escalated:[],completed:[]};if(!ok[s].includes(n))throw new Error(`invalid transition ${s}->${n}`);return n;}

const lifecycleTransitions: Record<LifecycleState, LifecycleState[]> = {
  DISCOVERED:["ADMITTED","BLOCKED","ESCALATED"], ADMITTED:["ISSUE_CREATED","BLOCKED","ESCALATED"],
  ISSUE_CREATED:["BUILDING","BLOCKED","ESCALATED"], BUILDING:["PR_CREATED","BLOCKED","ESCALATED"],
  PR_CREATED:["CI_PENDING","BLOCKED"], CI_PENDING:["REVIEWING","BLOCKED"],
  REVIEWING:["REPAIRING","READY_TO_MERGE","BLOCKED","ESCALATED"], REPAIRING:["BUILDING","BLOCKED"],
  READY_TO_MERGE:["MERGING","BLOCKED","ESCALATED"], MERGING:["MERGED","BLOCKED"],
  MERGED:["INSTALL_PENDING","RUNTIME_VERIFIED","CLOSEOUT_PENDING","TERMINAL_COMPLETED","BLOCKED"],
  INSTALL_PENDING:["INSTALLING","ESCALATED","BLOCKED"], INSTALLING:["RUNTIME_PILOT_PENDING","RUNTIME_VERIFIED","BLOCKED"],
  RUNTIME_PILOT_PENDING:["RUNTIME_PILOT_RUNNING","BLOCKED"], RUNTIME_PILOT_RUNNING:["RUNTIME_VERIFIED","BLOCKED"],
  RUNTIME_VERIFIED:["CLOSEOUT_PENDING","TERMINAL_COMPLETED","BLOCKED"], CLOSEOUT_PENDING:["CLOSEOUT_MERGED","BLOCKED","ESCALATED"],
  CLOSEOUT_MERGED:["TERMINAL_COMPLETED","BLOCKED"], TERMINAL_COMPLETED:[], BLOCKED:["OWNER_REPAIR_AUTHORIZED"], OWNER_REPAIR_AUTHORIZED:["BUILDING","BLOCKED"], ESCALATED:["INSTALL_PENDING","BLOCKED"]
};

export function transitionLifecycle(current: LifecycleState, next: LifecycleState): LifecycleState {
  if (!lifecycleTransitions[current].includes(next)) throw new Error(`invalid lifecycle transition ${current}->${next}`);
  return next;
}
