import {createHash,randomUUID} from "node:crypto";
import {appendFileSync,existsSync,mkdirSync,readFileSync,renameSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import type {ReviewerBackend,ReviewerInput,ReviewerRun} from "./reviewer_backend.js";
import {ReviewerBackendError} from "./reviewer_backend.js";
import {OpenCodeReviewerBackend} from "./opencode_reviewer.js";
import {REVIEWER_QUALIFICATION,reviewerArbiter,reviewerRoute} from "./reviewer_config.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {redactedError} from "./redaction.js";
import type {ReviewerOutput} from "./types.js";

const canonical=(value:unknown)=>JSON.stringify(value,(_k,v)=>v&&typeof v==="object"&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
const keyOf=(input:ReviewerInput)=>createHash("sha256").update(canonical({repository:input.repository,pr:input.pr,base_sha:input.baseSha,head_sha:input.headSha,risk:input.risk,changed_files:[...input.changedFiles].sort(),builder_session:input.builderSession,builder_model:input.builderModel??null})).digest("hex");
type BackendFactory=(model:string)=>ReviewerBackend;

const qualified=(model:string)=>Boolean((REVIEWER_QUALIFICATION as Record<string,{qualified:boolean}>)[model]?.qualified);
const evidenceHash=(saved:Pick<ReviewerRun,"primary_output"|"verifier"|"arbiter">)=>createHash("sha256").update(canonical({primary_output:saved.primary_output,verifier:saved.verifier,arbiter:saved.arbiter??null})).digest("hex");
function synthesizeOutput(primary:ReviewerOutput,verifier:ReviewerOutput,arbiter?:ReviewerOutput):{output:ReviewerOutput;requiresArbiter:boolean}{
  const disagreement=primary.verdict!==verifier.verdict,hasP0=[...primary.findings,...verifier.findings].some(f=>f.severity==="P0"),requiresArbiter=hasP0||disagreement;
  let output=primary;
  if(!disagreement&&primary.verdict==="CHANGES_REQUESTED"){const unique=new Map([...primary.findings,...verifier.findings].map(finding=>[canonical(finding),finding]));output={...primary,summary:"Independent reviewers requested bounded repairs",findings:[...unique.values()]};}
  if(requiresArbiter){if(!arbiter)throw new Error("review receipt arbiter evidence missing");const unique=new Map([...primary.findings,...verifier.findings,...arbiter.findings].map(finding=>[canonical(finding),finding]));output={...primary,verdict:"BLOCKED",summary:`${hasP0?"P0":"reviewer disagreement"} escalated after independent arbiter: ${arbiter.verdict}`,findings:[...unique.values()]};}
  return {output,requiresArbiter};
}
export function validateReviewerRunReceipt(saved:ReviewerRun,input:ReviewerInput,receiptKey=keyOf(input)){
  const identity={repository:input.repository,pr:input.pr,baseSha:input.baseSha,headSha:input.headSha,risk:input.risk,changedFiles:[...input.changedFiles].sort(),builderSession:input.builderSession,builderModel:input.builderModel??null},route=reviewerRoute(input);
  if(!saved||saved.schema_version!==1||saved.receipt_key!==receiptKey||canonical(saved.identity)!==canonical(identity)||saved.backend!=="opencode_ollama"||!saved.output||saved.output.head_sha!==input.headSha||!saved.primary_output||!saved.verifier?.output||!/^[a-f0-9]{64}$/.test(saved.evidence_sha256)||saved.evidence_sha256!==evidenceHash(saved)||typeof saved.session!=="string"||typeof saved.providerSession!=="string"||saved.session===input.builderSession||!route.includes(saved.model)||!qualified(saved.model)||!route.includes(saved.verifier.model)||!qualified(saved.verifier.model)||saved.verifier.model===saved.model||saved.verifier.session===input.builderSession||saved.verifier.session===saved.session||typeof saved.verifier.providerSession!=="string"||saved.verifier.providerSession===saved.providerSession||!Array.isArray(saved.attempts))throw new Error("review receipt identity mismatch");
  const passed=saved.attempts.filter(item=>item.status==="PASS");if(canonical(passed.map(item=>({model:item.model,session:item.session})))!==canonical([{model:saved.model,session:saved.session},{model:saved.verifier.model,session:saved.verifier.session}])||saved.attempts.some(item=>!route.includes(item.model)||item.model===input.builderModel))throw new Error("review receipt route mismatch");
  const primary=normalizeReviewerOutput(saved.primary_output,input.headSha),verifier=normalizeReviewerOutput(saved.verifier.output,input.headSha);if(saved.verifier.verdict!==verifier.verdict)throw new Error("review receipt quorum mismatch");const synthesized=synthesizeOutput(primary,verifier,saved.arbiter?normalizeReviewerOutput(saved.arbiter.output,input.headSha):undefined);
  if(synthesized.requiresArbiter){const expected=reviewerArbiter(input,[saved.model,saved.verifier.model]);if(!saved.arbiter||saved.arbiter.model!==expected||!qualified(saved.arbiter.model)||saved.arbiter.model===input.builderModel||[saved.model,saved.verifier.model].includes(saved.arbiter.model)||saved.arbiter.verdict!==saved.arbiter.output.verdict||typeof saved.arbiter.session!=="string"||typeof saved.arbiter.providerSession!=="string"||saved.arbiter.session===input.builderSession||[saved.session,saved.verifier.session].includes(saved.arbiter.session)||[saved.providerSession,saved.verifier.providerSession].includes(saved.arbiter.providerSession))throw new Error("review receipt arbiter mismatch");}else if(saved.arbiter)throw new Error("review receipt quorum mismatch");
  if(canonical(saved.output)!==canonical(synthesized.output))throw new Error("review receipt synthesized output mismatch");saved.output=synthesized.output;return saved;
}
export function validateReviewerEnvelope(value:any,expected:{issue:number;pr:number;base_sha:string;head_sha:string;front_id:string;builder_session:string;builder_model:string},input:ReviewerInput){
  if(!value||value.schema_version!==1||value.issue!==expected.issue||value.pr!==expected.pr||value.base_sha!==expected.base_sha||value.head_sha!==expected.head_sha||value.front_id!==expected.front_id||value.builder_session!==expected.builder_session||value.builder_model!==expected.builder_model||typeof value.session!=="string"||value.session===expected.builder_session||!value.router_run)throw new Error("outer review receipt identity mismatch");
  const run=validateReviewerRunReceipt(value.router_run,input);if(value.session!==run.session||canonical(value.result)!==canonical(run.output))throw new Error("outer review receipt evidence mismatch");return value;
}

export class ReviewerRouter {
  constructor(readonly root:string,private readonly factory:BackendFactory=model=>new OpenCodeReviewerBackend(model)){mkdirSync(join(root,"reviews"),{recursive:true});}
  private circuitEvents(){const path=join(this.root,"reviewer-circuit-events.jsonl");if(!existsSync(path))return [] as any[];return readFileSync(path,"utf8").split(/\r?\n/).filter(Boolean).map(line=>{try{return JSON.parse(line);}catch{throw new Error("reviewer circuit ledger corrupt");}});}
  private circuitOpen(model:string){const relevant=this.circuitEvents().filter(e=>e.model===model);let lastSuccess=-1;for(let i=0;i<relevant.length;i++)if(relevant[i].event==="reviewer_backend_succeeded")lastSuccess=i;const failures=relevant.slice(lastSuccess+1).filter(e=>e.event==="reviewer_backend_failed");if(failures.length<3)return false;const last=Date.parse(failures[failures.length-1].created_utc);return Number.isFinite(last)&&Date.now()-last<300000;}
  private circuitEvent(event:string,model:string,failureClass?:string){appendFileSync(join(this.root,"reviewer-circuit-events.jsonl"),`${JSON.stringify({schema_version:1,event,model,...(failureClass?{failure_class:failureClass}:{}),created_utc:new Date().toISOString()})}\n`);}
  review(input:ReviewerInput):ReviewerRun{
    const receiptKey=keyOf(input),path=join(this.root,"reviews",`review-${receiptKey}.json`),identity={repository:input.repository,pr:input.pr,baseSha:input.baseSha,headSha:input.headSha,risk:input.risk,changedFiles:[...input.changedFiles].sort(),builderSession:input.builderSession,builderModel:input.builderModel??null};
    if(existsSync(path))return validateReviewerRunReceipt(JSON.parse(readFileSync(path,"utf8")) as ReviewerRun,input,receiptKey);
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
    const selected=successful[0],verification=successful[1],primaryOutput=normalizeReviewerOutput(selected.output,input.headSha),verifierOutput=normalizeReviewerOutput(verification.output,input.headSha),disagreement=primaryOutput.verdict!==verifierOutput.verdict,hasP0=[...primaryOutput.findings,...verifierOutput.findings].some(f=>f.severity==="P0");
    let arbiter:ReviewerRun["arbiter"];
    if(hasP0||disagreement){
      const arbiterModel=reviewerArbiter(input,successful.map(run=>run.model));if(!arbiterModel)throw new ReviewerBackendError("qualified independent arbiter unavailable","P0_ARBITER_UNAVAILABLE");
      const session=`reviewer:opencode_ollama:${arbiterModel}:${randomUUID()}`;
      const arbiterInput={...input,panelEvidence:{primary:{model:selected.model,output:primaryOutput},verifier:{model:verification.model,output:verifierOutput}}};
      try{const result=this.factory(arbiterModel).review(arbiterInput,session),output=normalizeReviewerOutput(result.output,input.headSha);arbiter={model:arbiterModel,session,providerSession:result.providerSession,verdict:output.verdict,output};}catch(error){throw new ReviewerBackendError(redactedError(error),"P0_ARBITER_UNAVAILABLE");}
    }
    const output=synthesizeOutput(primaryOutput,verifierOutput,arbiter?.output).output,verifier={model:verification.model,session:verification.session,providerSession:verification.providerSession,verdict:verifierOutput.verdict,output:verifierOutput},evidence_sha256=evidenceHash({primary_output:primaryOutput,verifier,arbiter});
    const run:ReviewerRun={schema_version:1,receipt_key:receiptKey,evidence_sha256,identity,...selected,output,primary_output:primaryOutput,attempts,verifier,...(arbiter?{arbiter}:{})};
    const temp=`${path}.${process.pid}.tmp`;writeFileSync(temp,`${JSON.stringify(run,null,2)}\n`,{flag:"wx"});renameSync(temp,path);return run;
  }
}
