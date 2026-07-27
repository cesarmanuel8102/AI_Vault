import {randomUUID} from "node:crypto";
import {join} from "node:path";
import type {ProxySpec,ReviewerOutput} from "./types.js";
import type {AutonomousEffects,CiResult,PolicyResult} from "./autonomous_flow.js";
import {GitHubBus} from "./github_bus.js";
import {GovernedBuilder} from "./governed_builder.js";
import {Ledger} from "./decision_ledger.js";
import {collect,REQUIRED_CHECKS} from "./evidence_collector.js";
import {decide} from "./policy_engine.js";
import {runReviewer} from "./codex_reviewer.js";
import {execute} from "./action_executor.js";
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
  constructor(readonly bus:GitHubBus,readonly ledger:Ledger,readonly sourceRepo:string,readonly root:string,readonly boundary:ExternalEffectBoundary,readonly coordinator:LocalCoordinator=failClosedCoordinator){this.bus.setMutationGuard(this.boundary.assert.bind(this.boundary));this.builder=new GovernedBuilder(sourceRepo,join(root,"worktrees"),bus,this.boundary.assert.bind(this.boundary));}
  bindLifecycle(spec:ProxySpec,state:import("./types.js").LifecycleRecord){this.boundary.bind(spec,state);}
  ensureIssue(spec:ProxySpec){const existing=this.bus.findOpenFront(spec.front_id!);if(existing.length>1)throw new Error("duplicate governed Issues");if(existing.length===1){const persisted=parseIssue(this.bus.issueBody(existing[0])).spec;if(JSON.stringify(persisted)!==JSON.stringify(spec))throw new Error("existing governed Issue spec mismatch");return existing[0];}return this.bus.createGovernedIssue(`feat(control-plane): ${spec.objective}`,spec.executor==="agent_loop"?agentLoopIssueBody(spec):issueBody(spec),spec.executor==="agent_loop"?"agent:queued":"operator:building");}
  ensureBuild(spec:ProxySpec,issue:number,session:string,repairCycle:number,previousHead?:string){if(spec.executor==="agent_loop"){const existing=this.bus.findPrByBranch(spec.work_branch!);if(!existing||repairCycle>0&&existing.head_sha===previousHead)return "PENDING" as const;this.bus.bindPrToIssue(issue,existing.number);return {pr:existing.number,head_sha:existing.head_sha,session:`agent-loop-${existing.head_sha}`};}return this.builder.build(spec,issue,session,repairCycle);}
  ci(pr:number,head:string):CiResult {const p=this.bus.json(["pr","view",String(pr),"--json","headRefOid,headRefName,statusCheckRollup"]);if(p.headRefOid!==head)throw new Error("CI head changed");const checks=p.statusCheckRollup??[];if(!checks.length||checks.some((c:any)=>c.status!=="COMPLETED"))return "PENDING";const byName=new Map(checks.map((c:any)=>[c.name,c]));if(REQUIRED_CHECKS.some(name=>(byName.get(name) as any)?.conclusion!=="SUCCESS"))return "FAIL";const skips=String(p.headRefName).startsWith("agent/pilot-")?new Set<string>():new Set(["deterministic","codex","publish"]);return checks.every((c:any)=>c.conclusion==="SUCCESS"||(c.conclusion==="SKIPPED"&&skips.has(c.name)))?"PASS":"FAIL";}
  review(pr:number,head:string,session:string):ReviewerOutput {this.boundary.assert("reviewer_execute",{pr,expected_head:head});return runReviewer(process.env.CODEX_PATH??"codex",`Independently review PR #${pr} at exact HEAD ${head}. Read-only. Return PASS only with zero findings; CHANGES_REQUESTED only with non-empty P2-only findings.`,this.sourceRepo,session,head);}
  policy(spec:ProxySpec,issue:number,pr:number,head:string,review:ReviewerOutput,builderSession:string,reviewerSession:string,repairCycles:number):PolicyResult {review=normalizeReviewerOutput(review,head);const prior=this.ledger.findByHead(head);if(prior){if(prior.issue!==issue||prior.pr!==pr||prior.base_sha!==spec.expected_base_sha||prior.roadmap_id!==spec.roadmap_id||prior.roadmap_item_id!==spec.roadmap_item_id)throw new Error("prior decision binding mismatch");if(prior.codex_review!==review.verdict||prior.review_consistent!==true||prior.review_findings_count!==review.findings.length)throw new Error("prior reviewer decision inconsistent");return {outcome:prior.policy_decision,decision_id:prior.decision_id};}const evidence=collect(this.bus,issue,pr,reviewerSession,review,spec);evidence.builder_session=builderSession;evidence.review_session=reviewerSession;evidence.repair_cycles=repairCycles;const decision=decide(spec,evidence);this.boundary.assert("decision_persist",{issue,pr,expected_head:head});this.ledger.record(decision);if(decision.policy_decision==="REPAIR"){this.boundary.assert("findings_publish",{issue,pr,expected_head:head});this.boundary.assert("repair_request",{issue,pr,expected_head:head});this.bus.comment(issue,`[OPERATOR-PROXY][REPAIR]\n\ndecision_id=${decision.decision_id}\nhead=${head}\nfindings=${safeJson(review.findings)}`);if(spec.executor==="agent_loop"){this.bus.label("issue",issue,"loop:repairing",["operator:repairing","loop:ci"]);this.bus.label("pr",pr,"loop:repairing",["operator:repairing","loop:ci"]);}}return {outcome:decision.policy_decision,decision_id:decision.decision_id};}
  ensureMerge(pr:number,head:string,base:string,decisionId:string){const decision=this.ledger.load(decisionId);if(decision.pr!==pr||decision.head_sha!==head||decision.base_sha!==base)throw new Error("merge decision binding mismatch");const current=this.bus.json(["pr","view",String(pr),"--json","state,mergeCommit"]);if(current.state==="MERGED"){const merge=this.bus.verifyMerged(pr,head,base);this.ledger.ensureConsumed(decision);return merge;}execute(this.bus,this.ledger,decision,false);const merged=this.bus.json(["pr","view",String(pr),"--json","state,mergeCommit"]);if(merged.state!=="MERGED")throw new Error("governed merge not completed");return String(merged.mergeCommit?.oid??"");}
  ensureInstall(merge:string){return this.coordinator.install(merge);}
  ensureRuntimePilot(spec:ProxySpec,merge:string){return this.coordinator.pilot(spec,merge);}
  ensureCloseout(spec:ProxySpec,merge:string){this.boundary.assert("closeout_create",{issue:undefined});if(!spec.closeout)return this.coordinator.closeout(spec,merge);const c=spec.closeout;const closeout:ProxySpec={...spec,expected_base_sha:merge,executor:c.executor,risk:c.risk,allowed_paths:c.allowed_paths,forbidden_paths:c.forbidden_paths,acceptance:c.acceptance,test_commands:c.test_commands,objective:c.objective,work_branch:c.work_branch,deployment_mode:"NO_DEPLOY",front_id:c.front_id,test_profile:c.test_profile,max_executor_cycles:c.max_executor_cycles,closeout:undefined,closeout_only:true};const flow=new AutonomousFlow(new LifecycleStore(join(this.root,"lifecycle")),this);let state=flow.step(closeout);for(let i=0;i<20;i++){if(["CI_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=flow.step(closeout);}if(state.state==="BLOCKED"||state.state==="ESCALATED")throw new Error(`closeout ${state.state}: ${state.last_error??"unknown"}`);return state.state==="TERMINAL_COMPLETED"?"PASS":"PENDING";}
  discoverNext(item:string){this.coordinator.discoverNext(item);}
}
