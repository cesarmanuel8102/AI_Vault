import {existsSync,mkdirSync} from "node:fs";
import {join} from "node:path";
import {randomUUID} from "node:crypto";
import {lock} from "./single_instance_lock.js";
import {Ledger} from "./decision_ledger.js";
import {GitHubBus} from "./github_bus.js";
import {collect} from "./evidence_collector.js";
import {decide,decisionKey,POLICY_SHA256} from "./policy_engine.js";
import {resolveReviewerRepository} from "./codex_reviewer.js";
import {ReviewerRouter} from "./reviewer_router.js";
import {execute,reconcileAuthorizationComment} from "./action_executor.js";
import {parseIssue} from "./spec_contract.js";
import {runAutonomousRoadmapTick} from "./autonomous_runtime.js";
import {ExternalEffectBoundary} from "./external_effect_guard.js";
import {newLifecycle} from "./autonomous_flow.js";
import {redactString,safeJson} from "./redaction.js";

const args=new Set(process.argv.slice(2));
const root=process.env.OPERATOR_PROXY_ROOT??"C:\\AI_VAULT_CODEX_BRIDGE";
const dry=args.has("--dry-run");

function review(cwd:string,pr:number,base:string,head:string,risk:import("./types.js").Risk,changedFiles:string[],builderSession:string){
  const requestedSession=`reviewer-${randomUUID()}`;
  try {const run=new ReviewerRouter(join(root,"reviewer-router")).review({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:cwd,pr,baseSha:base,headSha:head,risk,changedFiles,builderSession});return {result:run.output,session:run.session,requestedSession,reviewer:{backend:run.backend,model:run.model,verifier:run.verifier,attempts:run.attempts,receipt_key:run.receipt_key,arbiter:run.arbiter}};}
  catch{return {result:{verdict:"BLOCKED" as const,head_sha:head,summary:"reviewer unavailable or invalid",findings:[{severity:"P1" as const,title:"review unavailable",evidence:"fail closed",required_correction:"restore independent reviewer"}]},session:requestedSession};}
}

if(args.has("--doctor")){
  try{const reviewer_repository=resolveReviewerRepository();console.log(JSON.stringify({status:"PASS",node:process.version,root,reviewer_repository,pause:existsSync(join(root,"state","PAUSE"))}));process.exit(0);}
  catch(error){console.log(safeJson({status:"BLOCKED",node:process.version,root,error:redactString(error instanceof Error?error.message:String(error))}));process.exit(1);}
}

const reviewerRepo=resolveReviewerRepository();mkdirSync(join(root,"state"),{recursive:true});const release=lock(join(root,"state","operator-proxy.lock"));
try {
  if(existsSync(join(root,"state","PAUSE"))){console.log(JSON.stringify({status:"PAUSED"}));process.exit(0);}
  const bus=new GitHubBus(process.env.GH_PATH??"gh");const boundary=new ExternalEffectBoundary(root,bus,release.owns);const ledger=new Ledger(join(root,"decisions"));let autonomous:any={status:"SKIPPED_DRY_RUN"};
  if(!dry){try{autonomous={status:"PASS",state:runAutonomousRoadmapTick(bus,root,reviewerRepo,boundary)};}catch(error){autonomous={status:"BLOCKED",error:redactString(error instanceof Error?error.message:String(error))};}}
  const queued=bus.queued();const results=[];
  for(const issue of queued){
    try {
      if((issue.labels??[]).some((x:any)=>x.name==="operator:pause")){results.push({issue:issue.number,status:"PAUSED"});continue;}
      const {spec,pr}=parseIssue(issue.body);if(!pr){results.push({issue:issue.number,status:"AWAITING_AUTONOMOUS_BUILDER"});continue;}
      const initial=bus.json(["pr","view",String(pr),"--json","baseRefOid,headRefOid,files"]);const lifecycle={...newLifecycle({...spec,front_id:spec.front_id??`LEGACY-${issue.number}`,deployment_mode:spec.deployment_mode??"NO_DEPLOY"}),state:"REVIEWING" as const,issue:issue.number,pr,head_sha:initial.headRefOid};boundary.bind(spec,lifecycle);bus.setMutationGuard(boundary.assert.bind(boundary));const key=decisionKey(spec,issue.number,pr,initial.baseRefOid,initial.headRefOid);let existing=ledger.findByKey(key)??ledger.findByHead(initial.headRefOid);if(!existing){const cached=ledger.loadOrCreateReview(key,()=>{boundary.assert("reviewer_execute",{issue:issue.number,pr,expected_head:initial.headRefOid});const builderSession=`legacy-builder-${issue.number}-${initial.headRefOid}`;const rv=dry?{result:{verdict:"BLOCKED" as const,head_sha:initial.headRefOid,summary:"dry run",findings:[]},session:`dry-reviewer-${randomUUID()}`}:review(reviewerRepo,pr,initial.baseRefOid,initial.headRefOid,spec.risk,(initial.files??[]).map((x:any)=>String(x.path)),builderSession);return {issue:issue.number,pr,base_sha:initial.baseRefOid,head_sha:initial.headRefOid,session:rv.session,result:rv.result};}).review as any;if(cached.issue!==issue.number||cached.pr!==pr||cached.base_sha!==initial.baseRefOid||cached.head_sha!==initial.headRefOid)throw new Error("review receipt identity mismatch");const evidence=collect(bus,issue.number,pr,cached.session,cached.result,spec);const candidate=decide(spec,evidence);boundary.assert("decision_persist",{issue:issue.number,pr,expected_head:initial.headRefOid});existing=ledger.recordOrLoad(candidate).decision;}const decision=existing;
      if(("review_consistent" in decision&&decision.decision_key!==key)||decision.authorization_id!==spec.authorization_id||decision.repository!==spec.repository||decision.issue!==issue.number||decision.pr!==pr||decision.base_sha!==initial.baseRefOid||decision.head_sha!==initial.headRefOid||decision.roadmap_id!==spec.roadmap_id||decision.roadmap_item_id!==spec.roadmap_item_id||decision.policy_sha256!==POLICY_SHA256)throw new Error("DECISION_IDENTITY_CONFLICT");
      if(!dry){const merge=execute(bus,ledger,decision,false);if(merge){boundary.bindPostMerge(merge);reconcileAuthorizationComment(bus,decision);}const marker=`decision_key=${decision.decision_key}`;bus.commentOnce("pr",pr,marker,`[OPERATOR-PROXY][DECISION]\n\n${marker}\ndecision_id=${decision.decision_id}\npolicy_decision=${decision.policy_decision}\nhead=${decision.head_sha}`);const label=decision.policy_decision==="APPROVE"?"operator:completed":decision.policy_decision==="REPAIR"?"operator:repairing":decision.policy_decision==="ESCALATE_TO_OWNER"?"operator:escalated":"operator:blocked";bus.reconcileLabel("issue",issue.number,label,["operator:queued","operator:building","operator:reviewing"]);}
      results.push({issue:issue.number,pr,decision});
    } catch(error){results.push({issue:issue.number,status:"BLOCKED",error:redactString(error instanceof Error?error.message:String(error))});}
  }
  const status=autonomous.status==="BLOCKED"?"BLOCKED":"PASS";console.log(safeJson({status,dry_run:dry,autonomous,queued:queued.length,results}));if(status==="BLOCKED")process.exitCode=1;
} finally {release();}
