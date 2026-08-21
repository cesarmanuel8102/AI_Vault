import {createHash,randomUUID} from "node:crypto";
import {appendFileSync,existsSync,mkdirSync,readFileSync,renameSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import type {ReviewerBackend,ReviewerInput,ReviewerRun} from "./reviewer_backend.js";
import {ReviewerBackendError} from "./reviewer_backend.js";
import {OpenCodeReviewerBackend} from "./opencode_reviewer.js";
import {REVIEWER_MODELS,REVIEWER_QUALIFICATION,reviewerRoute} from "./reviewer_config.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {redactedError} from "./redaction.js";

const canonical=(value:unknown)=>JSON.stringify(value,(_k,v)=>v&&typeof v==="object"&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
const keyOf=(input:ReviewerInput)=>createHash("sha256").update(canonical({repository:input.repository,pr:input.pr,base_sha:input.baseSha,head_sha:input.headSha,risk:input.risk,changed_files:[...input.changedFiles].sort(),builder_session:input.builderSession,builder_model:input.builderModel??null})).digest("hex");
const qualified=(model:string)=>Boolean((REVIEWER_QUALIFICATION as Record<string,{qualified:boolean}>)[model]?.qualified);
const identityOf=(input:ReviewerInput)=>({repository:input.repository,pr:input.pr,baseSha:input.baseSha,headSha:input.headSha,risk:input.risk,changedFiles:[...input.changedFiles].sort(),builderSession:input.builderSession,builderModel:input.builderModel??null});
const singleEvidenceHash=(saved:Pick<ReviewerRun,"review_mode"|"primary_output">)=>createHash("sha256").update(canonical({review_mode:saved.review_mode,primary_output:saved.primary_output})).digest("hex");
const legacyEvidenceHash=(saved:ReviewerRun)=>createHash("sha256").update(canonical({primary_output:saved.primary_output,verifier:saved.verifier,arbiter:saved.arbiter??null})).digest("hex");

export function validateReviewerRunReceipt(saved:ReviewerRun,input:ReviewerInput,receiptKey=keyOf(input)){
  if(!saved||saved.schema_version!==1||saved.receipt_key!==receiptKey||canonical(saved.identity)!==canonical(identityOf(input))||saved.backend!=="opencode_ollama"||!saved.output||saved.output.head_sha!==input.headSha||!saved.primary_output||!/^[a-f0-9]{64}$/.test(saved.evidence_sha256)||typeof saved.session!=="string"||typeof saved.providerSession!=="string"||saved.session===input.builderSession||!Array.isArray(saved.attempts))throw new Error("review receipt identity mismatch");
  if(saved.review_mode==="single-deepseek-pro"){
    const passed=saved.attempts.filter(item=>item.status==="PASS");
    if(saved.model!==REVIEWER_MODELS.deepseekPro||input.builderModel===REVIEWER_MODELS.deepseekPro||saved.verifier||saved.arbiter||saved.evidence_sha256!==singleEvidenceHash(saved)||canonical(passed.map(item=>({model:item.model,session:item.session})))!==canonical([{model:saved.model,session:saved.session}])||saved.attempts.some(item=>item.model!==REVIEWER_MODELS.deepseekPro)||canonical(saved.output)!==canonical(normalizeReviewerOutput(saved.primary_output,input.headSha)))throw new Error("single reviewer receipt invalid");
    saved.output=normalizeReviewerOutput(saved.primary_output,input.headSha);return saved;
  }
  // Legacy quorum receipts remain readable for already-persisted lifecycle evidence.
  if(!saved.verifier?.output||saved.evidence_sha256!==legacyEvidenceHash(saved)||!qualified(saved.model)||!qualified(saved.verifier.model)||saved.model===saved.verifier.model||saved.model===input.builderModel||saved.verifier.model===input.builderModel||saved.verifier.session===saved.session||saved.verifier.session===input.builderSession)throw new Error("legacy review receipt invalid");
  return saved;
}

export function validateReviewerEnvelope(value:any,expected:{issue:number;pr:number;base_sha:string;head_sha:string;front_id:string;builder_session:string;builder_model:string},input:ReviewerInput){
  if(!value||value.schema_version!==1||value.issue!==expected.issue||value.pr!==expected.pr||value.base_sha!==expected.base_sha||value.head_sha!==expected.head_sha||value.front_id!==expected.front_id||value.builder_session!==expected.builder_session||value.builder_model!==expected.builder_model||typeof value.session!=="string"||value.session===expected.builder_session||!value.router_run)throw new Error("outer review receipt identity mismatch");
  const run=validateReviewerRunReceipt(value.router_run,input);if(value.session!==run.session||canonical(value.result)!==canonical(run.output))throw new Error("outer review receipt evidence mismatch");return value;
}

export class ReviewerRouter {
  constructor(readonly root:string,private readonly factory:(model:string)=>ReviewerBackend=model=>new OpenCodeReviewerBackend(model)){mkdirSync(join(root,"reviews"),{recursive:true});}
  private circuitEvents(){const path=join(this.root,"reviewer-circuit-events.jsonl");if(!existsSync(path))return [] as any[];return readFileSync(path,"utf8").split(/\r?\n/).filter(Boolean).map(line=>{try{return JSON.parse(line);}catch{throw new Error("reviewer circuit ledger corrupt");}});}
  private circuitOpen(model:string){const relevant=this.circuitEvents().filter(e=>e.model===model);let lastSuccess=-1;for(let i=0;i<relevant.length;i++)if(relevant[i].event==="reviewer_backend_succeeded")lastSuccess=i;const failures=relevant.slice(lastSuccess+1).filter(e=>e.event==="reviewer_backend_failed");if(failures.length<3)return false;const last=Date.parse(failures[failures.length-1].created_utc);return Number.isFinite(last)&&Date.now()-last<300000;}
  private circuitEvent(event:string,model:string,failureClass?:string){appendFileSync(join(this.root,"reviewer-circuit-events.jsonl"),`${JSON.stringify({schema_version:1,event,model,...(failureClass?{failure_class:failureClass}:{}),created_utc:new Date().toISOString()})}\n`);}
  review(input:ReviewerInput):ReviewerRun{
    const receiptKey=keyOf(input),path=join(this.root,"reviews",`review-${receiptKey}.json`);
    if(existsSync(path))return validateReviewerRunReceipt(JSON.parse(readFileSync(path,"utf8")) as ReviewerRun,input,receiptKey);
    const [model]=reviewerRoute(input);if(model!==REVIEWER_MODELS.deepseekPro)throw new ReviewerBackendError("DeepSeek Pro reviewer conflicts with builder; manual Codex review required","REVIEWER_MODEL_CONFLICT");
    if(this.circuitOpen(model))throw new ReviewerBackendError("DeepSeek Pro reviewer circuit open; manual Codex review required","CIRCUIT_OPEN");
    const attempts:ReviewerRun["attempts"]=[];
    for(let n=0;n<2;n++){
      const session=`reviewer:opencode_ollama:${model}:${randomUUID()}`;
      try{
        const selected=this.factory(model).review(input,session),primary_output=normalizeReviewerOutput(selected.output,input.headSha);attempts.push({model,session,status:"PASS"});this.circuitEvent("reviewer_backend_succeeded",model);
        const run:ReviewerRun={schema_version:1,review_mode:"single-deepseek-pro",receipt_key:receiptKey,evidence_sha256:"",identity:identityOf(input),...selected,output:primary_output,primary_output,attempts};run.evidence_sha256=singleEvidenceHash(run);
        const temp=`${path}.${process.pid}.tmp`;writeFileSync(temp,`${JSON.stringify(run,null,2)}\n`,{flag:"wx"});renameSync(temp,path);return run;
      }catch(error){const failure=error instanceof ReviewerBackendError?error:new ReviewerBackendError(redactedError(error),"REVIEWER_BACKEND_FAILURE");attempts.push({model,session,status:"FAILED",failure_class:failure.failureClass});this.circuitEvent("reviewer_backend_failed",model,failure.failureClass);if(!failure.transient||n===1)break;}
    }
    throw new ReviewerBackendError("DeepSeek Pro reviewer unavailable; manual Codex review required","SINGLE_REVIEWER_UNAVAILABLE");
  }
}
