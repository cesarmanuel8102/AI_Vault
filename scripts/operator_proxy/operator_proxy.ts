import {existsSync,mkdirSync} from "node:fs";
import {join} from "node:path";
import {randomUUID} from "node:crypto";
import {lock} from "./single_instance_lock.js";
import {Ledger} from "./decision_ledger.js";
import {GitHubBus} from "./github_bus.js";
import {collect} from "./evidence_collector.js";
import {decide} from "./policy_engine.js";
import {resolveReviewerRepository,runReviewer} from "./codex_reviewer.js";
import {execute} from "./action_executor.js";
import {parseIssue} from "./spec_contract.js";
import {runAutonomousRoadmapTick} from "./autonomous_runtime.js";

const args=new Set(process.argv.slice(2));
const root=process.env.OPERATOR_PROXY_ROOT??"C:\\AI_VAULT_CODEX_BRIDGE";
const dry=args.has("--dry-run");

function review(cwd:string,pr:number,base:string,head:string){
  const session=`reviewer-${randomUUID()}`;
  try {const result=runReviewer(process.env.CODEX_PATH??"codex",`Independently review PR #${pr} at exact base ${base} and HEAD ${head}. Inspect the complete diff and checks. Do not modify files. Return strict schema JSON; PASS only with no P0/P1 findings.`,cwd,session);if(result.head_sha!==head)throw new Error("review head mismatch");return {result,session};}
  catch{return {result:{verdict:"BLOCKED" as const,head_sha:head,summary:"reviewer unavailable or invalid",findings:[{severity:"P1" as const,title:"review unavailable",evidence:"fail closed",required_correction:"restore independent reviewer"}]},session};}
}

if(args.has("--doctor")){
  try{const reviewer_repository=resolveReviewerRepository();console.log(JSON.stringify({status:"PASS",node:process.version,root,reviewer_repository,pause:existsSync(join(root,"state","PAUSE"))}));process.exit(0);}
  catch(error){console.log(JSON.stringify({status:"BLOCKED",node:process.version,root,error:error instanceof Error?error.message:String(error)}));process.exit(1);}
}

const reviewerRepo=resolveReviewerRepository();mkdirSync(join(root,"state"),{recursive:true});const release=lock(join(root,"state","operator-proxy.lock"));
try {
  if(existsSync(join(root,"state","PAUSE"))){console.log(JSON.stringify({status:"PAUSED"}));process.exit(0);}
  const bus=new GitHubBus(process.env.GH_PATH??"gh");const ledger=new Ledger(join(root,"decisions"));let autonomous:any={status:"SKIPPED_DRY_RUN"};
  if(!dry){try{autonomous={status:"PASS",state:runAutonomousRoadmapTick(bus,root,reviewerRepo)};}catch(error){autonomous={status:"BLOCKED",error:error instanceof Error?error.message:String(error)};}}
  const queued=bus.queued();const results=[];
  for(const issue of queued){
    try {
      if((issue.labels??[]).some((x:any)=>x.name==="operator:pause")){results.push({issue:issue.number,status:"PAUSED"});continue;}
      const {spec,pr}=parseIssue(issue.body);if(!pr){results.push({issue:issue.number,status:"AWAITING_AUTONOMOUS_BUILDER"});continue;}
      const initial=bus.json(["pr","view",String(pr),"--json","baseRefOid,headRefOid"]);const rv=dry?{result:{verdict:"BLOCKED" as const,head_sha:initial.headRefOid,summary:"dry run",findings:[]},session:`dry-reviewer-${randomUUID()}`}:review(reviewerRepo,pr,initial.baseRefOid,initial.headRefOid);const evidence=collect(bus,issue.number,pr,rv.session,rv.result,spec);const decision=decide(spec,evidence);ledger.record(decision);
      if(!dry){execute(bus,ledger,decision,false);const label=decision.policy_decision==="APPROVE"?"operator:completed":decision.policy_decision==="REPAIR"?"operator:repairing":decision.policy_decision==="ESCALATE_TO_OWNER"?"operator:escalated":"operator:blocked";bus.label("issue",issue.number,label,["operator:queued","operator:building","operator:reviewing"]);bus.prComment(pr,`[OPERATOR-PROXY][DECISION]\n\ndecision_id=${decision.decision_id}\npolicy_decision=${decision.policy_decision}\nhead=${decision.head_sha}`);}
      results.push({issue:issue.number,pr,decision});
    } catch(error){results.push({issue:issue.number,status:"BLOCKED",error:error instanceof Error?error.message:String(error)});}
  }
  const status=autonomous.status==="BLOCKED"?"BLOCKED":"PASS";console.log(JSON.stringify({status,dry_run:dry,autonomous,queued:queued.length,results}));if(status==="BLOCKED")process.exitCode=1;
} finally {release();}
