import {closeSync,existsSync,fsyncSync,mkdirSync,openSync,readFileSync,writeSync} from "node:fs";
import {createHash} from "node:crypto";
import {join} from "node:path";
import type {OwnerRepairEffectiveBaseBinding} from "./owner_repair_effective_base.js";
import {lock} from "./single_instance_lock.js";

export interface OwnerRepairRuntimeSupportEvent {
  schema_version:1;
  grant_key:string;
  front_id:string;
  authorization_id:string;
  build_attempt_id:string;
  effective_base_sha:string;
  effective_base_binding_sha256:string;
  runtime_support_sha:string;
  predecessor_event_sha256:string;
  event_sha256:string;
  created_at:string;
}

export interface OwnerRepairRuntimeSupportEvidence {
  currentTip:string;
  installedRuntimeSha:string;
  isAncestor:(older:string,newer:string)=>boolean;
}

const SHA40=/^[0-9a-f]{40}$/;
const SHA64=/^[0-9a-f]{64}$/;
const fields=["schema_version","grant_key","front_id","authorization_id","build_attempt_id","effective_base_sha","effective_base_binding_sha256","runtime_support_sha","predecessor_event_sha256","event_sha256","created_at"] as const;
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([left],[right])=>left.localeCompare(right)).map(([key,child])=>[key,canonical(child)])):value;
const digest=(value:unknown)=>createHash("sha256").update(`${JSON.stringify(canonical(value))}\n`,"utf8").digest("hex");
const withoutHash=(value:OwnerRepairRuntimeSupportEvent)=>{const {event_sha256,...body}=value;return body;};
const fail=(reason:string):never=>{throw new Error(`owner runtime support ${reason}`);};

function validate(value:unknown):asserts value is OwnerRepairRuntimeSupportEvent {
  if(!value||typeof value!=="object"||Array.isArray(value))fail("invalid");
  const event=value as OwnerRepairRuntimeSupportEvent;
  if(Object.keys(event).length!==fields.length||!fields.every(key=>Object.hasOwn(event,key))||event.schema_version!==1||!SHA64.test(event.grant_key)||!event.front_id||!event.authorization_id||!SHA64.test(event.build_attempt_id)||!SHA40.test(event.effective_base_sha)||!SHA64.test(event.effective_base_binding_sha256)||!SHA40.test(event.runtime_support_sha)||!SHA64.test(event.predecessor_event_sha256)||!SHA64.test(event.event_sha256)||!Number.isFinite(Date.parse(event.created_at))||digest(withoutHash(event))!==event.event_sha256)fail("invalid");
}

function matches(event:OwnerRepairRuntimeSupportEvent,binding:OwnerRepairEffectiveBaseBinding):boolean {
  return event.grant_key===binding.grant_key&&event.front_id===binding.front_id&&event.authorization_id===binding.authorization_id&&event.build_attempt_id===binding.build_attempt_id&&event.effective_base_sha===binding.effective_base_sha&&event.effective_base_binding_sha256===binding.event_sha256;
}

export class OwnerRepairRuntimeSupportLedger {
  constructor(readonly root:string){mkdirSync(root,{recursive:true});}
  private path(){return join(this.root,"owner-repair-runtime-support.jsonl");}
  private lockPath(){return join(this.root,"owner-repair-runtime-support-lock");}
  private all():OwnerRepairRuntimeSupportEvent[] {
    if(!existsSync(this.path()))return [];
    let values:unknown[]=[];
    try{const raw=readFileSync(this.path(),"utf8").trim();values=raw?raw.split(/\r?\n/).map(line=>JSON.parse(line)):[];}catch{fail("invalid");}
    const events=values as OwnerRepairRuntimeSupportEvent[],hashes=new Set<string>(),priorByGrant=new Map<string,OwnerRepairRuntimeSupportEvent>(),supportsByGrant=new Map<string,Set<string>>();
    for(const event of events){
      validate(event);
      if(hashes.has(event.event_sha256))fail("duplicate");hashes.add(event.event_sha256);
      const prior=priorByGrant.get(event.grant_key);
      const supports=supportsByGrant.get(event.grant_key)??new Set<string>();
      if(supports.has(event.runtime_support_sha))fail("duplicate");supports.add(event.runtime_support_sha);supportsByGrant.set(event.grant_key,supports);
      if(prior&&event.predecessor_event_sha256!==prior.event_sha256)fail("chain invalid");
      priorByGrant.set(event.grant_key,event);
    }
    return events;
  }
  load(grantKey:string):OwnerRepairRuntimeSupportEvent|undefined {
    if(!SHA64.test(grantKey))fail("grant key invalid");
    return this.all().filter(event=>event.grant_key===grantKey).at(-1);
  }
  bind(binding:OwnerRepairEffectiveBaseBinding,evidence:OwnerRepairRuntimeSupportEvidence):OwnerRepairRuntimeSupportEvent {
    if(!binding||!SHA64.test(binding.grant_key)||!SHA40.test(binding.effective_base_sha)||!SHA64.test(binding.event_sha256))fail("binding invalid");
    const support=evidence.currentTip;
    if(!SHA40.test(support)||evidence.installedRuntimeSha!==support)fail("runtime support mismatch");
    let descendant=false;try{descendant=evidence.isAncestor(binding.effective_base_sha,support);}catch{fail("ancestry unavailable");}
    if(!descendant)fail("runtime support ancestry invalid");
    const release=lock(this.lockPath());
    try{
      const history=this.all().filter(event=>event.grant_key===binding.grant_key),existing=history.at(-1);
      if(history.length&&(!history.every(event=>matches(event,binding))||history[0]!.predecessor_event_sha256!==binding.event_sha256))fail("root invalid");
      if(existing?.runtime_support_sha===support)return existing;
      if(existing){let advances=false;try{advances=evidence.isAncestor(existing.runtime_support_sha,support);}catch{fail("ancestry unavailable");}if(!advances)fail("conflict");}
      const event:OwnerRepairRuntimeSupportEvent={schema_version:1,grant_key:binding.grant_key,front_id:binding.front_id,authorization_id:binding.authorization_id,build_attempt_id:binding.build_attempt_id,effective_base_sha:binding.effective_base_sha,effective_base_binding_sha256:binding.event_sha256,runtime_support_sha:support,predecessor_event_sha256:existing?.event_sha256??binding.event_sha256,event_sha256:"",created_at:new Date().toISOString()};
      event.event_sha256=digest(withoutHash(event));validate(event);
      const descriptor=openSync(this.path(),"a");try{writeSync(descriptor,`${JSON.stringify(event)}\n`);fsyncSync(descriptor);}finally{closeSync(descriptor);}
      return event;
    }finally{release();}
  }
}
