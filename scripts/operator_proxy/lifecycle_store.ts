import {appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync} from "node:fs";
import {join} from "node:path";
import type {LifecycleRecord, LifecycleState} from "./types.js";
import {transitionLifecycle} from "./state_machine.js";

const safeFront = (front: string) => {
  if (!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(front)) throw new Error("front id invalid");
  return front;
};

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
    const path=this.path(record.front_id); const tmp=`${path}.${process.pid}.tmp`;
    writeFileSync(tmp,`${JSON.stringify(record,null,2)}\n`,{flag:"wx"}); renameSync(tmp,path);
    appendFileSync(join(this.root,"events.jsonl"),`${JSON.stringify({event:"lifecycle_saved",front_id:record.front_id,state:record.state,updated_utc:record.updated_utc})}\n`);
  }
  advance(record: LifecycleRecord, next: LifecycleState, patch: Partial<LifecycleRecord>={}): LifecycleRecord {
    const updated={...record,...patch,state:transitionLifecycle(record.state,next),updated_utc:new Date().toISOString()}; this.save(updated); return updated;
  }
  effect(record: LifecycleRecord, key: string): LifecycleRecord {
    if(!/^[A-Za-z0-9][A-Za-z0-9:._-]{2,159}$/.test(key)) throw new Error("effect key invalid");
    if(record.completed_effects.includes(key)) return record;
    const updated={...record,completed_effects:[...record.completed_effects,key],updated_utc:new Date().toISOString()}; this.save(updated); return updated;
  }
}
