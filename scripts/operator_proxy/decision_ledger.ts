import {appendFileSync,existsSync,mkdirSync,readFileSync,readdirSync,renameSync,rmSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import type {Decision} from "./types.js";
import {redactSensitiveData,safeJson} from "./redaction.js";

const sha64=/^[0-9a-f]{64}$/;
const identityFields=["decision_key","decision_id","authorization_id","repository","issue","pr","base_sha","head_sha","roadmap_id","roadmap_item_id","policy_sha256"] as const;

function parseDecision(path:string){
  let value:Decision;
  try{value=JSON.parse(readFileSync(path,"utf8")) as Decision;}catch{throw new Error("decision ledger entry corrupt");}
  if(value.schema_version!==1||!sha64.test(value.decision_key))throw new Error("decision ledger schema invalid");
  return value;
}
function sameIdentity(a:Decision,b:Decision){return identityFields.every(field=>a[field]===b[field]);}

export class Ledger {
  constructor(readonly root:string){mkdirSync(root,{recursive:true});}
  private decisionPath(key:string){if(!sha64.test(key))throw new Error("decision key invalid");return join(this.root,`decision-${key}.json`);}
  private claimPath(key:string){return join(this.root,`claim-${key}`);}
  private withClaim<T>(key:string,fn:()=>T):T{
    const claim=this.claimPath(key);let acquired=false;for(let attempt=0;attempt<200;attempt++){try{mkdirSync(claim);acquired=true;break;}catch{Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,10);}}if(!acquired)throw new Error("decision claim timeout");
    try{return fn();}finally{rmSync(claim,{recursive:true,force:true});}
  }
  private ensureEvent(d:Decision){
    const eventPath=join(this.root,"events.jsonl");let found=0;
    if(existsSync(eventPath))for(const line of readFileSync(eventPath,"utf8").split(/\r?\n/).filter(Boolean)){let value:any;try{value=JSON.parse(line);}catch{throw new Error("decision event ledger corrupt");}if(value.decision_key===d.decision_key&&String(value.event).startsWith("operator_policy_"))found++;}
    if(found>1)throw new Error("duplicate decision events");
    if(found===0)appendFileSync(eventPath,`${safeJson({event:"operator_policy_"+d.policy_decision.toLowerCase(),...d})}\n`);
  }
  decisions(){return readdirSync(this.root).filter(n=>n.endsWith(".json")&&!n.startsWith("review-")).map(n=>parseDecision(join(this.root,n)));}
  findByKey(key:string){this.decisionPath(key);const matches=this.decisions().filter(d=>d.decision_key===key);if(matches.length>1)throw new Error("duplicate decisions for key");return matches[0];}
  findByHead(head:string){const matches=this.decisions().filter(d=>d.head_sha===head);if(matches.length>1)throw new Error("duplicate decisions for head");return matches[0];}
  loadOrCreate(key:string,factory:()=>Decision){return this.withClaim(key,()=>{const path=this.decisionPath(key),existing=this.findByKey(key);if(existing){this.ensureEvent(existing);return {decision:existing,created:false};}const d=redactSensitiveData(factory()) as Decision;if(d.decision_key!==key)throw new Error("DECISION_IDENTITY_CONFLICT");const temp=`${path}.${process.pid}.tmp`;writeFileSync(temp,`${JSON.stringify(d,null,2)}\n`,{flag:"wx"});renameSync(temp,path);this.ensureEvent(d);return {decision:d,created:true};});}
  loadOrCreateReview<T extends object>(key:string,factory:()=>T){if(!sha64.test(key))throw new Error("decision key invalid");const reviewClaim=`review-${key}`;return this.withClaim(reviewClaim,()=>{const path=join(this.root,`review-${key}.json`);if(existsSync(path)){let value:T;try{value=JSON.parse(readFileSync(path,"utf8")) as T;}catch{throw new Error("review receipt corrupt");}return {review:value,created:false};}const value=redactSensitiveData(factory()) as T;const temp=`${path}.${process.pid}.tmp`;writeFileSync(temp,`${JSON.stringify(value,null,2)}\n`,{flag:"wx"});renameSync(temp,path);return {review:value,created:true};});}
  recordOrLoad(value:Decision){const d=redactSensitiveData(value) as Decision;const result=this.loadOrCreate(d.decision_key,()=>d);if(!sameIdentity(result.decision,d)||safeJson(result.decision)!==safeJson(d))throw new Error("DECISION_IDENTITY_CONFLICT");return result;}
  record(value:Decision){return this.recordOrLoad(value).decision;}
  load(id:string){const matches=this.decisions().filter(d=>d.decision_id===id);if(matches.length!==1)throw new Error("decision ledger entry missing or duplicate");return matches[0];}
  hasHead(h:string){return existsSync(join(this.root,`head-${h}.done`));}
  private ensureConsumptionEvent(d:Decision){const path=join(this.root,"events.jsonl");let count=0;if(existsSync(path))for(const line of readFileSync(path,"utf8").split(/\r?\n/).filter(Boolean)){let value:any;try{value=JSON.parse(line);}catch{throw new Error("decision event ledger corrupt");}if(value.event==="supervisor_authorization_consumed"&&value.decision_key===d.decision_key)count++;}if(count>1)throw new Error("duplicate authorization receipts");if(count===0)appendFileSync(path,`${safeJson({event:"supervisor_authorization_consumed",decision_key:d.decision_key,authorization_id:d.authorization_id,decision_id:d.decision_id,issue:d.issue,pr:d.pr,base_sha:d.base_sha,head_sha:d.head_sha,action:d.allowed_action,policy_sha256:d.policy_sha256})}\n`);}
  consume(d:Decision){writeFileSync(join(this.root,`head-${d.head_sha}.done`),d.decision_id,{flag:"wx"});this.ensureConsumptionEvent(d);}
  ensureConsumed(d:Decision){this.withClaim(d.decision_key,()=>{const path=join(this.root,`head-${d.head_sha}.done`);if(!existsSync(path))writeFileSync(path,d.decision_id,{flag:"wx"});else if(readFileSync(path,"utf8")!==d.decision_id)throw new Error("head consumed by different decision");this.ensureConsumptionEvent(d);});}
}
