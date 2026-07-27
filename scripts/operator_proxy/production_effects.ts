import {randomUUID} from "node:crypto";
import {join} from "node:path";
import type {ProxySpec,ReviewerOutput} from "./types.js";
import type {AutonomousEffects,CiResult,PolicyResult} from "./autonomous_flow.js";
import {GitHubBus} from "./github_bus.js";
import {GovernedBuilder} from "./governed_builder.js";
import {Ledger} from "./decision_ledger.js";
import {collect,REQUIRED_CHECKS} from "./evidence_collector.js";
import {decide,decisionKey,POLICY_SHA256} from "./policy_engine.js";
import {runReviewer} from "./codex_reviewer.js";
import {execute,reconcileAuthorizationComment} from "./action_executor.js";
import {agentLoopIssueBody,issueBody,parseIssue} from "./spec_contract.js";
import {AutonomousFlow} from "./autonomous_flow.js";
import {LifecycleStore} from "./lifecycle_store.js";
import type {ExternalEffectBoundary} from "./external_effect_guard.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {safeJson} from "./redaction.js";

export interface LocalCoordinator {
  install(merge:string):"PASS"|"LOCAL_PRIVILEGE_REQUIRED";
  pilot(spec:ProxySpec,merge:string):"PASS"|"PENDING";
  closeout(spec:ProxySpec,merge:string):"PASS"|"PENDING";
  discoverNext(item:string):void;
}
const failClosedCoordinator:LocalCoordinator={install:()=>"LOCAL_PRIVILEGE_REQUIRED",pilot:()=>"PENDING",closeout:()=>"PENDING",discoverNext:()=>{}};

export class ProductionEffects implements AutonomousEffects {
  readonly builder:GovernedBuilder;
  private activeSpec?:ProxySpec;private activeState?:import("./types.js").LifecycleRecord;
  constructor(readonly bus:GitHubBus,readonly ledger:Ledger,readonly sourceRepo:string,readonly root:string,readonly boundary:ExternalEffectBoundary,readonly coordinator:LocalCoordinator=failClosedCoordinator){this.bus.setMutationGuard(this.boundary.assert.bind(this.boundary));this.builder=new GovernedBuilder(sourceRepo,join(root,"worktrees"),bus,this.boundary.assert.bind(this.boundary));}
  bindLifecycle(spec:ProxySpec,state:import("./types.js").LifecycleRecord){this.activeSpec=spec;this.activeState=state;this.boundary.bind(spec,state);}
  ensureIssue(spec:ProxySpec){const existing=this.bus.findOpenFront(spec.front_id!);if(existing.length>1)throw new Error("duplicate governed Issues");if(existing.length===1){const persisted=parseIssue(this.bus.issueBody(existing[0])).spec;if(JSON.stringify(persisted)!==JSON.stringify(spec))throw new Error("existing governed Issue spec mismatch");return existing[0];}return this.bus.createGovernedIssue(`feat(control-plane): ${spec.objective}`,spec.executor==="agent_loop"?agentLoopIssueBody(spec):issueBody(spec),spec.executor==="agent_loop"?"agent:queued":"operator:building");}
  ensureBuild(spec:ProxySpec,issue:number,session:string,repairCycle:number,previousHead?:string){if(spec.executor==="agent_loop"){const existing=this.bus.findPrByBranch(spec.work_branch!);if(!existing||repairCycle>0&&existing.head_sha===previousHead)return "PENDING" as const;this.bus.bindPrToIssue(issue,existing.number);return {pr:existing.number,head_sha:existing.head_sha,session:`agent-loop-${existing.head_sha}`};}return this.builder.build(spec,issue,session,repairCycle);}
  ci(pr:number,head:string):CiResult {const p=this.bus.json(["pr","view",String(pr),"--json","headRefOid,headRefName,statusCheckRollup"]);if(p.headRefOid!==head)throw new Error("CI head changed");const checks=p.statusCheckRollup??[];if(!checks.length||checks.some((c:any)=>c.status!=="COMPLETED"))return "PENDING";const byName=new Map(checks.map((c:any)=>[c.name,c]));if(REQUIRED_CHECKS.some(name=>(byName.get(name) as any)?.conclusion!=="SUCCESS"))return "FAIL";const skips=String(p.headRefName).startsWith("agent/pilot-")?new Set<string>():new Set(["deterministic","codex","publish"]);return checks.every((c:any)=>c.conclusion==="SUCCESS"||(c.conclusion==="SKIPPED"&&skips.has(c.name)))?"PASS":"FAIL";}
  review(pr:number,head:string,session:string):ReviewerOutput {const spec=this.activeSpec,state=this.activeState;if(!spec||!state?.issue||state.pr!==pr||state.head_sha!==head)throw new Error("review lifecycle binding missing");const key=decisionKey(spec,state.issue,pr,state.base_sha,head);const cached=this.ledger.loadOrCreateReview(key,()=>{this.boundary.assert("reviewer_execute",{issue:state.issue,pr,expected_head:head});return {issue:state.issue,pr,base_sha:state.base_sha,head_sha:head,result:runReviewer(process.env.CODEX_PATH??"codex",`Independently review PR #${pr} at exact HEAD ${head}. Read-only. Return PASS only with zero findings; CHANGES_REQUESTED only with non-empty P2-only findings.`,this.sourceRepo,session,head)};}).review as any;if(cached.issue!==state.issue||cached.pr!==pr||cached.base_sha!==state.base_sha||cached.head_sha!==head)throw new Error("review receipt identity mismatch");return cached.result;}
  policy(spec:ProxySpec,issue:number,pr:number,head:string,review:ReviewerOutput,builderSession:string,reviewerSession:string,repairCycles:number):PolicyResult {review=normalizeReviewerOutput(review,head);const key=decisionKey(spec,issue,pr,spec.expected_base_sha,head);const prior=this.ledger.findByKey(key)??this.ledger.findByHead(head);if(prior){if((prior.schema_version===2&&prior.decision_key!==key)||prior.issue!==issue||prior.pr!==pr||prior.base_sha!==spec.expected_base_sha||prior.head_sha!==head||prior.roadmap_id!==spec.roadmap_id||prior.roadmap_item_id!==spec.roadmap_item_id||prior.authorization_id!==spec.authorization_id||prior.repository!==spec.repository||prior.policy_sha256!==POLICY_SHA256)throw new Error("DECISION_IDENTITY_CONFLICT");return {outcome:prior.policy_decision,decision_id:prior.decision_id};}const evidence=collect(this.bus,issue,pr,reviewerSession,review,spec);evidence.builder_session=builderSession;evidence.review_session=reviewerSession;evidence.repair_cycles=repairCycles;const candidate=decide(spec,evidence);this.boundary.assert("decision_persist",{issue,pr,expected_head:head});const decision=this.ledger.recordOrLoad(candidate).decision;if(decision.policy_decision==="REPAIR"){this.boundary.assert("findings_publish",{issue,pr,expected_head:head});this.boundary.assert("repair_request",{issue,pr,expected_head:head});const marker=`decision_key=${decision.decision_key}`;this.bus.commentOnce("issue",issue,marker,`[OPERATOR-PROXY][REPAIR]\n\n${marker}\ndecision_id=${decision.decision_id}\nhead=${head}\nfindings=${safeJson(review.findings)}`);if(spec.executor==="agent_loop"){this.bus.reconcileLabel("issue",issue,"loop:repairing",["operator:repairing","loop:ci"]);this.bus.reconcileLabel("pr",pr,"loop:repairing",["operator:repairing","loop:ci"]);}}return {outcome:decision.policy_decision,decision_id:decision.decision_id};}
  ensureMerge(pr:number,head:string,base:string,decisionId:string){const decision=this.ledger.load(decisionId);if(decision.pr!==pr||decision.head_sha!==head||decision.base_sha!==base)throw new Error("merge decision binding mismatch");const merge=execute(this.bus,this.ledger,decision,false);if(!merge)throw new Error("governed merge not completed");this.boundary.bindPostMerge(merge);reconcileAuthorizationComment(this.bus,decision);return merge;}
  ensureInstall(merge:string){return this.coordinator.install(merge);}
  ensureRuntimePilot(spec:ProxySpec,merge:string){return this.coordinator.pilot(spec,merge);}
  ensureCloseout(spec:ProxySpec,merge:string){this.boundary.assert("closeout_create",{issue:undefined});if(!spec.closeout)return this.coordinator.closeout(spec,merge);const c=spec.closeout;const closeout:ProxySpec={...spec,expected_base_sha:merge,executor:c.executor,risk:c.risk,allowed_paths:c.allowed_paths,forbidden_paths:c.forbidden_paths,acceptance:c.acceptance,test_commands:c.test_commands,objective:c.objective,work_branch:c.work_branch,deployment_mode:"NO_DEPLOY",front_id:c.front_id,test_profile:c.test_profile,max_executor_cycles:c.max_executor_cycles,closeout:undefined,closeout_only:true};const flow=new AutonomousFlow(new LifecycleStore(join(this.root,"lifecycle")),this);let state=flow.step(closeout);for(let i=0;i<20;i++){if(["CI_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=flow.step(closeout);}if(state.state==="BLOCKED"||state.state==="ESCALATED")throw new Error(`closeout ${state.state}: ${state.last_error??"unknown"}`);return state.state==="TERMINAL_COMPLETED"?"PASS":"PENDING";}
  discoverNext(item:string){this.coordinator.discoverNext(item);}
}
