import {closeSync,existsSync,fsyncSync,mkdirSync,openSync,readFileSync,writeSync} from "node:fs";
import {createHash} from "node:crypto";
import {join} from "node:path";
import {OwnerRepairReceiptLedger,type OwnerGrantReceiptEvent} from "./owner_repair_receipt_ledger.js";
import {lock} from "./single_instance_lock.js";

export const OWNER_REPAIR_EFFECTIVE_BASE_CANONICAL_BRANCH="codex/own-capital-sustainable-return";

export interface OwnerRepairEffectiveBaseBinding {
  schema_version:1;
  grant_key:string;
  front_id:string;
  authorization_id:string;
  build_attempt_id:string;
  frozen_base_sha:string;
  effective_base_sha:string;
  failed_head_sha:string;
  build_dispatched_event_sha256:string;
  canonical_branch:string;
  installed_runtime_sha:string;
  predecessor_event_sha256:string;
  event_sha256:string;
  created_at:string;
}

export interface OwnerRepairEffectiveBaseEvidence {
  receipts:OwnerRepairReceiptLedger;
  currentTip:string;
  installedRuntimeSha:string;
  doctorPassed:boolean;
  isAncestor:(older:string,newer:string)=>boolean;
}

type BindingInput=Omit<OwnerRepairEffectiveBaseBinding,"schema_version"|"event_sha256"|"created_at">;

const SHA40=/^[0-9a-f]{40}$/;
const SHA64=/^[0-9a-f]{64}$/;
const fields=["schema_version","grant_key","front_id","authorization_id","build_attempt_id","frozen_base_sha","effective_base_sha","failed_head_sha","build_dispatched_event_sha256","canonical_branch","installed_runtime_sha","predecessor_event_sha256","event_sha256","created_at"] as const;
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([left],[right])=>left.localeCompare(right)).map(([key,child])=>[key,canonical(child)])):value;
const hash=(value:unknown)=>createHash("sha256").update(`${JSON.stringify(canonical(value))}\n`,"utf8").digest("hex");
const withoutHash=(binding:OwnerRepairEffectiveBaseBinding)=>{const {event_sha256,...body}=binding;return body;};
const exactKeys=(value:Record<string,unknown>)=>Object.keys(value).length===fields.length&&fields.every(field=>Object.hasOwn(value,field));

function fail(reason:string):never {throw new Error(`owner effective base binding ${reason}`);}

function validateBinding(value:unknown):asserts value is OwnerRepairEffectiveBaseBinding {
  if(!value||typeof value!=="object"||Array.isArray(value)||!exactKeys(value as Record<string,unknown>))fail("invalid");
  const binding=value as OwnerRepairEffectiveBaseBinding;
  if(binding.schema_version!==1||!SHA64.test(binding.grant_key)||typeof binding.front_id!=="string"||!binding.front_id||typeof binding.authorization_id!=="string"||!binding.authorization_id||!SHA64.test(binding.build_attempt_id)||!SHA40.test(binding.frozen_base_sha)||!SHA40.test(binding.effective_base_sha)||!SHA40.test(binding.failed_head_sha)||!SHA64.test(binding.build_dispatched_event_sha256)||binding.canonical_branch!==OWNER_REPAIR_EFFECTIVE_BASE_CANONICAL_BRANCH||!SHA40.test(binding.installed_runtime_sha)||binding.predecessor_event_sha256!==binding.build_dispatched_event_sha256||!SHA64.test(binding.event_sha256)||typeof binding.created_at!=="string"||!Number.isFinite(Date.parse(binding.created_at))||hash(withoutHash(binding))!==binding.event_sha256)fail("invalid");
}

function sameBinding(left:OwnerRepairEffectiveBaseBinding,right:BindingInput):boolean {
  return left.grant_key===right.grant_key&&left.front_id===right.front_id&&left.authorization_id===right.authorization_id&&left.build_attempt_id===right.build_attempt_id&&left.frozen_base_sha===right.frozen_base_sha&&left.effective_base_sha===right.effective_base_sha&&left.failed_head_sha===right.failed_head_sha&&left.build_dispatched_event_sha256===right.build_dispatched_event_sha256&&left.canonical_branch===right.canonical_branch&&left.installed_runtime_sha===right.installed_runtime_sha&&left.predecessor_event_sha256===right.predecessor_event_sha256;
}

function allReceiptEvents(receipts:OwnerRepairReceiptLedger):OwnerGrantReceiptEvent[] {
  const path=join(receipts.root,"owner-repair-receipts.jsonl");
  if(!existsSync(path))fail("receipt missing");
  let values:unknown[];
  try{const raw=readFileSync(path,"utf8").trim();values=raw?raw.split(/\r?\n/).map(line=>JSON.parse(line)):[];}catch{fail("receipt invalid");}
  return values as OwnerGrantReceiptEvent[];
}

function dispatchFromCurrent(view:OwnerGrantReceiptEvent,input:BindingInput):string {
  if(view.phase==="BUILD_DISPATCHED")return view.event_sha256;
  if(view.phase==="HEAD_BOUND")return view.predecessor_event_sha256??"";
  fail("receipt is not dispatched");
}

function validateEvidence(input:BindingInput,evidence:OwnerRepairEffectiveBaseEvidence,allowHeadBoundReplay:boolean):void {
  if(!SHA64.test(input.grant_key)||!input.front_id||!input.authorization_id||!SHA64.test(input.build_attempt_id)||!SHA40.test(input.frozen_base_sha)||!SHA40.test(input.effective_base_sha)||!SHA40.test(input.failed_head_sha)||!SHA64.test(input.build_dispatched_event_sha256)||input.canonical_branch!==OWNER_REPAIR_EFFECTIVE_BASE_CANONICAL_BRANCH||!SHA40.test(input.installed_runtime_sha)||input.predecessor_event_sha256!==input.build_dispatched_event_sha256)fail("input invalid");
  if(evidence.currentTip!==input.effective_base_sha)fail("canonical tip mismatch");
  if(evidence.installedRuntimeSha!==input.effective_base_sha||input.installed_runtime_sha!==input.effective_base_sha)fail("runtime mismatch");
  if(evidence.doctorPassed!==true)fail("doctor failed");
  let descendant=false;try{descendant=evidence.isAncestor(input.frozen_base_sha,input.effective_base_sha);}catch{fail("ancestry unavailable");}
  if(!descendant)fail("effective base ancestry invalid");

  const view=evidence.receipts.deriveReceiptView(input.grant_key);
  if(view.phase!=="BUILD_DISPATCHED"&&(!allowHeadBoundReplay||view.phase!=="HEAD_BOUND"))fail("first binding requires dispatched receipt");
  const dispatched=dispatchFromCurrent(view,input);
  if(dispatched!==input.build_dispatched_event_sha256||view.build_attempt_id!==input.build_attempt_id||view.front_id!==input.front_id||view.authorization_id!==input.authorization_id||view.failed_head_sha!==input.failed_head_sha)fail("dispatch anchor invalid");
  const all=allReceiptEvents(evidence.receipts),events=all.filter(event=>event?.grant_key===input.grant_key),verified=events.filter(event=>event.phase==="VERIFIED"),dispatches=events.filter(event=>event.phase==="BUILD_DISPATCHED");
  if(all.filter(event=>event?.front_id===input.front_id&&event.phase==="CONSUMED").length!==1)fail("consumption ambiguous");
  if(verified.length!==1||dispatches.length!==1)fail("receipt chain ambiguous");
  const snapshot=verified[0]!.immutable_grant_snapshot,dispatch=dispatches[0]!;
  if(!snapshot||snapshot.grant_key!==input.grant_key||snapshot.front_id!==input.front_id||snapshot.authorization_id!==input.authorization_id||snapshot.canonical_base_sha!==input.frozen_base_sha||snapshot.failed_head_sha!==input.failed_head_sha||dispatch.event_sha256!==input.build_dispatched_event_sha256||dispatch.predecessor_event_sha256===null||dispatch.build_attempt_id!==input.build_attempt_id||view.phase==="HEAD_BOUND"&&view.predecessor_event_sha256!==dispatch.event_sha256)fail("receipt chain invalid");
}

export class OwnerRepairEffectiveBaseLedger {
  constructor(readonly root:string){mkdirSync(root,{recursive:true});}
  private path(){return join(this.root,"owner-repair-effective-bases.jsonl");}
  private lockPath(){return join(this.root,"owner-repair-effective-bases-lock");}
  private all():OwnerRepairEffectiveBaseBinding[] {
    if(!existsSync(this.path()))return [];
    let values:unknown[];
    try{const raw=readFileSync(this.path(),"utf8").trim();values=raw?raw.split(/\r?\n/).map(line=>JSON.parse(line)):[];}catch{fail("invalid");}
    const bindings=values as OwnerRepairEffectiveBaseBinding[],byGrant=new Set<string>(),byFront=new Set<string>();
    for(const binding of bindings){validateBinding(binding);if(byGrant.has(binding.grant_key)||byFront.has(binding.front_id))fail("duplicate");byGrant.add(binding.grant_key);byFront.add(binding.front_id);}
    return bindings;
  }
  load(grantKey:string):OwnerRepairEffectiveBaseBinding|undefined {
    if(!SHA64.test(grantKey))fail("grant key invalid");
    return this.all().find(binding=>binding.grant_key===grantKey);
  }
  bind(input:BindingInput,evidence:OwnerRepairEffectiveBaseEvidence):OwnerRepairEffectiveBaseBinding {
    const release=lock(this.lockPath());
    try{
      const bindings=this.all(),existing=bindings.find(binding=>binding.grant_key===input.grant_key),sameFront=bindings.find(binding=>binding.front_id===input.front_id);
      if(sameFront&&!existing)fail("conflict");
      validateEvidence(input,evidence,existing!==undefined);
      if(existing){if(!sameBinding(existing,input))fail("conflict");return existing;}
      const binding:OwnerRepairEffectiveBaseBinding={schema_version:1,...input,event_sha256:"",created_at:new Date().toISOString()};
      binding.event_sha256=hash(withoutHash(binding));validateBinding(binding);
      const descriptorAppend=openSync(this.path(),"a");
      try{writeSync(descriptorAppend,`${JSON.stringify(binding)}\n`);fsyncSync(descriptorAppend);}finally{closeSync(descriptorAppend);}
      return binding;
    }finally{release();}
  }
}
