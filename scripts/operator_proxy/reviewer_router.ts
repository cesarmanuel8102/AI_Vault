import {createHash,randomUUID} from "node:crypto";
import {appendFileSync,existsSync,mkdirSync,readFileSync,renameSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import type {ReviewerBackend,ReviewerInput,ReviewerRun} from "./reviewer_backend.js";
import {ReviewerBackendError} from "./reviewer_backend.js";
import {OpenCodeReviewerBackend} from "./opencode_reviewer.js";
import {reviewerArbiter,reviewerRoute} from "./reviewer_config.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {redactedError} from "./redaction.js";

const canonical=(value:unknown)=>JSON.stringify(value,(_k,v)=>v&&typeof v==="object"&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
const keyOf=(input:ReviewerInput)=>createHash("sha256").update(canonical({repository:input.repository,pr:input.pr,base_sha:input.baseSha,head_sha:input.headSha,risk:input.risk,changed_files:[...input.changedFiles].sort(),builder_session:input.builderSession,builder_model:input.builderModel??null})).digest("hex");
type BackendFactory=(model:string)=>ReviewerBackend;

export class ReviewerRouter {
  constructor(readonly root:string,private readonly factory:BackendFactory=model=>new OpenCodeReviewerBackend(model)){mkdirSync(join(root,"reviews"),{recursive:true});}
  private circuitEvents(){const path=join(this.root,"reviewer-circuit-events.jsonl");if(!existsSync(path))return [] as any[];return readFileSync(path,"utf8").split(/\r?\n/).filter(Boolean).map(line=>{try{return JSON.parse(line);}catch{throw new Error("reviewer circuit ledger corrupt");}});}
  private circuitOpen(model:string){const relevant=this.circuitEvents().filter(e=>e.model===model);let lastSuccess=-1;for(let i=0;i<relevant.length;i++)if(relevant[i].event==="reviewer_backend_succeeded")lastSuccess=i;const failures=relevant.slice(lastSuccess+1).filter(e=>e.event==="reviewer_backend_failed");if(failures.length<3)return false;const last=Date.parse(failures[failures.length-1].created_utc);return Number.isFinite(last)&&Date.now()-last<300000;}
  private circuitEvent(event:string,model:string,failureClass?:string){appendFileSync(join(this.root,"reviewer-circuit-events.jsonl"),`${JSON.stringify({schema_version:1,event,model,...(failureClass?{failure_class:failureClass}:{}),created_utc:new Date().toISOString()})}\n`);}
  review(input:ReviewerInput):ReviewerRun{
    const receiptKey=keyOf(input),path=join(this.root,"reviews",`review-${receiptKey}.json`),identity={repository:input.repository,pr:input.pr,baseSha:input.baseSha,headSha:input.headSha,risk:input.risk,changedFiles:[...input.changedFiles].sort(),builderSession:input.builderSession,builderModel:input.builderModel??null};
    if(existsSync(path)){const saved=JSON.parse(readFileSync(path,"utf8")) as ReviewerRun;if(saved.schema_version!==1||saved.receipt_key!==receiptKey||canonical(saved.identity)!==canonical(identity)||saved.backend!=="opencode_ollama"||saved.output.head_sha!==input.headSha||typeof saved.model!=="string"||typeof saved.session!=="string"||typeof saved.providerSession!=="string"||saved.session===input.builderSession||!saved.verifier||typeof saved.verifier.providerSession!=="string"||saved.verifier.session===input.builderSession||saved.verifier.session===saved.session||saved.verifier.providerSession===saved.providerSession||!Array.isArray(saved.attempts))throw new Error("review receipt identity mismatch");saved.output=normalizeReviewerOutput(saved.output,input.headSha);return saved;}
    const attempts:ReviewerRun["attempts"]=[],successful:any[]=[];
    for(const model of reviewerRoute(input)){
      if(this.circuitOpen(model)){attempts.push({model,session:"circuit-open",status:"FAILED",failure_class:"CIRCUIT_OPEN"});continue;}
      for(let n=0;n<2;n++){
        const session=`reviewer:opencode_ollama:${model}:${randomUUID()}`;
        try{successful.push(this.factory(model).review(input,session));attempts.push({model,session,status:"PASS"});this.circuitEvent("reviewer_backend_succeeded",model);break;}
        catch(error){const failure=error instanceof ReviewerBackendError?error:new ReviewerBackendError(redactedError(error),"REVIEWER_BACKEND_FAILURE");attempts.push({model,session,status:"FAILED",failure_class:failure.failureClass});this.circuitEvent("reviewer_backend_failed",model,failure.failureClass);if(!failure.transient||n===1)break;}
      }
      if(successful.length===2)break;
    }
    if(successful.length!==2)throw new ReviewerBackendError("independent reviewer quorum unavailable","BLOCKED_EXTERNAL_REVIEWER");
    const selected=successful[0],verification=successful[1],disagreement=selected.output.verdict!==verification.output.verdict,hasP0=successful.some(run=>run.output.findings.some((f:any)=>f.severity==="P0"));
    if(!disagreement&&selected.output.verdict==="CHANGES_REQUESTED"){
      const findings=[...selected.output.findings,...verification.output.findings],unique=new Map(findings.map((finding:any)=>[canonical(finding),finding]));
      selected.output={...selected.output,summary:"Independent reviewers requested bounded repairs",findings:[...unique.values()]};
    }
    let arbiter:ReviewerRun["arbiter"];
    if(hasP0||disagreement){
      const arbiterModel=reviewerArbiter(input,successful.map(run=>run.model));if(!arbiterModel)throw new ReviewerBackendError("qualified independent arbiter unavailable","P0_ARBITER_UNAVAILABLE");
      const session=`reviewer:opencode_ollama:${arbiterModel}:${randomUUID()}`;
      const arbiterInput={...input,panelEvidence:{primary:{model:selected.model,output:selected.output},verifier:{model:verification.model,output:verification.output}}};
      try{const result=this.factory(arbiterModel).review(arbiterInput,session);arbiter={model:arbiterModel,session,providerSession:result.providerSession,verdict:result.output.verdict};}catch(error){throw new ReviewerBackendError(redactedError(error),"P0_ARBITER_UNAVAILABLE");}
      selected.output={...selected.output,verdict:"BLOCKED",summary:`${hasP0?"P0":"reviewer disagreement"} escalated after independent arbiter: ${arbiter.verdict}`};
    }
    const run:ReviewerRun={schema_version:1,receipt_key:receiptKey,identity,...selected,attempts,verifier:{model:verification.model,session:verification.session,providerSession:verification.providerSession,verdict:verification.output.verdict},...(arbiter?{arbiter}:{})};
    const temp=`${path}.${process.pid}.tmp`;writeFileSync(temp,`${JSON.stringify(run,null,2)}\n`,{flag:"wx"});renameSync(temp,path);return run;
  }
}
