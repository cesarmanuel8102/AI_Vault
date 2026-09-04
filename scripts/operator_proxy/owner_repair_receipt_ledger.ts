import {appendFileSync,closeSync,existsSync,mkdirSync,openSync,readFileSync,unlinkSync} from "node:fs";
import {createHash} from "node:crypto";
import {join} from "node:path";
import type {OwnerAuthorizedPayloadRepairGrant} from "./types.js";

type Phase="VERIFIED"|"CONSUMED"|"BUILD_DISPATCHED"|"HEAD_BOUND"|"TERMINAL";
export interface OwnerGrantReceiptEvent {schema_version:1;grant_key:string;sequence:number;phase:Phase;predecessor_event_sha256:string|null;event_sha256:string;authorization_id:string;front_id:string;failed_head_sha:string;immutable_grant_snapshot_sha256:string;created_at:string;build_attempt_id?:string;new_head_sha?:string;terminal_reason?:string;immutable_grant_snapshot?:OwnerAuthorizedPayloadRepairGrant}

const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([key,child])=>[key,canonical(child)])):value;
const bytes=(value:unknown)=>`${JSON.stringify(canonical(value))}\n`;
const hash=(value:unknown)=>createHash("sha256").update(bytes(value),"utf8").digest("hex");
const sha40=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{40}$/.test(value);
const sha64=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{64}$/.test(value);
const phases:Record<Phase,readonly Phase[]>={VERIFIED:["CONSUMED"],CONSUMED:["BUILD_DISPATCHED","TERMINAL"],BUILD_DISPATCHED:["HEAD_BOUND","TERMINAL"],HEAD_BOUND:["TERMINAL"],TERMINAL:[]};
const withoutHash=(event:OwnerGrantReceiptEvent)=>{const {event_sha256,...body}=event;return body;};

export class OwnerRepairReceiptLedger {
  constructor(readonly root:string){mkdirSync(root,{recursive:true});}
  private path(){return join(this.root,"owner-repair-receipts.jsonl");}
  private events():OwnerGrantReceiptEvent[]{
    if(!existsSync(this.path()))return [];
    const raw=readFileSync(this.path(),"utf8").trim();
    if(!raw)return [];
    try{return raw.split(/\r?\n/).map(line=>JSON.parse(line) as OwnerGrantReceiptEvent);}catch{throw new Error("owner receipt invalid");}
  }
  private validate(events:OwnerGrantReceiptEvent[]):void {
    const grouped=new Map<string,OwnerGrantReceiptEvent[]>();
    for(const event of events){if(!event||event.schema_version!==1||!sha64(event.grant_key)||!Number.isInteger(event.sequence)||event.sequence<0||!Object.hasOwn(phases,event.phase)||!sha64(event.event_sha256)||typeof event.authorization_id!=="string"||typeof event.front_id!=="string"||!sha40(event.failed_head_sha)||!sha64(event.immutable_grant_snapshot_sha256)||typeof event.created_at!=="string"||hash(withoutHash(event))!==event.event_sha256)throw new Error("owner receipt invalid");const list=grouped.get(event.grant_key)??[];list.push(event);grouped.set(event.grant_key,list);}
    for(const list of grouped.values())for(let index=0;index<list.length;index++){
      const event=list[index]!,previous=list[index-1];
      if(event.sequence!==index||event.predecessor_event_sha256!==(previous?.event_sha256??null)||index>0&&!phases[previous!.phase].includes(event.phase))throw new Error("owner receipt chain invalid");
      if(index===0&&(event.phase!=="VERIFIED"||!event.immutable_grant_snapshot||hash(event.immutable_grant_snapshot)!==event.immutable_grant_snapshot_sha256))throw new Error("owner receipt chain invalid");
      if(index>0&&event.immutable_grant_snapshot!==undefined)throw new Error("owner receipt chain invalid");
      if(event.phase==="CONSUMED"&&!sha64(event.build_attempt_id))throw new Error("owner receipt chain invalid");
      if(index>0&&event.phase!=="CONSUMED"&&event.build_attempt_id!==previous?.build_attempt_id)throw new Error("owner receipt chain invalid");
      if(event.phase==="HEAD_BOUND"&&!sha40(event.new_head_sha))throw new Error("owner receipt chain invalid");
    }
  }
  private append(event:Omit<OwnerGrantReceiptEvent,"event_sha256">,beforeAppend?:(events:readonly OwnerGrantReceiptEvent[])=>void):OwnerGrantReceiptEvent {
    const lock=join(this.root,"owner-repair-receipts.lock");let descriptor:number|undefined;
    try{try{descriptor=openSync(lock,"wx");}catch{throw new Error("owner receipt lock unavailable");}
      const completed={...event,event_sha256:""} as OwnerGrantReceiptEvent;completed.event_sha256=hash(withoutHash(completed));const all=this.events();this.validate(all);beforeAppend?.(all);all.push(completed);this.validate(all);appendFileSync(this.path(),`${JSON.stringify(completed)}\n`);return completed;
    }finally{if(descriptor!==undefined){closeSync(descriptor);unlinkSync(lock);}}
  }
  deriveReceiptView(grant_key:string):OwnerGrantReceiptEvent {const all=this.events();this.validate(all);const list=all.filter(event=>event.grant_key===grant_key);if(!list.length)throw new Error("owner receipt missing");return list.at(-1)!;}
  findGrantSnapshot(identity:{front_id:string;issue:number;pr:number;failed_head_sha:string}):OwnerAuthorizedPayloadRepairGrant|undefined {
    const all=this.events();this.validate(all);
    const matches=all.filter(event=>event.phase==="VERIFIED"&&event.front_id===identity.front_id&&event.failed_head_sha===identity.failed_head_sha&&event.immutable_grant_snapshot?.issue===identity.issue&&event.immutable_grant_snapshot?.pr===identity.pr);
    if(matches.length>1)throw new Error("owner receipt snapshot ambiguous");
    const event=matches[0];if(!event)return undefined;
    const grant=event.immutable_grant_snapshot;
    if(!grant||grant.grant_key!==event.grant_key||grant.authorization_id!==event.authorization_id||grant.front_id!==event.front_id||grant.failed_head_sha!==event.failed_head_sha)throw new Error("owner receipt snapshot invalid");
    return grant;
  }
  assertCurrentConsumedReceipt(receipt:OwnerGrantReceiptEvent):void {
    const all=this.events();this.validate(all);
    const current=all.filter(event=>event.grant_key===receipt.grant_key).at(-1);
    const consumed=all.filter(event=>event.front_id===receipt.front_id&&event.phase==="CONSUMED");
    if(receipt.phase!=="CONSUMED"||!current||hash(withoutHash(current))!==hash(withoutHash(receipt))||current.event_sha256!==receipt.event_sha256||current.phase!=="CONSUMED"||consumed.length!==1||consumed[0]!.event_sha256!==receipt.event_sha256)throw new Error("owner receipt consumed view invalid");
  }
  appendVerified(grant:OwnerAuthorizedPayloadRepairGrant):OwnerGrantReceiptEvent {const all=this.events();this.validate(all);if(all.some(event=>event.grant_key===grant.grant_key))throw new Error("owner receipt already exists");return this.append({schema_version:1,grant_key:grant.grant_key,sequence:0,phase:"VERIFIED",predecessor_event_sha256:null,authorization_id:grant.authorization_id,front_id:grant.front_id,failed_head_sha:grant.failed_head_sha,immutable_grant_snapshot_sha256:hash(grant),immutable_grant_snapshot:grant,created_at:new Date().toISOString()});}
  private next(grant_key:string,phase:Exclude<Phase,"VERIFIED">,patch:Partial<OwnerGrantReceiptEvent>={},beforeAppend?:(events:readonly OwnerGrantReceiptEvent[])=>void):OwnerGrantReceiptEvent {const prior=this.deriveReceiptView(grant_key);if(!phases[prior.phase].includes(phase))throw new Error("owner receipt transition invalid");return this.append({schema_version:1,grant_key,sequence:prior.sequence+1,phase,predecessor_event_sha256:prior.event_sha256,authorization_id:prior.authorization_id,front_id:prior.front_id,failed_head_sha:prior.failed_head_sha,immutable_grant_snapshot_sha256:prior.immutable_grant_snapshot_sha256,build_attempt_id:prior.build_attempt_id,...patch,created_at:new Date().toISOString()},beforeAppend);}
  hasConsumedOwnerException(front_id:string):boolean {const all=this.events();this.validate(all);return all.some(event=>event.front_id===front_id&&["CONSUMED","BUILD_DISPATCHED","HEAD_BOUND","TERMINAL"].includes(event.phase));}
  consume(grant_key:string):OwnerGrantReceiptEvent {const prior=this.deriveReceiptView(grant_key);if(prior.phase!=="VERIFIED")throw new Error("owner receipt transition invalid");if(this.hasConsumedOwnerException(prior.front_id))throw new Error("owner exception already consumed");const build_attempt_id=createHash("sha256").update(`owner-payload-repair-build-attempt-v1\0${grant_key}\0${prior.front_id}\0${prior.failed_head_sha}`,"utf8").digest("hex");return this.next(grant_key,"CONSUMED",{build_attempt_id},events=>{if(events.some(event=>event.front_id===prior.front_id&&["CONSUMED","BUILD_DISPATCHED","HEAD_BOUND","TERMINAL"].includes(event.phase)))throw new Error("owner exception already consumed");});}
  markBuildDispatched(grant_key:string){return this.next(grant_key,"BUILD_DISPATCHED");}
  bindHead(grant_key:string,new_head_sha:string){if(!sha40(new_head_sha))throw new Error("owner receipt head invalid");return this.next(grant_key,"HEAD_BOUND",{new_head_sha});}
  terminalize(grant_key:string,terminal_reason:string){if(typeof terminal_reason!=="string"||!terminal_reason)throw new Error("owner receipt terminal invalid");return this.next(grant_key,"TERMINAL",{terminal_reason});}
}
