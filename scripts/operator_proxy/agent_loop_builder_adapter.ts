import type {BuildResult} from "./autonomous_flow.js";
import type {ProxySpec} from "./types.js";
import {agentLoopIssueBody,parseAgentLoopIssue,parseIssue} from "./spec_contract.js";

const PHASES=new Set(["agent:queued","loop:executing","loop:ci","loop:repairing","loop:ready-human-audit","loop:blocked","loop:failed","loop:token-exhausted","loop:accepted"]);
const TERMINAL=new Set(["loop:ready-human-audit","loop:blocked","loop:failed","loop:token-exhausted","loop:accepted"]);

export interface AgentLoopBus {
  createGovernedIssue(title:string,body:string,label?:string):number;
  issueSnapshot(issue:number):{state:string;body:string;labels:string[]};
  reconcileLabel(kind:"issue"|"pr",n:number,add:string,remove?:string[]):void;
  prCandidatesByBranch(branch:string):any[];
  prIdentity(pr:number):any;
  bindPrToIssue(issue:number,pr:number):void;
}

function exactLine(body:string,value:string){return body.split(/\r?\n/).filter(line=>line.trim()===value).length===1;}
const REPO="cesarmanuel8102/AI_Vault",BASE="codex/own-capital-sustainable-return";
function trustedIdentity(value:any,spec:ProxySpec){return value?.isCrossRepository===false&&value?.headRepository?.nameWithOwner===REPO&&value?.author?.login==="cesarmanuel8102"&&value?.headRefName===spec.work_branch&&value?.baseRefName===BASE&&value?.baseRefOid===spec.expected_base_sha&&value?.state==="OPEN"&&value?.isDraft===true&&/^[0-9a-f]{40}$/.test(String(value?.headRefOid??""));}

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
    const phases=this.validateIssue(spec,issue),candidates=this.bus.prCandidatesByBranch(spec.work_branch);
    const trusted=candidates.filter(candidate=>trustedIdentity(candidate,spec));
    if(trusted.length!==1){if(candidates.length===0&&!phases.some(phase=>phase==="loop:ci"||phase==="loop:repairing"))return "PENDING";throw new Error(`agent loop trusted PR candidate count invalid: ${trusted.length}`);}
    const selected=trusted[0],pr=this.bus.prIdentity(Number(selected.number));
    if(!trustedIdentity(pr,spec)||Number(selected.number)!==Number(pr.number??selected.number)||pr.headRefOid!==selected.headRefOid)throw new Error("agent loop PR identity mismatch");
    if(!exactLine(String(pr.body??""),`AGENT_LOOP_FRONT: ${spec.front_id}`)||!exactLine(String(pr.body??""),`AGENT_LOOP_ISSUE: #${issue}`))throw new Error("agent loop PR evidence mismatch");
    if(repairCycle>0&&pr.headRefOid===previousHead)return "PENDING";
    this.bus.bindPrToIssue(issue,Number(selected.number));
    return {pr:Number(selected.number),head_sha:String(pr.headRefOid),session:`agent-loop-builder-${pr.headRefOid}`};
  }
}
