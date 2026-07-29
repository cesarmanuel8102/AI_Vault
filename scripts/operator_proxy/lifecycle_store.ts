import {appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync} from "node:fs";
import {join} from "node:path";
import type {LifecycleRecord, LifecycleState} from "./types.js";
import {transitionLifecycle} from "./state_machine.js";
import {redactSensitiveData,safeJson} from "./redaction.js";

const safeFront = (front: string) => {
  if (!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(front)) throw new Error("front id invalid");
  return front;
};
export function validBlockedCiEffectChain(record:LifecycleRecord){
  const effects=record.completed_effects;if(effects.length<2||effects.length>10||effects[0]!==`issue:${record.issue}`||!/^build:[0-9a-f]{40}$/.test(effects[1]??"")||new Set(effects).size!==effects.length)return false;
  if(effects.length===2)return effects[1]===`build:${record.head_sha}`;
  return effects.slice(2).every(effect=>/^base-sync:[0-9a-f]{40}$/.test(effect))&&effects.at(-1)===`base-sync:${record.head_sha}`;
}

export class LifecycleStore {
  constructor(readonly root: string) { mkdirSync(root, {recursive:true}); }
  path(front: string) { return join(this.root, `${safeFront(front)}.json`); }
  load(front: string): LifecycleRecord | undefined {
    const path=this.path(front); if(!existsSync(path)) return undefined;
    const record=JSON.parse(readFileSync(path,"utf8")) as LifecycleRecord;
    if(record.schema_version!==1||record.front_id!==front||!Array.isArray(record.completed_effects)) throw new Error("lifecycle state invalid");
    return record;
  }
  save(record: LifecycleRecord) {
    record=redactSensitiveData(record);
    const path=this.path(record.front_id); const tmp=`${path}.${process.pid}.tmp`;
    writeFileSync(tmp,`${JSON.stringify(record,null,2)}\n`,{flag:"wx"}); renameSync(tmp,path);
    appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_saved",front_id:record.front_id,state:record.state,updated_utc:record.updated_utc})}\n`);
  }
  advance(record: LifecycleRecord, next: LifecycleState, patch: Partial<LifecycleRecord>={}): LifecycleRecord {
    const updated={...record,...patch,state:transitionLifecycle(record.state,next),updated_utc:new Date().toISOString()}; this.save(updated); return updated;
  }
  effect(record: LifecycleRecord, key: string): LifecycleRecord {
    if(!/^[A-Za-z0-9][A-Za-z0-9:._-]{2,159}$/.test(key)) throw new Error("effect key invalid");
    if(record.completed_effects.includes(key)) return record;
    const updated={...record,completed_effects:[...record.completed_effects,key],updated_utc:new Date().toISOString()}; this.save(updated); return updated;
  }
  rebindPreBuildBase(record: LifecycleRecord, nextBase: string): LifecycleRecord {
    const pristine=record.state==="BUILDING"&&Number.isInteger(record.issue)&&record.issue!>0&&record.repair_cycles===0&&!record.pr&&!record.head_sha&&!record.builder_session&&!record.reviewer_session&&!record.decision_id&&record.completed_effects.length===1&&record.completed_effects[0]===`issue:${record.issue}`;
    if(!pristine||!/^[0-9a-f]{40}$/.test(nextBase)||record.base_sha===nextBase)throw new Error("pre-build lifecycle base rebind denied");
    const updated={...record,base_sha:nextBase,updated_utc:new Date().toISOString()};
    appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_prebuild_base_rebound",front_id:record.front_id,issue:record.issue,old_base_sha:record.base_sha,new_base_sha:nextBase,updated_utc:updated.updated_utc})}\n`);
    this.save(updated);return updated;
  }
  invalidatePostBuildBase(record:LifecycleRecord):LifecycleRecord {
    const exact=["CI_PENDING","REVIEWING"].includes(record.state)&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.repair_cycles===0&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
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
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.repair_cycles===0&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact||!/^[0-9a-f]{40}$/.test(nextBase)||!/^[0-9a-f]{40}$/.test(nextHead)||record.base_sha===nextBase||record.head_sha===nextHead)throw new Error("blocked CI base recovery denied");
    const updated={...record,state:"CI_PENDING" as const,base_sha:nextBase,head_sha:nextHead,last_error:undefined,completed_effects:[...record.completed_effects,`base-sync:${nextHead}`],updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_blocked_ci_base_recovered",front_id:record.front_id,issue:record.issue,pr:record.pr,old_base_sha:record.base_sha,new_base_sha:nextBase,old_head_sha:record.head_sha,new_head_sha:nextHead,updated_utc:updated.updated_utc})}\n`);return updated;
  }
  recoverBlockedCiChecks(record:LifecycleRecord):LifecycleRecord {
    const exact=record.state==="BLOCKED"&&record.last_error==="CI_FAILED"&&Number.isInteger(record.issue)&&record.issue!>0&&Number.isInteger(record.pr)&&record.pr!>0&&record.repair_cycles===0&&!!record.builder_session&&!record.reviewer_session&&!record.decision_id&&/^[0-9a-f]{40}$/.test(record.base_sha)&&/^[0-9a-f]{40}$/.test(record.head_sha??"")&&validBlockedCiEffectChain(record);
    if(!exact)throw new Error("blocked CI check recovery denied");
    const updated={...record,state:"CI_PENDING" as const,last_error:undefined,updated_utc:new Date().toISOString()};
    this.save(updated);appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"lifecycle_blocked_ci_checks_reopened",front_id:record.front_id,issue:record.issue,pr:record.pr,base_sha:record.base_sha,head_sha:record.head_sha,updated_utc:updated.updated_utc})}\n`);return updated;
  }
}
