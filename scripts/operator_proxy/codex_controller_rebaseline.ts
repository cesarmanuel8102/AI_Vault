import {planControllerRebaseline} from "./controller_rebaseline.js";
import {createHash} from "node:crypto";
import type {ControllerRebaselineCanonicalBindingV1,ControllerSupersessionReceiptInputV1,ControllerSupersessionReceiptV1,FunctionalEvidenceAssertionV1,HistoricalAttemptRefV1} from "./types.js";

export interface CodexControllerRebaselineArgs {
  created_utc:string;
  historical:HistoricalAttemptRefV1;
  evidence:FunctionalEvidenceAssertionV1;
  canonical:ControllerRebaselineCanonicalBindingV1;
}
export interface CodexControllerRebaselineDependencies {
  gitShow:(ref:string,path:string)=>Uint8Array;
  loadReceipts:()=>readonly ControllerSupersessionReceiptV1[];
  appendReceipt:(receipt:ControllerSupersessionReceiptInputV1)=>ControllerSupersessionReceiptV1;
  writeSnapshot:(snapshot:Record<string,unknown>)=>void;
}

const digest=(bytes:Uint8Array)=>createHash("sha256").update(bytes).digest("hex");
function pinnedArtifactsMatch(args:CodexControllerRebaselineArgs,deps:CodexControllerRebaselineDependencies):boolean {
  try{
    const ref=args.canonical.canonical_base_sha,manifest=deps.gitShow(ref,"docs/roadmap/BRAIN_101_MANIFEST.json"),roadmap=deps.gitShow(ref,"docs/roadmap/BRAIN_101_ROADMAP.md"),evidence=deps.gitShow(ref,args.evidence.evidence_path);
    const parsed=JSON.parse(Buffer.from(manifest).toString("utf8")) as Record<string,unknown>,items=parsed.roadmap_items as Record<string,unknown>|undefined,item=items?.[args.canonical.roadmap_item_id] as Record<string,unknown>|undefined;
    return digest(manifest)===args.canonical.manifest_sha256&&digest(roadmap)===args.canonical.roadmap_sha256&&digest(evidence)===args.evidence.evidence_sha256&&parsed.repository===args.canonical.repository&&parsed.roadmap_sha256===args.canonical.roadmap_sha256&&item?.status===args.canonical.item_status;
  }catch{return false;}
}

export function runCodexControllerRebaseline(args:CodexControllerRebaselineArgs,deps:CodexControllerRebaselineDependencies){
  if(!pinnedArtifactsMatch(args,deps))throw new Error("rebaseline command blocked");
  const before=deps.loadReceipts(),prior=before.at(-1);
  const initial=planControllerRebaseline({canonical:args.canonical,historical:args.historical,evidence:args.evidence,receipts:before});
  if(initial.status!=="REBASELINE_REQUIRED")throw new Error("rebaseline command blocked");
  const receipt=deps.appendReceipt({schema_version:1,controller:"CODEX_GOVERNED_CONTROLLER",supersession_key:initial.supersession_key!,sequence:before.length,previous_event_sha256:prior?.event_sha256??null,repository:args.canonical.repository,roadmap_item_id:args.canonical.roadmap_item_id,canonical_base_sha:args.canonical.canonical_base_sha,manifest_sha256:args.canonical.manifest_sha256,roadmap_sha256:args.canonical.roadmap_sha256,historical_attempt_sha256:args.historical.historical_sha256,front_id:args.historical.front_id,failed_head_sha:args.historical.failed_head_sha,grant_key:args.historical.grant_key,consumed_event_sha256:args.historical.consumed_event_sha256,build_attempt_id:args.historical.build_attempt_id,functional_evidence_ref:args.evidence.canonical_ref,functional_evidence_path:args.evidence.evidence_path,functional_evidence_sha256:args.evidence.evidence_sha256,functional_evidence_assertion_sha256:args.evidence.assertion_sha256,hard_limits:args.canonical.hard_limits,persistent_agent_loop_enabled:false,created_utc:args.created_utc});
  const final=planControllerRebaseline({canonical:args.canonical,historical:args.historical,evidence:args.evidence,receipts:deps.loadReceipts()});
  if(final.status!=="CLOSEOUT_ALLOWED")throw new Error("rebaseline command blocked");
  deps.writeSnapshot({schema_version:1,mode:"CODEX_GOVERNED_CONTROLLER",canonical_sha:args.canonical.canonical_base_sha,current_item:args.canonical.roadmap_item_id,supersession_key:final.supersession_key,event_sha256:receipt.event_sha256,hard_limits:args.canonical.hard_limits,deferred_agent_loop:true});
  return {status:final.status,supersession_key:final.supersession_key!,event_sha256:receipt.event_sha256,controller:"CODEX_GOVERNED_CONTROLLER" as const};
}
