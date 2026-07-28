import type {BuildResult} from "./autonomous_flow.js";
import type {ProxySpec} from "./types.js";
import {agentLoopIssueBody,parseAgentLoopIssue,parseIssue} from "./spec_contract.js";

const PHASES=new Set(["agent:queued","loop:executing","loop:ci","loop:repairing","loop:ready-human-audit","loop:blocked","loop:failed","loop:token-exhausted","loop:accepted"]);
const TERMINAL=new Set(["loop:ready-human-audit","loop:blocked","loop:failed","loop:token-exhausted","loop:accepted"]);

export interface AgentLoopBus {
  createGovernedIssue(title:string,body:string,label?:string):number;
  issueSnapshot(issue:number):{state:string;body:string;labels:string[]};
  reconcileLabel(kind:"issue"|"pr",n:number,add:string,remove?:string[]):void;
  findPrByBranch(branch:string):{number:number;head_sha:string}|undefined;
  prIdentity(pr:number):any;
  bindPrToIssue(issue:number,pr:number):void;
}

function exactLine(body:string,value:string){return body.split(/\r?\n/).filter(line=>line.trim()===value).length===1;}

export class AgentLoopBuilderAdapter {
  constructor(readonly bus:AgentLoopBus){}
  private validateIssue(spec:ProxySpec,issue:number){
    const snapshot=this.bus.issueSnapshot(issue);
    if(snapshot.state!=="OPEN")throw new Error("agent loop Issue is not open");
    const governed=parseIssue(snapshot.body).spec;
    if(JSON.stringify(governed)!==JSON.stringify(spec))throw new Error("operator proxy spec mismatch");
    if(!exactLine(snapshot.body,`FRONT_ID: ${spec.front_id}`))throw new Error("operator proxy front mismatch");
    parseAgentLoopIssue(snapshot.body,spec);
    const phases=snapshot.labels.filter(label=>PHASES.has(label));
    if(phases.some(label=>TERMINAL.has(label)))throw new Error("agent loop Issue is terminal");
    if(phases.length>1)throw new Error("agent loop Issue phase is ambiguous");
    return phases;
  }
  ensureIssue(spec:ProxySpec,existing:number[]){
    if(spec.executor!=="agent_loop")throw new Error("agent loop adapter executor mismatch");
    if(existing.length>1)throw new Error("duplicate governed Issues");
    if(!existing.length)return this.bus.createGovernedIssue(`feat(agent-loop): ${spec.objective}`,agentLoopIssueBody(spec),"agent:queued");
    const issue=existing[0],phases=this.validateIssue(spec,issue);
    if(phases.length===0)this.bus.reconcileLabel("issue",issue,"agent:queued");
    return issue;
  }
  observe(spec:ProxySpec,issue:number,repairCycle:number,previousHead?:string):BuildResult|"PENDING"{
    if(spec.executor!=="agent_loop"||!spec.work_branch)throw new Error("agent loop adapter metadata missing");
    this.validateIssue(spec,issue);
    const existing=this.bus.findPrByBranch(spec.work_branch);if(!existing)return "PENDING";
    const pr=this.bus.prIdentity(existing.number);
    if(pr.state!=="OPEN"||pr.isDraft!==true||pr.baseRefName!=="codex/own-capital-sustainable-return"||pr.baseRefOid!==spec.expected_base_sha||pr.headRefName!==spec.work_branch||pr.headRefOid!==existing.head_sha)throw new Error("agent loop PR identity mismatch");
    if(!exactLine(String(pr.body??""),`AGENT_LOOP_FRONT: ${spec.front_id}`)||!exactLine(String(pr.body??""),`AGENT_LOOP_ISSUE: #${issue}`))throw new Error("agent loop PR evidence mismatch");
    if(repairCycle>0&&existing.head_sha===previousHead)return "PENDING";
    this.bus.bindPrToIssue(issue,existing.number);
    return {pr:existing.number,head_sha:existing.head_sha,session:`agent-loop-builder-${existing.head_sha}`};
  }
}
