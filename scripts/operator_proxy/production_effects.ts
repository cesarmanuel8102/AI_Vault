import {createHash,randomUUID} from "node:crypto";
import {join} from "node:path";
import type {ProxySpec,ReviewerOutput} from "./types.js";
import type {AutonomousEffects,CiResult,PolicyResult} from "./autonomous_flow.js";
import {GitHubBus} from "./github_bus.js";
import {GovernedBuilder} from "./governed_builder.js";
import {Ledger} from "./decision_ledger.js";
import {collect,evaluateChecks} from "./evidence_collector.js";
import {decide,decisionKey,POLICY_SHA256} from "./policy_engine.js";
import {runReviewer} from "./codex_reviewer.js";
import {execute,reconcileAuthorizationComment} from "./action_executor.js";
import {issueBody,parseIssue} from "./spec_contract.js";
import {AutonomousFlow} from "./autonomous_flow.js";
import {LifecycleStore,validBlockedCiEffectChain} from "./lifecycle_store.js";
import type {ExternalEffectBoundary} from "./external_effect_guard.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {safeJson} from "./redaction.js";
import {AgentLoopBuilderAdapter} from "./agent_loop_builder_adapter.js";
import {classify} from "./risk_classifier.js";

export interface LocalCoordinator {
  install(spec:ProxySpec,merge:string,artifactSha256:string):"PASS"|"LOCAL_PRIVILEGE_REQUIRED";
  pilot(spec:ProxySpec,merge:string):"PASS"|"PENDING";
  closeout(spec:ProxySpec,merge:string):"PASS"|"PENDING";
  discoverNext(item:string):void;
}
const failClosedCoordinator:LocalCoordinator={install:()=>"LOCAL_PRIVILEGE_REQUIRED",pilot:()=>"PENDING",closeout:()=>"PENDING",discoverNext:()=>{}};
const installArtifactPath=(spec:ProxySpec)=>spec.install_target==="agent_loop_worker"?"scripts/agent_loop/local_worker/agent_worker.py":undefined;
const pathAllowed=(path:string,spec:ProxySpec)=>spec.allowed_paths.some(p=>p.endsWith("/")?path.startsWith(p):path===p)&&!spec.forbidden_paths.some(p=>path===p||path.startsWith(p.endsWith("/")?p:`${p}/`));

export class ProductionEffects implements AutonomousEffects {
  readonly builder:GovernedBuilder;readonly agentLoopBuilder:AgentLoopBuilderAdapter;
  private activeSpec?:ProxySpec;private activeState?:import("./types.js").LifecycleRecord;
  constructor(readonly bus:GitHubBus,readonly ledger:Ledger,readonly sourceRepo:string,readonly root:string,readonly boundary:ExternalEffectBoundary,readonly coordinator:LocalCoordinator=failClosedCoordinator){this.bus.setMutationGuard(this.boundary.assert.bind(this.boundary));this.builder=new GovernedBuilder(sourceRepo,join(root,"worktrees"),bus,this.boundary.assert.bind(this.boundary));this.agentLoopBuilder=new AgentLoopBuilderAdapter(bus);}
  bindLifecycle(spec:ProxySpec,state:import("./types.js").LifecycleRecord){this.activeSpec=spec;this.activeState=state;this.boundary.bind(spec,state);}
  reconcilePreBuildBase(spec:ProxySpec,state:import("./types.js").LifecycleRecord,store:LifecycleStore){
    if(state.base_sha===spec.expected_base_sha)return state;
    const pristine=state.state==="BUILDING"&&Number.isInteger(state.issue)&&state.issue!>0&&state.repair_cycles===0&&!state.pr&&!state.head_sha&&!state.builder_session&&!state.reviewer_session&&!state.decision_id&&state.completed_effects.length===1&&state.completed_effects[0]===`issue:${state.issue}`;
    if(!pristine||!this.bus.isAncestor(state.base_sha,spec.expected_base_sha)||this.bus.remoteBranchHead(spec.work_branch!)||this.bus.prCandidatesByBranch(spec.work_branch!).length)throw new Error("pre-build base reconciliation denied");
    const snapshot=this.bus.issueSnapshot(state.issue!);if(snapshot.state!=="OPEN"||snapshot.labels.length!==1||snapshot.labels[0]!=="operator:building")throw new Error("pre-build Issue state invalid");
    const oldSpec={...spec,expected_base_sha:state.base_sha};const oldBody=issueBody(oldSpec),nextBody=issueBody(spec);const parsed=parseIssue(snapshot.body);
    if(parsed.pr||snapshot.body!==oldBody&&snapshot.body!==nextBody)throw new Error("pre-build Issue contract mismatch");
    this.boundary.bind(spec,state);if(snapshot.body===oldBody)this.bus.replaceIssueBodyExact(state.issue!,oldBody,nextBody);
    const updated=store.rebindPreBuildBase(state,spec.expected_base_sha);this.bindLifecycle(spec,updated);return updated;
  }
  reconcileBlockedCiBase(spec:ProxySpec,state:import("./types.js").LifecycleRecord,store:LifecycleStore){
    if(state.base_sha===spec.expected_base_sha)return state;
    const exact=state.state==="BLOCKED"&&state.last_error==="CI_FAILED"&&Number.isInteger(state.issue)&&Number.isInteger(state.pr)&&state.repair_cycles===0&&!!state.head_sha&&!!state.builder_session&&!state.reviewer_session&&!state.decision_id&&validBlockedCiEffectChain(state);
    if(!exact||!this.bus.isAncestor(state.base_sha,spec.expected_base_sha))throw new Error("blocked CI base reconciliation denied");
    const snapshot=this.bus.issueSnapshot(state.issue!);if(snapshot.state!=="OPEN"||snapshot.labels.length!==1||snapshot.labels[0]!=="operator:building")throw new Error("blocked CI Issue state invalid");
    const oldSpec={...spec,expected_base_sha:state.base_sha},oldBody=`${issueBody(oldSpec).trim()}\n\nOPERATOR_PROXY_PR: ${state.pr}\n`,nextBody=`${issueBody(spec).trim()}\n\nOPERATOR_PROXY_PR: ${state.pr}\n`,parsed=parseIssue(snapshot.body);
    if(parsed.pr!==state.pr||JSON.stringify(parsed.spec)!==JSON.stringify(snapshot.body===oldBody?oldSpec:spec)||snapshot.body!==oldBody&&snapshot.body!==nextBody)throw new Error("blocked CI Issue contract mismatch");
    this.boundary.beginBlockedCiRecovery(spec,state);
    try {
      const nextHead=this.builder.synchronizeBlockedCiBase(spec,state);this.boundary.bindBlockedCiRecoveryHead(nextHead);if(snapshot.body===oldBody)this.bus.replaceIssueBodyExact(state.issue!,oldBody,nextBody,nextHead);
      const updated=store.recoverBlockedCiBase(state,spec.expected_base_sha,nextHead);this.bindLifecycle(spec,updated);return updated;
    } finally {this.boundary.endBlockedCiRecovery();}
  }
  reconcileNegatedRiskEscalation(spec:ProxySpec,state:import("./types.js").LifecycleRecord,store:LifecycleStore){
    const decision=state.decision_id?this.ledger.load(state.decision_id):undefined;
    const exact=decision&&state.state==="ESCALATED"&&state.last_error==="OWNER_AUTHORITY_REQUIRED"&&decision.authorization_id===spec.authorization_id&&decision.repository===spec.repository&&decision.issue===state.issue&&decision.pr===state.pr&&decision.base_sha===state.base_sha&&decision.head_sha===state.head_sha&&decision.roadmap_id===spec.roadmap_id&&decision.roadmap_item_id===spec.roadmap_item_id&&decision.risk==="CRITICAL"&&decision.deterministic_gate==="PASS"&&decision.codex_review==="PASS"&&("review_findings_count" in decision&&decision.review_findings_count===0&&decision.review_consistent===true)&&decision.policy_decision==="ESCALATE_TO_OWNER"&&decision.allowed_action==="NONE"&&classify(spec)!=="CRITICAL"&&classify(spec)!=="HIGH"&&state.base_sha!==spec.expected_base_sha&&this.bus.isAncestor(state.base_sha,spec.expected_base_sha);
    if(!exact)throw new Error("negated risk escalation identity invalid");
    const snapshot=this.bus.issueSnapshot(state.issue!);const oldSpec={...spec,expected_base_sha:state.base_sha},oldBody=`${issueBody(oldSpec).trim()}\n\nOPERATOR_PROXY_PR: ${state.pr}\n`,nextBody=`${issueBody(spec).trim()}\n\nOPERATOR_PROXY_PR: ${state.pr}\n`,parsed=parseIssue(snapshot.body);
    if(snapshot.state!=="OPEN"||snapshot.labels.length!==1||snapshot.labels[0]!=="operator:building"||parsed.pr!==state.pr||JSON.stringify(parsed.spec)!==JSON.stringify(snapshot.body===oldBody?oldSpec:spec)||snapshot.body!==oldBody&&snapshot.body!==nextBody)throw new Error("negated risk escalation Issue identity invalid");
    this.boundary.beginNegatedRiskRecovery(spec,state);
    try {
      const branchState={...state,state:"BLOCKED" as const,last_error:"CI_FAILED",reviewer_session:undefined,decision_id:undefined};
      const nextHead=this.builder.synchronizeBlockedCiBase(spec,branchState);this.boundary.bindBlockedCiRecoveryHead(nextHead);if(snapshot.body===oldBody)this.bus.replaceIssueBodyExact(state.issue!,oldBody,nextBody,nextHead);
      const updated=store.recoverNegatedRiskEscalation(state,spec.expected_base_sha,nextHead);this.bindLifecycle(spec,updated);return updated;
    } finally {this.boundary.endBlockedCiRecovery();}
  }
  reconcileBlockedCiChecks(spec:ProxySpec,state:import("./types.js").LifecycleRecord,store:LifecycleStore){
    if(state.base_sha!==spec.expected_base_sha)throw new Error("blocked CI check binding mismatch");
    const exact=state.state==="BLOCKED"&&state.last_error==="CI_FAILED"&&Number.isInteger(state.issue)&&Number.isInteger(state.pr)&&state.repair_cycles===0&&!!state.head_sha&&!!state.builder_session&&!state.reviewer_session&&!state.decision_id&&validBlockedCiEffectChain(state);
    if(!exact)throw new Error("blocked CI check reconciliation denied");
    const snapshot=this.bus.issueSnapshot(state.issue!);const expectedBody=`${issueBody(spec).trim()}\n\nOPERATOR_PROXY_PR: ${state.pr}\n`;
    if(snapshot.state!=="OPEN"||snapshot.labels.length!==1||snapshot.labels[0]!=="operator:building"||snapshot.body!==expectedBody)throw new Error("blocked CI check Issue identity invalid");
    const pr=this.bus.prIdentity(state.pr!),files=(pr.files??[]).map((x:any)=>String(x.path));
    if(pr.author?.login!=="cesarmanuel8102"||pr.baseRefName!=="codex/own-capital-sustainable-return"||pr.baseRefOid!==state.base_sha||pr.headRefName!==spec.work_branch||pr.headRefOid!==state.head_sha||pr.headRepository?.nameWithOwner!=="cesarmanuel8102/AI_Vault"||pr.isCrossRepository!==false||pr.isDraft!==true||pr.state!=="OPEN"||pr.mergeable!=="MERGEABLE"||files.length===0||!files.every((path:string)=>pathAllowed(path,spec))||this.bus.remoteBranchHead(spec.work_branch!)!==state.head_sha)throw new Error("blocked CI check PR identity invalid");
    if(this.ci(state.pr!,state.head_sha!)!=="PASS")throw new Error("blocked CI checks not green");
    const updated=store.recoverBlockedCiChecks(state);this.bindLifecycle(spec,updated);return updated;
  }
  invalidateFailedMerge(spec:ProxySpec,state:import("./types.js").LifecycleRecord,store:LifecycleStore){
    const decision=state.decision_id?this.ledger.load(state.decision_id):undefined,pr=state.pr?this.bus.prIdentity(state.pr):undefined,files=(pr?.files??[]).map((x:any)=>String(x.path));
    const baseTip=pr?.baseRefName?this.bus.remoteBranchHead(pr.baseRefName):undefined,acceptedPrBase=pr?.baseRefOid===state.base_sha||pr?.baseRefOid===spec.expected_base_sha;
    const exact=decision&&decision.authorization_id===spec.authorization_id&&decision.repository===spec.repository&&decision.policy_sha256===POLICY_SHA256&&["LOW","MEDIUM"].includes(decision.risk)&&decision.policy_decision==="APPROVE"&&decision.allowed_action==="MERGE"&&decision.issue===state.issue&&decision.pr===state.pr&&decision.base_sha===state.base_sha&&decision.head_sha===state.head_sha&&decision.roadmap_id===spec.roadmap_id&&decision.roadmap_item_id===spec.roadmap_item_id&&!this.ledger.hasHead(state.head_sha!)&&state.base_sha!==spec.expected_base_sha&&this.bus.isAncestor(state.base_sha,spec.expected_base_sha)&&pr?.author?.login==="cesarmanuel8102"&&pr.baseRefName==="codex/own-capital-sustainable-return"&&baseTip===spec.expected_base_sha&&acceptedPrBase&&pr.headRefName===spec.work_branch&&pr.headRefOid===state.head_sha&&pr.headRepository?.nameWithOwner==="cesarmanuel8102/AI_Vault"&&pr.isCrossRepository===false&&pr.isDraft===true&&pr.state==="OPEN"&&files.length>0&&files.every((path:string)=>pathAllowed(path,spec))&&this.bus.remoteBranchHead(spec.work_branch!)===state.head_sha;
    if(!exact)throw new Error("failed merge recovery identity invalid");
    const runId=this.bus.failedGovernedMerge(state.decision_id!);const updated=store.invalidateFailedMerge(state,runId);this.bindLifecycle(spec,updated);return updated;
  }
  ensureIssue(spec:ProxySpec){const existing=this.bus.findOpenFront(spec.front_id!);if(spec.executor==="agent_loop")return this.agentLoopBuilder.ensureIssue(spec,existing);if(existing.length>1)throw new Error("duplicate governed Issues");if(existing.length===1){const persisted=parseIssue(this.bus.issueBody(existing[0])).spec;if(JSON.stringify(persisted)!==JSON.stringify(spec))throw new Error("existing governed Issue spec mismatch");return existing[0];}return this.bus.createGovernedIssue(`feat(control-plane): ${spec.objective}`,issueBody(spec),"operator:building");}
  ensureBuild(spec:ProxySpec,issue:number,session:string,repairCycle:number,previousHead?:string){return spec.executor==="agent_loop"?this.agentLoopBuilder.observe(spec,issue,repairCycle,previousHead):this.builder.build(spec,issue,session,repairCycle);}
  ci(pr:number,head:string):CiResult {const p=this.bus.json(["pr","view",String(pr),"--json","headRefOid,headRefName"]);if(p.headRefOid!==head)throw new Error("CI head changed");const result=evaluateChecks(this.bus,head,String(p.headRefName));return !result.terminal?"PENDING":result.green?"PASS":"FAIL";}
  review(pr:number,head:string,session:string):ReviewerOutput {const spec=this.activeSpec,state=this.activeState;if(!spec||!state?.issue||state.pr!==pr||state.head_sha!==head)throw new Error("review lifecycle binding missing");const key=decisionKey(spec,state.issue,pr,state.base_sha,head);const cached=this.ledger.loadOrCreateReview(key,()=>{this.boundary.assert("reviewer_execute",{issue:state.issue,pr,expected_head:head});return {issue:state.issue,pr,base_sha:state.base_sha,head_sha:head,result:runReviewer(process.env.CODEX_PATH??"codex",`Independently review PR #${pr} at exact HEAD ${head}. Read-only. Return PASS only with zero findings. Return CHANGES_REQUESTED for non-empty, technically repairable P1/P2 findings inside the declared scope. Return BLOCKED for P0 or non-repairable authority/security findings.`,this.sourceRepo,session,head)};}).review as any;if(cached.issue!==state.issue||cached.pr!==pr||cached.base_sha!==state.base_sha||cached.head_sha!==head)throw new Error("review receipt identity mismatch");return cached.result;}
  policy(spec:ProxySpec,issue:number,pr:number,head:string,review:ReviewerOutput,builderSession:string,reviewerSession:string,repairCycles:number):PolicyResult {review=normalizeReviewerOutput(review,head);const key=decisionKey(spec,issue,pr,spec.expected_base_sha,head);const prior=this.ledger.findByKey(key)??this.ledger.findByHead(head);if(prior){if(("review_consistent" in prior&&prior.decision_key!==key)||prior.issue!==issue||prior.pr!==pr||prior.base_sha!==spec.expected_base_sha||prior.head_sha!==head||prior.roadmap_id!==spec.roadmap_id||prior.roadmap_item_id!==spec.roadmap_item_id||prior.authorization_id!==spec.authorization_id||prior.repository!==spec.repository||prior.policy_sha256!==POLICY_SHA256)throw new Error("DECISION_IDENTITY_CONFLICT");return {outcome:prior.policy_decision,decision_id:prior.decision_id};}const evidence=collect(this.bus,issue,pr,reviewerSession,review,spec);evidence.builder_session=builderSession;evidence.review_session=reviewerSession;evidence.repair_cycles=repairCycles;const candidate=decide(spec,evidence);this.boundary.assert("decision_persist",{issue,pr,expected_head:head});const decision=this.ledger.recordOrLoad(candidate).decision;if(decision.policy_decision==="REPAIR"){this.boundary.assert("findings_publish",{issue,pr,expected_head:head});this.boundary.assert("repair_request",{issue,pr,expected_head:head});const marker=`decision_key=${decision.decision_key}`;this.bus.commentOnce("issue",issue,marker,`[OPERATOR-PROXY][REPAIR]\n\n${marker}\ndecision_id=${decision.decision_id}\nhead=${head}\nfindings=${safeJson(review.findings)}`);if(spec.executor==="agent_loop"){this.bus.reconcileLabel("issue",issue,"loop:repairing",["operator:repairing","loop:ci"]);this.bus.reconcileLabel("pr",pr,"loop:repairing",["operator:repairing","loop:ci"]);}}return {outcome:decision.policy_decision,decision_id:decision.decision_id};}
  ensureMerge(pr:number,head:string,base:string,decisionId:string){const decision=this.ledger.load(decisionId);if(decision.pr!==pr||decision.head_sha!==head||decision.base_sha!==base)throw new Error("merge decision binding mismatch");const merge=execute(this.bus,this.ledger,decision,false);if(!merge)throw new Error("governed merge not completed");this.boundary.bindPostMerge(merge);reconcileAuthorizationComment(this.bus,decision);return merge;}
  ensureInstall(spec:ProxySpec,merge:string){const path=installArtifactPath(spec);if(!path)throw new Error("install artifact target invalid");const artifactSha256=createHash("sha256").update(Buffer.from(this.bus.fileAt(path,merge),"utf8")).digest("hex");return this.coordinator.install(spec,merge,artifactSha256);}
  ensureRuntimePilot(spec:ProxySpec,merge:string){return this.coordinator.pilot(spec,merge);}
  ensureCloseout(spec:ProxySpec,merge:string){this.boundary.assert("closeout_create",{issue:undefined});if(!spec.closeout)return this.coordinator.closeout(spec,merge);const c=spec.closeout;const closeout:ProxySpec={...spec,executor:c.executor,risk:c.risk,allowed_paths:c.allowed_paths,forbidden_paths:c.forbidden_paths,acceptance:c.acceptance,test_commands:c.test_commands,objective:c.objective,work_branch:c.work_branch,deployment_mode:"NO_DEPLOY",install_target:undefined,front_id:c.front_id,test_profile:c.test_profile,max_executor_cycles:c.max_executor_cycles,closeout:undefined,closeout_only:true};const store=new LifecycleStore(join(this.root,"lifecycle"));const prior=store.load(closeout.front_id!);if(prior&&prior.base_sha!==closeout.expected_base_sha){if(!this.bus.isAncestor(prior.base_sha,closeout.expected_base_sha))throw new Error("closeout base ancestry invalid");store.rebindUnstartedBase(prior,closeout.expected_base_sha);}const flow=new AutonomousFlow(store,this);let state=flow.step(closeout);for(let i=0;i<20;i++){if(["CI_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=flow.step(closeout);}if(state.state==="BLOCKED"||state.state==="ESCALATED")throw new Error(`closeout ${state.state}: ${state.last_error??"unknown"}`);return state.state==="TERMINAL_COMPLETED"?"PASS":"PENDING";}
  discoverNext(item:string){this.coordinator.discoverNext(item);}
}
