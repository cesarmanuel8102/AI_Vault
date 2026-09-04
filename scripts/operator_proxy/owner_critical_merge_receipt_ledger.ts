import {appendFileSync,closeSync,existsSync,mkdirSync,openSync,readFileSync,unlinkSync} from "node:fs";
import {createHash} from "node:crypto";
import {join} from "node:path";
import type {OwnerAuthorizedCriticalMerge} from "./types.js";

type Phase="VERIFIED"|"CONSUMED"|"MERGE_DISPATCHED"|"MERGED_BOUND";
export interface OwnerCriticalMergeReceiptEvent {schema_version:1;critical_merge_key:string;sequence:number;phase:Phase;predecessor_event_sha256:string|null;event_sha256:string;authorization_id:string;repository:string;issue:number;front_id:string;pr:number;base_branch:string;base_sha:string;head_branch:string;head_sha:string;policy_decision_id:string;policy_decision_key:string;immutable_authorization_snapshot_sha256:string;created_at:string;merge_commit_sha?:string;immutable_authorization_snapshot?:OwnerAuthorizedCriticalMerge}

const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==="object"&&!Array.isArray(value)?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b)).map(([key,child])=>[key,canonical(child)])):value;
const bytes=(value:unknown)=>`${JSON.stringify(canonical(value))}\n`;
const hash=(value:unknown)=>createHash("sha256").update(bytes(value),"utf8").digest("hex");
const sha40=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{40}$/.test(value);
const sha64=(value:unknown)=>typeof value==="string"&&/^[0-9a-f]{64}$/.test(value);
const positive=(value:unknown)=>Number.isSafeInteger(value)&&(value as number)>0;
const text=(value:unknown)=>typeof value==="string"&&value.trim()===value&&value.length>0;
const phases:Record<Phase,readonly Phase[]>={VERIFIED:["CONSUMED"],CONSUMED:["MERGE_DISPATCHED"],MERGE_DISPATCHED:["MERGED_BOUND"],MERGED_BOUND:[]};
const withoutHash=(event:OwnerCriticalMergeReceiptEvent)=>{const {event_sha256,...body}=event;return body;};
const sameIdentity=(left:OwnerCriticalMergeReceiptEvent,right:OwnerCriticalMergeReceiptEvent)=>left.authorization_id===right.authorization_id&&left.repository===right.repository&&left.issue===right.issue&&left.front_id===right.front_id&&left.pr===right.pr&&left.base_branch===right.base_branch&&left.base_sha===right.base_sha&&left.head_branch===right.head_branch&&left.head_sha===right.head_sha&&left.policy_decision_id===right.policy_decision_id&&left.policy_decision_key===right.policy_decision_key&&left.immutable_authorization_snapshot_sha256===right.immutable_authorization_snapshot_sha256;
const snapshotMatchesEvent=(snapshot:OwnerAuthorizedCriticalMerge,event:OwnerCriticalMergeReceiptEvent)=>snapshot.schema_version===1&&snapshot.critical_merge_key===event.critical_merge_key&&snapshot.authorization_id===event.authorization_id&&snapshot.repository===event.repository&&snapshot.issue===event.issue&&snapshot.front_id===event.front_id&&snapshot.pr===event.pr&&snapshot.base_branch===event.base_branch&&snapshot.base_sha===event.base_sha&&snapshot.head_branch===event.head_branch&&snapshot.head_sha===event.head_sha&&snapshot.policy_decision_id===event.policy_decision_id&&snapshot.policy_decision_key===event.policy_decision_key&&snapshot.risk==="CRITICAL"&&snapshot.action==="OWNER_AUTHORIZED_CRITICAL_MERGE"&&snapshot.max_uses===1;

export class OwnerCriticalMergeReceiptLedger {
  constructor(readonly root:string){mkdirSync(root,{recursive:true});}
  private path(){return join(this.root,"owner-critical-merge-receipts.jsonl");}
  private events():OwnerCriticalMergeReceiptEvent[]{
    if(!existsSync(this.path()))return [];
    const raw=readFileSync(this.path(),"utf8").trim();
    if(!raw)return [];
    try{return raw.split(/\r?\n/).map(line=>JSON.parse(line) as OwnerCriticalMergeReceiptEvent);}catch{throw new Error("critical merge receipt invalid");}
  }
  private validate(events:OwnerCriticalMergeReceiptEvent[]):void {
    const grouped=new Map<string,OwnerCriticalMergeReceiptEvent[]>();
    for(const event of events){
      if(!event||event.schema_version!==1||!sha64(event.critical_merge_key)||!Number.isInteger(event.sequence)||event.sequence<0||!Object.hasOwn(phases,event.phase)||!sha64(event.event_sha256)||!text(event.authorization_id)||!text(event.repository)||!positive(event.issue)||!text(event.front_id)||!positive(event.pr)||!text(event.base_branch)||!sha40(event.base_sha)||!text(event.head_branch)||!sha40(event.head_sha)||!text(event.policy_decision_id)||!sha64(event.policy_decision_key)||!sha64(event.immutable_authorization_snapshot_sha256)||!text(event.created_at)||hash(withoutHash(event))!==event.event_sha256)throw new Error("critical merge receipt invalid");
      const list=grouped.get(event.critical_merge_key)??[];list.push(event);grouped.set(event.critical_merge_key,list);
    }
    const authorizationKeys=new Map<string,string>();
    for(const list of grouped.values())for(let index=0;index<list.length;index++){
      const event=list[index]!,previous=list[index-1];
      if(event.sequence!==index||event.predecessor_event_sha256!==(previous?.event_sha256??null)||index>0&&!phases[previous!.phase].includes(event.phase)||index>0&&!sameIdentity(event,previous!))throw new Error("critical merge receipt chain invalid");
      if(index===0&&(event.phase!=="VERIFIED"||!event.immutable_authorization_snapshot||hash(event.immutable_authorization_snapshot)!==event.immutable_authorization_snapshot_sha256||!snapshotMatchesEvent(event.immutable_authorization_snapshot,event)))throw new Error("critical merge receipt chain invalid");
      if(index>0&&event.immutable_authorization_snapshot!==undefined)throw new Error("critical merge receipt chain invalid");
      if(event.phase==="MERGED_BOUND"&&!sha40(event.merge_commit_sha))throw new Error("critical merge receipt chain invalid");
      if(event.phase!=="MERGED_BOUND"&&event.merge_commit_sha!==undefined)throw new Error("critical merge receipt chain invalid");
      const existing=authorizationKeys.get(event.authorization_id);
      if(existing&&existing!==event.critical_merge_key)throw new Error("critical merge receipt authorization replay");
      authorizationKeys.set(event.authorization_id,event.critical_merge_key);
    }
  }
  private append(event:Omit<OwnerCriticalMergeReceiptEvent,"event_sha256">,beforeAppend?:(events:readonly OwnerCriticalMergeReceiptEvent[])=>void):OwnerCriticalMergeReceiptEvent {
    const lock=join(this.root,"owner-critical-merge-receipts.lock");let descriptor:number|undefined;
    try{
      try{descriptor=openSync(lock,"wx");}catch{throw new Error("critical merge receipt lock unavailable");}
      const all=this.events();this.validate(all);beforeAppend?.(all);
      const completed={...event,event_sha256:""} as OwnerCriticalMergeReceiptEvent;completed.event_sha256=hash(withoutHash(completed));
      all.push(completed);this.validate(all);appendFileSync(this.path(),`${JSON.stringify(completed)}\n`);return completed;
    }finally{if(descriptor!==undefined){closeSync(descriptor);unlinkSync(lock);}}
  }
  deriveReceiptView(critical_merge_key:string):OwnerCriticalMergeReceiptEvent {const all=this.events();this.validate(all);const list=all.filter(event=>event.critical_merge_key===critical_merge_key);if(!list.length)throw new Error("critical merge receipt missing");return list.at(-1)!;}
  assertCurrentConsumedReceipt(receipt:OwnerCriticalMergeReceiptEvent):void {
    const all=this.events();this.validate(all);const current=all.filter(event=>event.critical_merge_key===receipt.critical_merge_key).at(-1);
    if(receipt.phase!=="CONSUMED"||!current||current.event_sha256!==receipt.event_sha256||current.phase!=="CONSUMED"||!sameIdentity(current,receipt))throw new Error("critical merge receipt consumed view invalid");
  }
  assertCurrentDispatchedReceipt(receipt:OwnerCriticalMergeReceiptEvent):void {
    const all=this.events();this.validate(all);const current=all.filter(event=>event.critical_merge_key===receipt.critical_merge_key).at(-1);
    if(receipt.phase!=="MERGE_DISPATCHED"||!current||current.event_sha256!==receipt.event_sha256||current.phase!=="MERGE_DISPATCHED"||!sameIdentity(current,receipt))throw new Error("critical merge receipt dispatched view invalid");
  }
  appendVerified(authorization:OwnerAuthorizedCriticalMerge):OwnerCriticalMergeReceiptEvent {
    const snapshot=hash(authorization);
    return this.append({schema_version:1,critical_merge_key:authorization.critical_merge_key,sequence:0,phase:"VERIFIED",predecessor_event_sha256:null,authorization_id:authorization.authorization_id,repository:authorization.repository,issue:authorization.issue,front_id:authorization.front_id,pr:authorization.pr,base_branch:authorization.base_branch,base_sha:authorization.base_sha,head_branch:authorization.head_branch,head_sha:authorization.head_sha,policy_decision_id:authorization.policy_decision_id,policy_decision_key:authorization.policy_decision_key,immutable_authorization_snapshot_sha256:snapshot,immutable_authorization_snapshot:authorization,created_at:new Date().toISOString()},events=>{if(events.some(event=>event.critical_merge_key===authorization.critical_merge_key||event.authorization_id===authorization.authorization_id))throw new Error("critical merge receipt already exists");});
  }
  private next(critical_merge_key:string,phase:Exclude<Phase,"VERIFIED">,patch:Partial<OwnerCriticalMergeReceiptEvent>={}):OwnerCriticalMergeReceiptEvent {
    const prior=this.deriveReceiptView(critical_merge_key);
    if(!phases[prior.phase].includes(phase))throw new Error("critical merge receipt transition invalid");
    return this.append({schema_version:1,critical_merge_key,sequence:prior.sequence+1,phase,predecessor_event_sha256:prior.event_sha256,authorization_id:prior.authorization_id,repository:prior.repository,issue:prior.issue,front_id:prior.front_id,pr:prior.pr,base_branch:prior.base_branch,base_sha:prior.base_sha,head_branch:prior.head_branch,head_sha:prior.head_sha,policy_decision_id:prior.policy_decision_id,policy_decision_key:prior.policy_decision_key,immutable_authorization_snapshot_sha256:prior.immutable_authorization_snapshot_sha256,created_at:new Date().toISOString(),...patch},events=>{const current=events.filter(event=>event.critical_merge_key===critical_merge_key).at(-1);if(!current||current.event_sha256!==prior.event_sha256||current.phase!==prior.phase||!sameIdentity(current,prior))throw new Error("critical merge receipt transition stale");});
  }
  consume(critical_merge_key:string):OwnerCriticalMergeReceiptEvent {return this.next(critical_merge_key,"CONSUMED");}
  markMergeDispatched(critical_merge_key:string):OwnerCriticalMergeReceiptEvent {return this.next(critical_merge_key,"MERGE_DISPATCHED");}
  bindMergedSha(critical_merge_key:string,merge_commit_sha:string):OwnerCriticalMergeReceiptEvent {if(!sha40(merge_commit_sha))throw new Error("critical merge receipt merge sha invalid");return this.next(critical_merge_key,"MERGED_BOUND",{merge_commit_sha});}
}
