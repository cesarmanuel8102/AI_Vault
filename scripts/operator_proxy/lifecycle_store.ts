import {appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync} from "node:fs";
import {join} from "node:path";
import type {LifecycleRecord, LifecycleState, OwnerAuthorizedCriticalMerge} from "./types.js";
import {CONTROL_PLANE_VERSION} from "./lineage.js";
import {transitionLifecycle} from "./state_machine.js";
import {redactSensitiveData,safeJson} from "./redaction.js";
import {OwnerRepairReceiptLedger,type OwnerGrantReceiptEvent} from "./owner_repair_receipt_ledger.js";
import {OwnerCriticalMergeReceiptLedger,type OwnerCriticalMergeReceiptEvent} from "./owner_critical_merge_receipt_ledger.js";

const safeFront = (front: string) => {
  if (!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(front)) throw new Error("front id invalid");
  return front;
};
export function validBlockedCiEffectChain(record:LifecycleRecord){
  const effects=record.completed_effects;if(effects.length<2||effects.length>10||effects[0]!==`issue:${record.issue}`||!/^build:[0-9a-f]{40}$/.test(effects[1]??"")||new Set(effects).size!==effects.length)return false;
  if(effects.length===2)return effects[1]===`build:${record.head_sha}`;
  return effects.slice(2).every(effect=>/^base-sync:[0-9a-f]{40}$/.test(effect))&&effects.at(-1)===`base-sync:${record.head_sha}`;
}
function validExpandableBlockedCiEffectChain(record:LifecycleRecord){
  const effects=record.completed_effects;
  return effects.length>=2&&effects.length<=64&&effects[0]===`issue:${record.issue}`&&/^build:[0-9a-f]{40}$/.test(effects[1]??"")&&new Set(effects).size===effects.length&&effects.slice(2).every(effect=>/^base-sync:[0-9a-f]{40}$/.test(effect))&&effects.at(-1)===`base-sync:${record.head_sha}`;
}
export function validPrivilegedInstallEffectChain(record:LifecycleRecord){
  const effects=record.completed_effects;
  if(!record.issue||!record.head_sha||effects.length<3||effects.length>11||effects[0]!==`issue:${record.issue}`||!/^build:[0-9a-f]{40}$/.test(effects[1]??"")||effects.at(-1)!==`merge:${record.head_sha}`||new Set(effects).size!==effects.length)return false;
  return effects.slice(2,-1).every(effect=>/^base-sync:[0-9a-f]{40}$/.test(effect));
}
export function validBridgeAdoptionState(record:LifecycleRecord){
  const hasPositiveIssue=Number.isInteger(record.issue)&&record.issue! > 0;
  const hasPositivePr=Number.isInteger(record.pr)&&record.pr! > 0;
  return ["CI_PENDING","REVIEWING"].includes(record.state)&&hasPositiveIssue&&hasPositivePr&&record.repair_cycles===0&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&record.completed_effects.length===2&&validBlockedCiEffectChain(record);
}

export class LifecycleStore {
  constructor(readonly root: string) { mkdirSync(root, {recursive:true}); }
  path(front: string) { return join(this.root, `${safeFront(front)}.json`); }
  load(front: string): LifecycleRecord | undefined {
    const path=this.path(front); if(!existsSync(path)) return undefined;
    const record=JSON.parse(readFileSync(path,"utf8")) as LifecycleRecord;
    const receiptAnchors=[record.builder_receipt_head_sha,record.builder_receipt_base_sha];
    if(record.schema_version!==1||record.front_id!==front||!Array.isArray(record.completed_effects)||receiptAnchors.some(value=>value!==undefined)&&!receiptAnchors.every(value=>typeof value==="string"&&/^[0-9a-f]{40}$/.test(value))) throw new Error("lifecycle state invalid");
    return record;
  }
  save(record: LifecycleRecord) {
    record=redactSensitiveData(record);
    const persisted={...record,state_writer_control_plane_version:CONTROL_PLANE_VERSION};
    const path=this.path(persisted.front_id); const tmp=`${path}.${process.pid}.tmp`;
    writeFileSync(tmp,`${JSON.stringify(persisted,null,2)}\n`,{flag:"wx"}); renameSync(tmp,path);
    appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_saved",front_id:persisted.front_id,state:persisted.state,updated_utc:persisted.updated_utc})}\n`);
  }
  advance(record: LifecycleRecord, next: LifecycleState, patch: Partial<LifecycleRecord>={}): LifecycleRecord {
    if(record.state==="OWNER_REPAIR_AUTHORIZED"||next==="OWNER_REPAIR_AUTHORIZED")throw new Error("owner payload repair transition requires dedicated operation");
    if(record.state==="ESCALATED"&&next==="MERGING")throw new Error("owner critical merge transition requires dedicated operation");
    const updated={...record,...patch,state:transitionLifecycle(record.state,next),updated_utc:new Date().toISOString()}; this.save(updated); return updated;
  }
  beginOwnerCriticalMerge(record:LifecycleRecord,ledger:OwnerCriticalMergeReceiptLedger,authorization:OwnerAuthorizedCriticalMerge,receipt:OwnerCriticalMergeReceiptEvent):LifecycleRecord {
    const exact=record.state==="ESCALATED"&&record.last_error==="OWNER_AUTHORITY_REQUIRED"&&Number.isInteger(record.repair_cycles)&&record.repair_cycles>=0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.issue===authorization.issue&&record.pr===authorization.pr&&record.front_id===authorization.front_id&&record.base_sha===authorization.base_sha&&record.head_sha===authorization.head_sha&&record.decision_id===authorization.policy_decision_id&&!record.owner_critical_merge&&receipt.phase==="CONSUMED"&&receipt.critical_merge_key===authorization.critical_merge_key&&receipt.authorization_id===authorization.authorization_id&&receipt.repository===authorization.repository&&receipt.issue===authorization.issue&&receipt.front_id===authorization.front_id&&receipt.pr===authorization.pr&&receipt.base_branch===authorization.base_branch&&receipt.base_sha===authorization.base_sha&&receipt.head_branch===authorization.head_branch&&receipt.head_sha===authorization.head_sha&&receipt.policy_decision_id===authorization.policy_decision_id&&receipt.policy_decision_key===authorization.policy_decision_key;
    if(!exact)throw new Error("owner critical merge lifecycle authorization denied");
    try{ledger.assertCurrentConsumedReceipt(receipt);}catch{throw new Error("owner critical merge lifecycle authorization denied");}
    const updated={...record,state:transitionLifecycle(record.state,"MERGING"),owner_critical_merge:{critical_merge_key:receipt.critical_merge_key,consumed_event_sha256:receipt.event_sha256},updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_owner_critical_merge_authorized",front_id:record.front_id,issue:record.issue,pr:record.pr,critical_merge_key:receipt.critical_merge_key,consumed_event_sha256:receipt.event_sha256,repair_cycles:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  authorizeOwnerPayloadRepair(record:LifecycleRecord,ledger:OwnerRepairReceiptLedger,receipt:OwnerGrantReceiptEvent):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&record.repair_cycles===2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.head_sha&&record.completed_effects.length>=2&&receipt.phase==="CONSUMED"&&receipt.front_id===record.front_id&&receipt.failed_head_sha===record.head_sha&&!!receipt.build_attempt_id&&!record.owner_payload_repair;
    if(!exact)throw new Error("owner payload repair authorization denied");
    try{ledger.assertCurrentConsumedReceipt(receipt);}catch{throw new Error("owner payload repair authorization denied");}
    const updated={...record,state:transitionLifecycle(record.state,"OWNER_REPAIR_AUTHORIZED"),owner_payload_repair:{grant_key:receipt.grant_key,consumed_event_sha256:receipt.event_sha256,build_attempt_id:receipt.build_attempt_id!},updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_owner_payload_repair_authorized",front_id:record.front_id,grant_key:receipt.grant_key,consumed_event_sha256:receipt.event_sha256,build_attempt_id:receipt.build_attempt_id,repair_cycles:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  beginOwnerPayloadRepairBuild(record:LifecycleRecord,receipt:OwnerGrantReceiptEvent):LifecycleRecord {
    const binding=record.owner_payload_repair,exact=record.state==="OWNER_REPAIR_AUTHORIZED"&&record.repair_cycles===2&&!!binding&&receipt.phase==="CONSUMED"&&binding.grant_key===receipt.grant_key&&binding.consumed_event_sha256===receipt.event_sha256&&binding.build_attempt_id===receipt.build_attempt_id&&receipt.front_id===record.front_id&&receipt.failed_head_sha===record.head_sha;
    if(!exact)throw new Error("owner payload repair build denied");
    const updated={...record,state:transitionLifecycle(record.state,"BUILDING"),last_error:undefined,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_owner_payload_repair_build_started",front_id:record.front_id,grant_key:binding.grant_key,consumed_event_sha256:binding.consumed_event_sha256,build_attempt_id:binding.build_attempt_id,repair_cycles:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  adoptOwnerPayloadRepairCandidate(record:LifecycleRecord,candidate:{pr:number;head_sha:string;builder_session:string;grant_key:string;build_attempt_id:string;consumed_event_sha256:string}):LifecycleRecord {
    const binding=record.owner_payload_repair,exact=record.state==="BUILDING"&&record.last_error===undefined&&record.repair_cycles===2&&!!binding&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&candidate.pr===record.pr&&/^[0-9a-f]{40}$/.test(candidate.head_sha)&&candidate.head_sha!==record.head_sha&&!!candidate.builder_session&&binding.grant_key===candidate.grant_key&&binding.build_attempt_id===candidate.build_attempt_id&&binding.consumed_event_sha256===candidate.consumed_event_sha256;
    if(!exact)throw new Error("owner payload repair candidate adoption denied");
    const updated={...record,state:transitionLifecycle(record.state,"PR_CREATED"),head_sha:candidate.head_sha,builder_session:candidate.builder_session,builder_receipt_head_sha:undefined,builder_receipt_base_sha:undefined,reviewer_session:undefined,decision_id:undefined,last_error:undefined,last_error_detail:undefined,builder_retry_reason:undefined,completed_effects:[`issue:${record.issue}`,`build:${candidate.head_sha}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_owner_payload_repair_candidate_adopted",front_id:record.front_id,issue:record.issue,pr:record.pr,old_head_sha:record.head_sha,new_head_sha:candidate.head_sha,grant_key:binding.grant_key,build_attempt_id:binding.build_attempt_id,repair_cycles:updated.repair_cycles,updated_utc:updated.updated_utc})}\n`);return this.advance(updated,"CI_PENDING");
  }
  effect(record: LifecycleRecord, key: string): LifecycleRecord {
    if(!/^[A-Za-z0-9][A-Za-z0-9:._-]{2,159}$/.test(key)) throw new Error("effect key invalid");
    if(record.completed_effects.includes(key)) return record;
    const updated={...record,completed_effects:[...record.completed_effects,key],updated_utc:new Date().toISOString()}; this.save(updated); return updated;
  }
  compactBuilderFailureEffectChain(record:LifecycleRecord,decisionHead:string):LifecycleRecord {
    if(record.completed_effects.length<=10)return record;
    const decisionEffect=`base-sync:${decisionHead}`;
    const currentEffect=`base-sync:${record.head_sha}`;
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&/^[0-9a-f]{40}$/.test(decisionHead)&&validExpandableBlockedCiEffectChain(record)&&record.completed_effects.includes(decisionEffect)&&record.completed_effects.at(-1)===currentEffect;
    if(!exact)throw new Error("builder failure effect-chain compaction denied");
    const retained=[record.completed_effects[0]!,record.completed_effects[1]!,...(decisionEffect===currentEffect?[currentEffect]:[decisionEffect,currentEffect])];
    const updated={...record,completed_effects:retained,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_builder_failure_effect_chain_compacted",front_id:record.front_id,issue:record.issue,pr:record.pr,decision_id:record.decision_id,decision_head_sha:decisionHead,current_head_sha:record.head_sha,discarded_effects:record.completed_effects.filter(effect=>!retained.includes(effect)),retained_effects:retained,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  repairBuild(record:LifecycleRecord,head:string):LifecycleRecord {
    const exact=record.state==="BUILDING"&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.head_sha&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(head)||head===record.head_sha)throw new Error("repair build evidence denied");
    const updated={...record,completed_effects:[`issue:${record.issue}`,`build:${head}`],updated_utc:new Date().toISOString()};
    appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_repair_build_replaced",front_id:record.front_id,issue:record.issue,pr:record.pr,old_head_sha:record.head_sha,new_head_sha:head,decision_id:record.decision_id,repair_cycle:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);
    this.save(updated);return updated;
  }
  rebindPreBuildBase(record: LifecycleRecord, nextBase: string): LifecycleRecord {
    const pristine=record.state==="BUILDING"&&Number.isInteger(record.issue)&&record.issue!>0&&record.repair_cycles===0&&!record.pr&&!record.head_sha&&!record.builder_session&&!record.reviewer_session&&!record.decision_id&&record.completed_effects.length===1&&record.completed_effects[0]===`issue:${record.issue}`;
    if(!pristine||!/^[0-9a-f]{40}$/.test(nextBase)||record.base_sha===nextBase)throw new Error("pre-build lifecycle base rebind denied");
    const updated={...record,base_sha:nextBase,updated_utc:new Date().toISOString()};
    appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_prebuild_base_rebound",front_id:record.front_id,issue:record.issue,old_base_sha:record.base_sha,new_base_sha:nextBase,updated_utc:updated.updated_utc})}\n`);
    this.save(updated);return updated;
  }
  rebindPostMergeBase(record:LifecycleRecord,nextBase:string):LifecycleRecord {
    const postMerge=new Set(["MERGED","INSTALL_PENDING","INSTALLING","RUNTIME_PILOT_PENDING","RUNTIME_PILOT_RUNNING","RUNTIME_VERIFIED","CLOSEOUT_PENDING","CLOSEOUT_MERGED","TERMINAL_COMPLETED"]);
    const privilegedInstallPending=record.state==="ESCALATED"&&record.last_error==="LOCAL_PRIVILEGE_REQUIRED"&&["INSTALL_ONLY","INSTALL_AND_RUNTIME_PILOT"].includes(record.deployment_mode)&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.repair_cycles===0&&!!record.builder_session&&!!record.reviewer_session&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(record.decision_id??"")&&validPrivilegedInstallEffectChain(record);
    const exact=(postMerge.has(record.state)||privilegedInstallPending)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&record.completed_effects.includes(`merge:${record.head_sha}`);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||record.base_sha===nextBase)throw new Error("post-merge lifecycle base rebind denied");
    const updated={...record,base_sha:nextBase,updated_utc:new Date().toISOString()};
    appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_postmerge_base_rebound",front_id:record.front_id,old_base_sha:record.base_sha,new_base_sha:nextBase,merge_sha:record.head_sha,state:record.state,updated_utc:updated.updated_utc})}\n`);
    this.save(updated);return updated;
  }
  rebindUnstartedBase(record:LifecycleRecord,nextBase:string):LifecycleRecord {
    const exact=["DISCOVERED","ADMITTED"].includes(record.state)&&!record.issue&&!record.pr&&!record.head_sha&&!record.builder_session&&!record.reviewer_session&&!record.decision_id&&record.completed_effects.length===0;
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||record.base_sha===nextBase)throw new Error("unstarted lifecycle base rebind denied");
    const updated={...record,base_sha:nextBase,updated_utc:new Date().toISOString()};
    appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_unstarted_base_rebound",front_id:record.front_id,old_base_sha:record.base_sha,new_base_sha:nextBase,state:record.state,updated_utc:updated.updated_utc})}\n`);
    this.save(updated);return updated;
  }
  invalidatePostBuildBase(record:LifecycleRecord):LifecycleRecord {
    const exact=["CI_PENDING","REVIEWING"].includes(record.state)&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&Number.isInteger(record.repair_cycles)&&record.repair_cycles>=0&&record.repair_cycles<=2&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact)throw new Error("post-build base invalidation denied");
    const updated={...record,state:transitionLifecycle(record.state,"BLOCKED"),last_error:"CI_FAILED",updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_postbuild_base_invalidated",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,prior_state:record.state,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  invalidateFailedMerge(record:LifecycleRecord,runId:number):LifecycleRecord {
    const exact=record.state==="MERGING"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.repair_cycles===0&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record)&&Number.isInteger(runId)&&runId>0;
    if(!exact)throw new Error("failed merge lifecycle invalidation denied");
    const updated={...record,state:transitionLifecycle(record.state,"BLOCKED"),last_error:"CI_FAILED",reviewer_session:undefined,decision_id:undefined,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_failed_merge_invalidated",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,decision_id:record.decision_id,workflow_run_id:runId,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  recoverBlockedCiBase(record:LifecycleRecord,nextBase:string,nextHead:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&Number.isInteger(record.repair_cycles)&&record.repair_cycles>=0&&record.repair_cycles<=2&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||!/^[0-9a-f]{40}$/.test(nextHead)||record.base_sha===nextBase||record.head_sha===nextHead)throw new Error("blocked CI base recovery denied");
    const updated={...record,state:"CI_PENDING" as const,base_sha:nextBase,head_sha:nextHead,last_error:undefined,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_blocked_ci_base_recovered",front_id:record.front_id,issue:record.issue,pr:record.pr,old_base_sha:record.base_sha,new_base_sha:nextBase,old_head_sha:record.head_sha,new_head_sha:nextHead,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  stageBlockedCiBridge(record:LifecycleRecord,nextBase:string,nextHead:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&typeof record.issue==="number"&&Number.isInteger(record.issue)&&record.issue>0&&typeof record.pr==="number"&&Number.isInteger(record.pr)&&record.pr>0&&Number.isInteger(record.repair_cycles)&&record.repair_cycles>=0&&record.repair_cycles<=2&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||!/^[0-9a-f]{40}$/.test(nextHead)||record.base_sha===nextBase||record.head_sha===nextHead||record.completed_effects.length>=10||record.completed_effects.includes(`base-sync:${nextHead}`))throw new Error("blocked CI bridge adoption denied");
    // Keep the intermediate bridge in memory until branch synchronization succeeds.
    return {...record,base_sha:nextBase,head_sha:nextHead,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`]};
  }
  recoverRepairBase(record:LifecycleRecord,nextBase:string,nextHead:string):LifecycleRecord {
    const exact=record.state==="BUILDING"&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||!/^[0-9a-f]{40}$/.test(nextHead)||record.base_sha===nextBase||record.head_sha===nextHead)throw new Error("repair base recovery denied");
    const updated={...record,base_sha:nextBase,head_sha:nextHead,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_repair_base_recovered",front_id:record.front_id,issue:record.issue,pr:record.pr,old_base_sha:record.base_sha,new_base_sha:nextBase,old_head_sha:record.head_sha,new_head_sha:nextHead,decision_id:record.decision_id,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  recoverBuilderFailureBase(record:LifecycleRecord,nextBase:string,nextHead:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.head_sha&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||!/^[0-9a-f]{40}$/.test(nextHead)||record.base_sha===nextBase||record.head_sha===nextHead)throw new Error("builder failure base recovery denied");
    const updated={...record,state:"BUILDING" as const,base_sha:nextBase,head_sha:nextHead,last_error:undefined,builder_retry_reason:"BUILDER_FAILURE" as const,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_builder_failure_base_recovered",front_id:record.front_id,issue:record.issue,pr:record.pr,old_base_sha:record.base_sha,new_base_sha:nextBase,old_head_sha:record.head_sha,new_head_sha:nextHead,decision_id:record.decision_id,repair_cycle:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  /**
   * Consumes the published authorized repair payload for a BLOCKED
   * builder-failure repair: the payload head replaces the recorded head as a
   * consummated repair build and the record re-enters CI_PENDING with the
   * payload's verified builder session. The immutable decision stays in the
   * ledger; review restarts fresh at the new head.
   */
  consumePublishedRepair(record:LifecycleRecord,nextHead:string,decisionId:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.repair_cycles>0&&record.repair_cycles<=2&&!!record.head_sha&&!!record.builder_session&&!!record.reviewer_session&&record.decision_id===decisionId&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextHead)||nextHead===record.head_sha)throw new Error("published repair consumption denied");
    const updated={...record,state:"CI_PENDING" as const,head_sha:nextHead,builder_session:`builder-recovered:${nextHead}`,builder_receipt_head_sha:undefined,builder_receipt_base_sha:undefined,reviewer_session:undefined,decision_id:undefined,last_error:undefined,last_error_detail:undefined,builder_retry_reason:undefined,completed_effects:[`issue:${record.issue}`,`build:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_repair_build_replaced",front_id:record.front_id,issue:record.issue,pr:record.pr,old_head_sha:record.head_sha,new_head_sha:nextHead,decision_id:decisionId,repair_cycle:record.repair_cycles,consummated_via:"published_authorized_payload",updated_utc:updated.updated_utc})}\n`);return updated;
  }
  resumeRecordedBuilderRetry(record:LifecycleRecord):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&record.builder_retry_reason==="BUILDER_FAILURE"&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.head_sha&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&validBlockedCiEffectChain(record);
    if(!exact)throw new Error("recorded builder retry resume denied");
    const updated={...record,state:"BUILDING" as const,last_error:undefined,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_recorded_builder_retry_resumed",front_id:record.front_id,issue:record.issue,pr:record.pr,head_sha:record.head_sha,decision_id:record.decision_id,repair_cycle:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  adoptBlockedBuilderCandidate(record:LifecycleRecord,head:string,pr:number,builderSession:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&record.builder_retry_reason==="BUILDER_FAILURE"&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&Number.isInteger(pr)&&pr>0&&!!record.head_sha&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(head)||head===record.head_sha||!/^builder-recovered:[0-9a-f]{40}$/.test(builderSession))throw new Error("blocked builder candidate adoption denied");
    const updated={...record,state:"CI_PENDING" as const,pr,head_sha:head,builder_session:builderSession,builder_receipt_head_sha:undefined,builder_receipt_base_sha:undefined,reviewer_session:undefined,decision_id:undefined,last_error:undefined,last_error_detail:undefined,builder_retry_reason:undefined,completed_effects:[`issue:${record.issue}`,`build:${head}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_blocked_builder_candidate_adopted",front_id:record.front_id,issue:record.issue,old_pr:record.pr,new_pr:pr,old_head_sha:record.head_sha,new_head_sha:head,repair_cycle:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  adoptVerifiedSynchronizedBuilderCandidate(record:LifecycleRecord,builderSession:string,receiptHead:string,receiptBase:string):LifecycleRecord {
    const blocked=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&(record.builder_retry_reason===undefined||record.builder_retry_reason==="BUILDER_FAILURE"),advanced=record.state==="BUILDING"&&record.last_error===undefined&&record.builder_retry_reason==="BUILDER_FAILURE";
    const exact=(blocked||advanced)&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.head_sha&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&record.completed_effects.length>=3&&record.completed_effects.at(-1)===`base-sync:${record.head_sha}`&&validBlockedCiEffectChain(record);
    if(!exact||builderSession!==`builder-recovered:${record.head_sha}`||!/^[0-9a-f]{40}$/.test(receiptHead)||!/^[0-9a-f]{40}$/.test(receiptBase))throw new Error("verified synchronized builder candidate adoption denied");
    const updated={...record,state:"CI_PENDING" as const,builder_session:builderSession,builder_receipt_head_sha:receiptHead,builder_receipt_base_sha:receiptBase,reviewer_session:undefined,decision_id:undefined,last_error:undefined,last_error_detail:undefined,builder_retry_reason:undefined,completed_effects:[`issue:${record.issue}`,`build:${record.head_sha}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_verified_synchronized_builder_candidate_adopted",front_id:record.front_id,issue:record.issue,pr:record.pr,head_sha:record.head_sha,receipt_head_sha:receiptHead,receipt_base_sha:receiptBase,repair_cycle:record.repair_cycles,prior_decision_id:record.decision_id,prior_effects:record.completed_effects,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  verifiedSynchronizedBuilderAdoption(record:LifecycleRecord):any {
    const path=join(this.root,"events.jsonl");if(!existsSync(path))throw new Error("verified synchronized builder adoption event missing");
    const matches=readFileSync(path,"utf8").split(/\r?\n/).filter(Boolean).map(line=>{try{return JSON.parse(line);}catch{throw new Error("lifecycle event ledger corrupt");}}).filter(value=>value?.event==="lifecycle_verified_synchronized_builder_candidate_adopted"&&value.front_id===record.front_id&&value.issue===record.issue&&value.pr===record.pr&&value.head_sha===record.head_sha);
    if(matches.length!==1)throw new Error("verified synchronized builder adoption event missing or duplicate");return matches[0];
  }
  recoverFalseBuilderProvenanceRepair(record:LifecycleRecord,adoption:any,receiptHead:string,receiptBase:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="BUILDER_FAILED:UNKNOWN_BUILD_FAILURE"&&record.last_error_detail==="UNCLASSIFIED"&&record.builder_retry_reason==="BUILDER_FAILURE"&&record.repair_cycles===adoption.repair_cycle+1&&record.repair_cycles<=2&&record.reviewer_session===`reviewer:builder-provenance-recovery:${record.head_sha}`&&record.decision_id&&record.completed_effects.length===2&&validBlockedCiEffectChain(record)&&adoption.prior_decision_id&&Array.isArray(adoption.prior_effects)&&adoption.prior_effects[0]===`issue:${record.issue}`&&adoption.prior_effects.at(-1)===`base-sync:${record.head_sha}`;
    if(!exact||!/^[0-9a-f]{40}$/.test(receiptHead)||!/^[0-9a-f]{40}$/.test(receiptBase)||adoption.receipt_head_sha&&adoption.receipt_head_sha!==receiptHead||adoption.receipt_base_sha&&adoption.receipt_base_sha!==receiptBase)throw new Error("false builder provenance repair recovery denied");
    const updated={...record,state:"CI_PENDING" as const,repair_cycles:adoption.repair_cycle,builder_receipt_head_sha:receiptHead,builder_receipt_base_sha:receiptBase,reviewer_session:undefined,decision_id:undefined,last_error:undefined,last_error_detail:undefined,builder_retry_reason:undefined,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_false_builder_provenance_repair_recovered",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,receipt_head_sha:receiptHead,receipt_base_sha:receiptBase,invalidated_decision_id:record.decision_id,restored_repair_cycle:updated.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  resumeInitialBuilderFailure(record:LifecycleRecord):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&record.repair_cycles===0&&Number.isInteger(record.issue)&&record.issue!>0&&!record.pr&&!record.head_sha&&!record.builder_session&&!record.reviewer_session&&!record.decision_id&&!record.builder_retry_reason&&record.completed_effects.length===1&&record.completed_effects[0]===`issue:${record.issue}`;
    if(!exact)throw new Error("initial builder failure resume denied");
    const updated={...record,state:"BUILDING" as const,repair_cycles:1,last_error:undefined,last_error_detail:undefined,builder_retry_reason:"BUILDER_FAILURE" as const,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_initial_builder_failure_resumed",front_id:record.front_id,issue:record.issue,base_sha:record.base_sha,repair_cycle:updated.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  resumeInitialBuilderFailureAtAdvancedBase(record:LifecycleRecord,nextBase:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&record.repair_cycles===0&&Number.isInteger(record.issue)&&record.issue!>0&&!record.pr&&!record.head_sha&&!record.builder_session&&!record.reviewer_session&&!record.decision_id&&!record.builder_retry_reason&&record.completed_effects.length===1&&record.completed_effects[0]===`issue:${record.issue}`;
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||record.base_sha===nextBase)throw new Error("initial builder failure base resume denied");
    const updated={...record,state:"BUILDING" as const,base_sha:nextBase,repair_cycles:1,last_error:undefined,last_error_detail:undefined,builder_retry_reason:"BUILDER_FAILURE" as const,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_initial_builder_failure_base_resumed",front_id:record.front_id,issue:record.issue,old_base_sha:record.base_sha,new_base_sha:nextBase,repair_cycle:updated.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  adoptInitialRetryCandidate(record:LifecycleRecord,nextBase:string,pr:number,candidateHead:string,nextHead:string,builderSession:string):LifecycleRecord {
    const exact=record.state==="BUILDING"&&record.builder_retry_reason==="BUILDER_FAILURE"&&record.repair_cycles===1&&Number.isInteger(record.issue)&&record.issue!>0&&!record.pr&&!record.head_sha&&!record.builder_session&&!record.reviewer_session&&!record.decision_id&&record.completed_effects.length===1&&record.completed_effects[0]===`issue:${record.issue}`;
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||record.base_sha===nextBase||!Number.isInteger(pr)||pr<=0||!/^[0-9a-f]{40}$/.test(candidateHead)||!/^[0-9a-f]{40}$/.test(nextHead)||candidateHead===nextHead||!/^builder-recovered:[0-9a-f]{40}$/.test(builderSession))throw new Error("initial retry candidate adoption denied");
    const updated={...record,state:"CI_PENDING" as const,base_sha:nextBase,pr,head_sha:nextHead,builder_session:builderSession,builder_retry_reason:undefined,completed_effects:[`issue:${record.issue}`,`build:${candidateHead}`,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_initial_retry_candidate_adopted",front_id:record.front_id,issue:record.issue,pr,old_base_sha:record.base_sha,new_base_sha:nextBase,candidate_head_sha:candidateHead,new_head_sha:nextHead,builder_session:builderSession,repair_cycle:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  recoverNegatedRiskEscalation(record:LifecycleRecord,nextBase:string,nextHead:string):LifecycleRecord {
    const exact=record.state==="ESCALATED"&&record.last_error==="OWNER_AUTHORITY_REQUIRED"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.repair_cycles===0&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||!/^[0-9a-f]{40}$/.test(nextHead)||record.base_sha===nextBase||record.head_sha===nextHead)throw new Error("negated risk escalation recovery denied");
    const updated={...record,state:"CI_PENDING" as const,base_sha:nextBase,head_sha:nextHead,last_error:undefined,reviewer_session:undefined,decision_id:undefined,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_negated_risk_escalation_recovered",front_id:record.front_id,issue:record.issue,pr:record.pr,old_base_sha:record.base_sha,new_base_sha:nextBase,old_head_sha:record.head_sha,new_head_sha:nextHead,invalidated_decision_id:record.decision_id,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  recoverBlockedCiChecks(record:LifecycleRecord):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&Number.isInteger(record.repair_cycles)&&record.repair_cycles>=0&&record.repair_cycles<=2&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact)throw new Error("blocked CI check recovery denied");
    const updated={...record,state:"CI_PENDING" as const,last_error:undefined,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_blocked_ci_checks_reopened",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  resumeBlockedCiRepair(record:LifecycleRecord,reviewerSession:string,decisionId:string):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&Number.isInteger(record.repair_cycles)&&record.repair_cycles>=0&&record.repair_cycles<2&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact||!/^reviewer:deterministic-ci:[0-9a-f]{40}$/.test(reviewerSession)||!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(decisionId))throw new Error("blocked CI repair resume denied");
    const updated={...record,state:"REPAIRING" as const,last_error:undefined,reviewer_session:reviewerSession,decision_id:decisionId,repair_cycles:record.repair_cycles+1,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_blocked_ci_repair_resumed",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,decision_id:decisionId,repair_cycle:updated.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  /**
   * CONSUMMATED payload-review repairs only: a repair is consummated exactly
   * when a governed repair build replaced the candidate payload head
   * (lifecycle_repair_build_replaced). Lifecycle/system recovery churn
   * (base-sync, builder-failure recovery, control-plane reconciliation)
   * never counts toward the payload repair budget.
   */
  consummatedPayloadRepairs(issue:number,pr:number):number {
    if(!Number.isInteger(issue)||issue<=0||!Number.isInteger(pr)||pr<=0)throw new Error("payload repair accounting identity invalid");
    const path=join(this.root,"events.jsonl");if(!existsSync(path))return 0;
    const decisions=new Set<string>();
    for(const line of readFileSync(path,"utf8").split(/\r?\n/).filter(Boolean)){
      let value:any;try{value=JSON.parse(line);}catch{throw new Error("lifecycle event ledger corrupt");}
      if(value?.event==="lifecycle_repair_build_replaced"&&value.issue===issue&&value.pr===pr&&typeof value.decision_id==="string"&&value.decision_id)decisions.add(value.decision_id);
    }
    return decisions.size;
  }
  /**
   * Governed resume of an UNCONSUMMATED payload repair. The prior review
   * requested changes, policy recorded an immutable BLOCK on the same head,
   * no new payload head was consummated, and the payload budget remains.
   * The immutable decision is never rewritten; a new candidate head is
   * produced by the ordinary REPAIRING -> BUILDING repair path.
   */
  resumeUnconsummatedRepair(record:LifecycleRecord,consummated:number):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="POLICY_BLOCK"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact||!Number.isInteger(consummated)||consummated<0||consummated>=2||this.consummatedPayloadRepairs(record.issue!,record.pr!)!==consummated)throw new Error("unconsummated repair resume denied");
    const updated={...record,state:"REPAIRING" as const,last_error:undefined,repair_cycles:consummated+1,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_unconsummated_repair_resumed",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,decision_id:record.decision_id,prior_lifecycle_repair_cycles:record.repair_cycles,consummated_payload_repairs:consummated,repair_cycle:updated.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  /**
   * Converts an unconsummated policy-blocked repair into the undecided
   * blocked-CI candidate shape so the generic base synchronization path can
   * carry it across an advanced base. The immutable BLOCK decision remains in
   * the ledger untouched; only the mutable lifecycle pointer is re-shaped.
   */
  /**
   * An undecided post-build record adopts its own PR's advanced payload head
   * at the matching base: the trusted repair payload replaces the stale
   * candidate identity and re-enters CI from scratch.
   */
  adoptAdvancedPayload(record:LifecycleRecord,nextHead:string):LifecycleRecord {
    const exact=["CI_PENDING","REVIEWING"].includes(record.state)&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&Number.isInteger(record.repair_cycles)&&record.repair_cycles>=0&&record.repair_cycles<=2&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextHead)||nextHead===record.head_sha)throw new Error("advanced payload adoption denied");
    const updated={...record,state:"CI_PENDING" as const,head_sha:nextHead,builder_session:undefined,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_advanced_payload_adopted",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,old_head_sha:record.head_sha,new_head_sha:nextHead,repair_cycles:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  beginUnconsummatedRepairSync(record:LifecycleRecord):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="POLICY_BLOCK"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.builder_session&&!!record.reviewer_session&&!!record.decision_id&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact)throw new Error("unconsummated repair synchronization denied");
    const updated={...record,last_error:"CI_FAILED",reviewer_session:undefined,decision_id:undefined,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_unconsummated_repair_synchronizing",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,decision_id:record.decision_id,repair_cycles:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  exhaustBlockedCiRepair(record:LifecycleRecord):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&record.repair_cycles===2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact)throw new Error("blocked CI repair exhaustion denied");
    const updated={...record,last_error:"REPAIR_LIMIT_REACHED",updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_blocked_ci_repair_exhausted",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,repair_cycle:record.repair_cycles,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  adoptBridgeCandidate(record:LifecycleRecord,nextBase:string,nextHead:string):LifecycleRecord {
    // ProductionEffects owns remote PR/commit verification. This persistence
    // transition is one-shot and returns to CI_PENDING without review or policy.
    const exact=validBridgeAdoptionState(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||!/^[0-9a-f]{40}$/.test(nextHead)||record.base_sha===nextBase||record.head_sha!==nextHead)throw new Error("bridge candidate adoption denied");
    const updated={...record,state:"CI_PENDING" as const,base_sha:nextBase,head_sha:nextHead,last_error:undefined,decision_id:undefined,reviewer_session:undefined,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_bridge_candidate_adopted",front_id:record.front_id,issue:record.issue,pr:record.pr,old_base_sha:record.base_sha,new_base_sha:nextBase,old_head_sha:record.head_sha,new_head_sha:nextHead,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  adoptExternallyMergedPr(record:LifecycleRecord,nextBase:string,candidateHead:string,merge:string,reviewerCheck:"review",baseAdvanced:boolean):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&/^BUILDER_FAILED:[A-Z_]+$/.test(record.last_error??"")&&record.repair_cycles>0&&record.repair_cycles<=2&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&/^[0-9a-f]{40}$/.test(nextBase)&&/^[0-9a-f]{40}$/.test(candidateHead)&&/^[0-9a-f]{40}$/.test(merge)&&reviewerCheck==="review"&&!record.completed_effects.includes(`merge:${merge}`)&&record.completed_effects.at(-1)===`base-sync:${record.head_sha}`;
    if(!exact||(!baseAdvanced&&nextBase!==merge)||candidateHead===merge)throw new Error("external merge adoption denied");
    const updated={...record,state:"MERGED" as const,base_sha:nextBase,head_sha:merge,last_error:undefined,last_error_detail:undefined,reviewer_session:undefined,decision_id:undefined,merge_reconciliation:{source:"GITHUB_EXTERNALLY_MERGED_PR" as const,issue:record.issue!,pr:record.pr!,original_base_sha:record.base_sha,original_state_head_sha:record.head_sha!,candidate_head_sha:candidateHead,merge_commit_sha:merge,reviewer_check:reviewerCheck},completed_effects:[...record.completed_effects,`merge:${merge}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_external_merge_reconciled",front_id:record.front_id,issue:record.issue,pr:record.pr,original_base_sha:record.base_sha,original_state_head_sha:record.head_sha,candidate_head_sha:candidateHead,merge_commit_sha:merge,reviewer_check:reviewerCheck,updated_utc:updated.updated_utc})}\n`);return updated;
  }
}
