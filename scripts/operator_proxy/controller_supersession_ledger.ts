import {appendFileSync,closeSync,existsSync,mkdirSync,openSync,readFileSync,unlinkSync} from "node:fs";
import {createHash} from "node:crypto";
import {join} from "node:path";
import type {ControllerSupersessionReceiptInputV1,ControllerSupersessionReceiptV1} from "./types.js";

const sha40=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{40}$/.test(value);
const sha64=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{64}$/.test(value);
const text=(value:unknown)=>typeof value==="string"&&value.length>0&&value.trim()===value;
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([left],[right])=>left.localeCompare(right)).map(([key,child])=>[key,canonical(child)])):value;
const serialized=(value:unknown)=>`${JSON.stringify(canonical(value))}\n`;
const hash=(value:unknown)=>createHash("sha256").update(serialized(value),"utf8").digest("hex");
const withoutHash=(event:ControllerSupersessionReceiptV1)=>{const {event_sha256,...body}=event;return body;};
const keys=new Set(["schema_version","controller","supersession_key","sequence","previous_event_sha256","repository","roadmap_item_id","canonical_base_sha","manifest_sha256","roadmap_sha256","historical_attempt_sha256","historical_base_sha","front_id","failed_head_sha","grant_key","consumed_event_sha256","build_attempt_id","functional_evidence_ref","functional_evidence_path","functional_evidence_sha256","functional_evidence_assertion_sha256","hard_limits","persistent_agent_loop_enabled","created_utc","event_sha256"]);

function validHardLimits(value:unknown):boolean {
  if(!value||typeof value!=="object"||Array.isArray(value))return false;
  const limits=value as Record<string,unknown>;
  return Object.keys(limits).length===5&&limits.human_final_authority===true&&limits.auto_merge===false&&limits.canonical_local_sync===false&&limits.live_trading===false&&limits.real_money===false;
}

function validCreatedUtc(value:unknown):boolean {
  if(!text(value))return false;
  const date=new Date(value as string);
  return !Number.isNaN(date.valueOf())&&date.toISOString()===value;
}

function validEvent(event:unknown):event is ControllerSupersessionReceiptV1 {
  if(!event||typeof event!=="object"||Array.isArray(event))return false;
  const value=event as Record<string,unknown>;
  if(Object.keys(value).length!==keys.size||Object.keys(value).some(key=>!keys.has(key)))return false;
  const typed=value as unknown as ControllerSupersessionReceiptV1;
  return typed.schema_version===1&&typed.controller==="CODEX_GOVERNED_CONTROLLER"&&sha64(typed.supersession_key)&&Number.isSafeInteger(typed.sequence)&&typed.sequence>=0&&(typed.previous_event_sha256===null||sha64(typed.previous_event_sha256))&&text(typed.repository)&&text(typed.roadmap_item_id)&&sha40(typed.canonical_base_sha)&&sha64(typed.manifest_sha256)&&sha64(typed.roadmap_sha256)&&sha64(typed.historical_attempt_sha256)&&sha40(typed.historical_base_sha)&&text(typed.front_id)&&sha40(typed.failed_head_sha)&&sha64(typed.grant_key)&&sha64(typed.consumed_event_sha256)&&sha64(typed.build_attempt_id)&&sha40(typed.functional_evidence_ref)&&text(typed.functional_evidence_path)&&typed.functional_evidence_path.startsWith("docs/")&&!typed.functional_evidence_path.includes("..")&&sha64(typed.functional_evidence_sha256)&&sha64(typed.functional_evidence_assertion_sha256)&&validHardLimits(typed.hard_limits)&&typed.persistent_agent_loop_enabled===false&&validCreatedUtc(typed.created_utc)&&sha64(typed.event_sha256)&&hash(withoutHash(typed))===typed.event_sha256;
}

export class ControllerSupersessionLedger {
  constructor(readonly root:string){mkdirSync(root,{recursive:true});}
  private path(){return join(this.root,"controller-supersessions.jsonl");}
  private lockPath(){return join(this.root,"controller-supersessions.lock");}
  private events():ControllerSupersessionReceiptV1[]{
    if(!existsSync(this.path()))return [];
    const raw=readFileSync(this.path(),"utf8");
    if(!raw)return [];
    if(!raw.endsWith("\n"))throw new Error("supersession receipt invalid");
    try{return raw.slice(0,-1).split("\n").map(line=>JSON.parse(line) as ControllerSupersessionReceiptV1);}catch{throw new Error("supersession receipt invalid");}
  }
  validate():readonly ControllerSupersessionReceiptV1[]{
    const events=this.events(),seen=new Set<string>();
    for(let index=0;index<events.length;index++){
      const event=events[index]!,previous=events[index-1];
      if(!validEvent(event)||seen.has(event.supersession_key)||event.sequence!==index||event.previous_event_sha256!==(previous?.event_sha256??null))throw new Error("supersession receipt invalid");
      seen.add(event.supersession_key);
    }
    return events;
  }
  append(input:ControllerSupersessionReceiptInputV1):ControllerSupersessionReceiptV1 {
    let descriptor:number|undefined;
    try{
      try{descriptor=openSync(this.lockPath(),"wx");}catch{throw new Error("supersession receipt lock unavailable");}
      const existing=this.validate();
      const candidate={...input,event_sha256:""} as ControllerSupersessionReceiptV1;
      candidate.event_sha256=hash(withoutHash(candidate));
      if(!validEvent(candidate))throw new Error("supersession receipt invalid");
      const sameKey=existing.find(event=>event.supersession_key===candidate.supersession_key);
      if(sameKey){if(sameKey.event_sha256!==candidate.event_sha256)throw new Error("supersession receipt conflict");return sameKey;}
      const prior=existing.at(-1);
      if(candidate.sequence!==existing.length||candidate.previous_event_sha256!==(prior?.event_sha256??null))throw new Error("supersession receipt chain invalid");
      const after=[...existing,candidate];
      for(let index=0;index<after.length;index++){const event=after[index]!,previous=after[index-1];if(!validEvent(event)||event.sequence!==index||event.previous_event_sha256!==(previous?.event_sha256??null))throw new Error("supersession receipt invalid");}
      appendFileSync(this.path(),serialized(candidate),"utf8");
      return candidate;
    }finally{if(descriptor!==undefined){closeSync(descriptor);unlinkSync(this.lockPath());}}
  }
}
