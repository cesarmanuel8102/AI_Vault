import {mkdirSync,existsSync,writeFileSync,appendFileSync,readdirSync,readFileSync} from "node:fs";
import {join} from "node:path";
import type {Decision} from "./types.js";
import {redactSensitiveData,safeJson} from "./redaction.js";

export class Ledger {
  constructor(readonly root:string){mkdirSync(root,{recursive:true});}
  hasHead(h:string){return existsSync(join(this.root,`head-${h}.done`));}
  record(value:Decision){const d=redactSensitiveData(value);const p=join(this.root,`${d.created_utc.replace(/[:.]/g,"-")}-${d.decision_id}.json`);writeFileSync(p,`${JSON.stringify(d,null,2)}\n`,{flag:"wx"});appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"operator_policy_"+d.policy_decision.toLowerCase(),...d})}\n`);}
  decisions(){return readdirSync(this.root).filter(n=>/\.json$/.test(n)).map(n=>JSON.parse(readFileSync(join(this.root,n),"utf8")) as Decision);}
  findByHead(head:string){const matches=this.decisions().filter(d=>d.head_sha===head);if(matches.length>1)throw new Error("duplicate decisions for head");return matches[0];}
  load(id:string){const names=readdirSync(this.root).filter(n=>n.endsWith(`-${id}.json`));if(names.length!==1)throw new Error("decision ledger entry missing or duplicate");const d=JSON.parse(readFileSync(join(this.root,names[0]),"utf8")) as Decision;if(d.decision_id!==id)throw new Error("decision ledger identity mismatch");return d;}
  consume(d:Decision){writeFileSync(join(this.root,`head-${d.head_sha}.done`),d.decision_id,{flag:"wx"});appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"supervisor_authorization_consumed",authorization_id:d.authorization_id,decision_id:d.decision_id,issue:d.issue,pr:d.pr,base_sha:d.base_sha,head_sha:d.head_sha,action:d.allowed_action,policy_sha256:d.policy_sha256})}\n`);}
  ensureConsumed(d:Decision){const path=join(this.root,`head-${d.head_sha}.done`);if(!existsSync(path)){this.consume(d);return;}if(readFileSync(path,"utf8")!==d.decision_id)throw new Error("head consumed by different decision");}
}
