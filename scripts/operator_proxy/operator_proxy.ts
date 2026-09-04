import {existsSync,mkdirSync} from "node:fs";
import {join} from "node:path";
import {lock} from "./single_instance_lock.js";
import {GitHubBus} from "./github_bus.js";
import {resolveReviewerRepository} from "./codex_reviewer.js";
import {parseIssue} from "./spec_contract.js";
import {runAutonomousRoadmapTick} from "./autonomous_runtime.js";
import {ExternalEffectBoundary} from "./external_effect_guard.js";
import {redactString,safeJson} from "./redaction.js";

const args=new Set(process.argv.slice(2));
const root=process.env.OPERATOR_PROXY_ROOT??"C:\\AI_VAULT_CODEX_BRIDGE";
const dry=args.has("--dry-run");

if(args.has("--doctor")){
  try{const reviewer_repository=resolveReviewerRepository();console.log(JSON.stringify({status:"PASS",node:process.version,root,reviewer_repository,pause:existsSync(join(root,"state","PAUSE"))}));process.exit(0);}
  catch(error){console.log(safeJson({status:"BLOCKED",node:process.version,root,error:redactString(error instanceof Error?error.message:String(error))}));process.exit(1);}
}

const reviewerRepo=resolveReviewerRepository();mkdirSync(join(root,"state"),{recursive:true});const release=lock(join(root,"state","operator-proxy.lock"));
try {
  if(existsSync(join(root,"state","PAUSE"))){console.log(JSON.stringify({status:"PAUSED"}));process.exit(0);}
  const bus=new GitHubBus(process.env.GH_PATH??"gh");const boundary=new ExternalEffectBoundary(root,bus,release.owns);let autonomous:any={status:"SKIPPED_DRY_RUN"};
  if(!dry){try{autonomous={status:"PASS",state:await runAutonomousRoadmapTick(bus,root,reviewerRepo,boundary)};}catch(error){autonomous={status:"BLOCKED",error:redactString(error instanceof Error?error.message:String(error))};}}
  const queued=bus.queued();const results=[];
  for(const issue of queued){
    try {
      if((issue.labels??[]).some((x:any)=>x.name==="operator:pause")){results.push({issue:issue.number,status:"PAUSED"});continue;}
      const {spec,pr}=parseIssue(issue.body);if(!pr){results.push({issue:issue.number,status:"AWAITING_AUTONOMOUS_BUILDER"});continue;}
      // A linked legacy PR has no lifecycle/provenance binding. It cannot enter review or policy.
      results.push({issue:issue.number,pr,status:"PROVENANCE_GAP"});
    } catch(error){results.push({issue:issue.number,status:"BLOCKED",error:redactString(error instanceof Error?error.message:String(error))});}
  }
  const status=autonomous.status==="BLOCKED"?"BLOCKED":"PASS";console.log(safeJson({status,dry_run:dry,autonomous,queued:queued.length,results}));if(status==="BLOCKED")process.exitCode=1;
} finally {release();}
