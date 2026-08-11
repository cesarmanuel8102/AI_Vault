import {createHash,randomUUID} from "node:crypto";
import {join} from "node:path";
import type {LifecycleRecord,ProxySpec,ReviewerOutput} from "./types.js";
import type {AutonomousEffects,CiResult,PolicyResult} from "./autonomous_flow.js";
import {GitHubBus} from "./github_bus.js";
import {GovernedBuilder} from "./governed_builder.js";
import {Ledger} from "./decision_ledger.js";
import {collect,evaluateChecks} from "./evidence_collector.js";
import {decide,decisionKey,decisionMatchesCandidate,POLICY_SHA256} from "./policy_engine.js";
import {ReviewerRouter,validateReviewerEnvelope} from "./reviewer_router.js";
import {inspectAgentLoopCommitModel,verifiedBuilderModel} from "./reviewer_config.js";
import {execute,reconcileAuthorizationComment} from "./action_executor.js";
import {agentLoopIssueBody,issueBody,parseAgentLoopIssue,parseIssue} from "./spec_contract.js";
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
const boundIssueBody=(spec:ProxySpec,pr:number)=>`${(spec.executor==="agent_loop"?agentLoopIssueBody(spec):issueBody(spec)).trim()}\n\nOPERATOR_PROXY_PR: ${pr}\n`;
const blockedCiIssuePhase=(spec:ProxySpec)=>spec.executor==="agent_loop"?"loop:ci":"operator:building";

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
    const snapshot=this.bus.issueSnapshot(state.issue!);if(snapshot.state!=="OPEN"||snapshot.labels.length!==1||snapshot.labels[0]!==blockedCiIssuePhase(spec))throw new Error("blocked CI Issue state invalid");
    const oldSpec={...spec,expected_base_sha:state.base_sha},oldBody=boundIssueBody(oldSpec,state.pr!),nextBody=boundIssueBody(spec,state.pr!),parsed=parseIssue(snapshot.body);
    if(parsed.pr!==state.pr||JSON.stringify(parsed.spec)!==JSON.stringify(snapshot.body===oldBody?oldSpec:spec)||snapshot.body!==oldBody&&snapshot.body!==nextBody)throw new Error("blocked CI Issue contract mismatch");
    if(spec.executor==="agent_loop")parseAgentLoopIssue(snapshot.body,snapshot.body===oldBody?oldSpec:spec);
    this.boundary.beginBlockedCiRecovery(spec,state);
    try {
      const nextHead=this.builder.synchronizeBlockedCiBase(spec,state);this.boundary.bindBlockedCiRecoveryHead(nextHead);if(snapshot.body===oldBody)this.bus.replaceIssueBodyExact(state.issue!,oldBody,nextBody,nextHead);
      const updated=store.recoverBlockedCiBase(state,spec.expected_base_sha,nextHead);this.bindLifecycle(spec,updated);return updated;
    } finally {this.boundary.endBlockedCiRecovery();}
  }
  reconcileNegatedRiskEscalation(spec:ProxySpec,state:import("./types.js").LifecycleRecord,store:LifecycleStore){
    const decision=state.decision_id?this.ledger.load(state.decision_id):undefined;
    const reviewRecoverable=decision&&"review_findings_count" in decision&&decision.review_consistent===true&&(decision.codex_review==="PASS"&&decision.review_findings_count===0||decision.codex_review==="CHANGES_REQUESTED"&&decision.review_findings_count>0);
    const exact=decision&&state.state==="ESCALATED"&&state.last_error==="OWNER_AUTHORITY_REQUIRED"&&decision.authorization_id===spec.authorization_id&&decision.repository===spec.repository&&decision.issue===state.issue&&decision.pr===state.pr&&decision.base_sha===state.base_sha&&decision.head_sha===state.head_sha&&decision.roadmap_id===spec.roadmap_id&&decision.roadmap_item_id===spec.roadmap_item_id&&decision.risk==="CRITICAL"&&decision.deterministic_gate==="PASS"&&reviewRecoverable&&decision.policy_decision==="ESCALATE_TO_OWNER"&&decision.allowed_action==="NONE"&&classify(spec)!=="CRITICAL"&&classify(spec)!=="HIGH"&&state.base_sha!==spec.expected_base_sha&&this.bus.isAncestor(state.base_sha,spec.expected_base_sha);
    if(!exact)throw new Error("negated risk escalation identity invalid");
    const snapshot=this.bus.issueSnapshot(state.issue!);const oldSpec={...spec,expected_base_sha:state.base_sha},oldBody=boundIssueBody(oldSpec,state.pr!),nextBody=boundIssueBody(spec,state.pr!),parsed=parseIssue(snapshot.body);
    if(snapshot.state!=="OPEN"||snapshot.labels.length!==1||snapshot.labels[0]!==blockedCiIssuePhase(spec)||parsed.pr!==state.pr||JSON.stringify(parsed.spec)!==JSON.stringify(snapshot.body===oldBody?oldSpec:spec)||snapshot.body!==oldBody&&snapshot.body!==nextBody)throw new Error("negated risk escalation Issue identity invalid");
    if(spec.executor==="agent_loop")parseAgentLoopIssue(snapshot.body,snapshot.body===oldBody?oldSpec:spec);
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
    const snapshot=this.bus.issueSnapshot(state.issue!);const expectedBody=boundIssueBody(spec,state.pr!);
    if(snapshot.state!=="OPEN"||snapshot.labels.length!==1||snapshot.labels[0]!==blockedCiIssuePhase(spec)||snapshot.body!==expectedBody)throw new Error("blocked CI check Issue identity invalid");
    if(spec.executor==="agent_loop")parseAgentLoopIssue(snapshot.body,spec);
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
  async ensureBuild(spec:ProxySpec,issue:number,session:string,repairCycle:number,previousHead?:string){return spec.executor==="agent_loop"?await this.agentLoopBuilder.observe(spec,issue,repairCycle,previousHead):await this.builder.build(spec,issue,session,repairCycle);}
  ci(pr:number,head:string):CiResult {const p=this.bus.json(["pr","view",String(pr),"--json","headRefOid,headRefName"]);if(p.headRefOid!==head)throw new Error("CI head changed");const result=evaluateChecks(this.bus,head,String(p.headRefName));return !result.terminal?"PENDING":result.green?"PASS":"FAIL";}
  private agentLoopReceiptMessage(spec:ProxySpec,state:import("./types.js").LifecycleRecord,head:string){const current=this.bus.commitMessage(head),syncSubject=`chore(control-plane): synchronize ${spec.front_id} base`;if(current.split("\n",1)[0]!==syncSubject)return current;const builds=state.completed_effects.filter(value=>/^build:[0-9a-f]{40}$/.test(value)),candidate=builds.length===1?builds[0].slice(6):undefined;if(!candidate||state.repair_cycles!==0||state.builder_session!==`agent-loop-builder-${candidate}`||!state.completed_effects.includes(`base-sync:${head}`)||!this.bus.isAncestor(candidate,head))throw new Error("Agent Loop synchronized receipt evidence invalid");return this.bus.commitMessage(candidate);}
  private inspectRouterBuilderReceipt(head:string,baseSha:string,frontId:string):{model:string;headCommit:string}{
    if(!/^[0-9a-f]{40}$/.test(head)||!/^[0-9a-f]{40}$/.test(baseSha)||!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(frontId)||!this.bus.isAncestor(baseSha,head))throw new Error("builder model receipt history invalid");
    const subject=`feat(control-plane): complete ${frontId}`;
    const prefix="BUILDER_MODEL=";
    const safeModel=/^[a-z0-9][a-z0-9._:/-]{2,127}$/;
    let current=head,depth=0;
    while(current!==baseSha&&depth++<64){
      const message=this.bus.commitMessage(current);
      if(message.split("\n",1)[0]===subject){
        const lines=message.replace(/\r\n/g,"\n").split("\n");
        const trailers=lines.slice(1).filter(line=>line.startsWith(prefix));
        if(trailers.length!==1)throw new Error(trailers.length>1?"builder model receipt ambiguous":"builder model receipt missing");
        const model=trailers[0].slice(prefix.length);
        if(!safeModel.test(model))throw new Error("builder model receipt malformed");
        return {model,headCommit:current};
      }
      const commit=JSON.parse(this.bus.call(["api",`repos/${this.bus.repo}/git/commits/${current}`]));
      const parents=Array.isArray(commit?.parents)?commit.parents.map((parent:any)=>String(parent?.sha??"")):[];
      if(parents.length<1||parents.length>2||parents.some((parent:string)=>!/^[0-9a-f]{40}$/.test(parent)))throw new Error("builder model receipt history invalid");
      current=parents[0];
    }
    throw new Error("builder model receipt missing");
  }
  review(pr:number,head:string,session:string) {const spec=this.activeSpec,state=this.activeState;if(!spec||!state?.issue||state.pr!==pr||state.head_sha!==head||!state.builder_session||!spec.front_id)throw new Error("review lifecycle binding missing");const key=decisionKey(spec,state.issue,pr,state.base_sha,head),identity=this.bus.prIdentity(pr),files=(identity.files??[]).map((x:any)=>String(x.path)),reportPath="docs/agent_loop/pilot/EXECUTOR_REPORT.json",report=spec.executor==="agent_loop"&&files.includes(reportPath)?JSON.parse(this.bus.fileAt(reportPath,head)):undefined,receipt=spec.executor==="agent_loop"?inspectAgentLoopCommitModel(this.agentLoopReceiptMessage(spec,state,head),spec.front_id,report?.model):undefined,routerReceipt=spec.executor==="codex_control_plane"?this.inspectRouterBuilderReceipt(head,state.base_sha,spec.front_id):undefined,builderModel=receipt?.model??routerReceipt?.model??verifiedBuilderModel(spec.executor);if(receipt?.status==="MISSING")return {session:`reviewer:deterministic-receipt-repair:${head}`,output:{verdict:"CHANGES_REQUESTED",head_sha:head,summary:"Agent Loop commit evidence requires bounded regeneration",findings:[{severity:"P1",title:"Executor model receipt missing",evidence:"The exact Agent Loop candidate commit subject is valid, but the required AGENT_LOOP_EXECUTOR_MODEL trailer is absent.",required_correction:"Regenerate the candidate with the installed governed Agent Loop worker so the commit records exactly one configured executor model receipt."}]}};const input={repository:spec.repository,repositoryRoot:this.sourceRepo,pr,baseSha:state.base_sha,headSha:head,risk:spec.risk,changedFiles:files,builderSession:state.builder_session,builderModel},expected={issue:state.issue,pr,base_sha:state.base_sha,head_sha:head,front_id:spec.front_id,builder_session:state.builder_session,builder_model:builderModel};const cached=this.ledger.loadOrCreateReview(key,()=>{this.boundary.assert("reviewer_execute",{issue:state.issue,pr,expected_head:head});const run=new ReviewerRouter(join(this.root,"reviewer-router")).review(input);return {schema_version:1,...expected,requested_session:session,session:run.session,router_run:run,result:run.output};},value=>{validateReviewerEnvelope(value,expected,input);}).review as any;return {output:cached.result,session:cached.session};}
  policy(spec:ProxySpec,issue:number,pr:number,head:string,review:ReviewerOutput,builderSession:string,reviewerSession:string,repairCycles:number):PolicyResult {review=normalizeReviewerOutput(review,head);const key=decisionKey(spec,issue,pr,spec.expected_base_sha,head),evidence=collect(this.bus,issue,pr,reviewerSession,review,spec);evidence.builder_session=builderSession;evidence.review_session=reviewerSession;evidence.repair_cycles=repairCycles;const candidate=decide(spec,evidence),prior=this.ledger.findByKey(key)??this.ledger.findByHead(head);if(prior){if(!decisionMatchesCandidate(prior,candidate))throw new Error("DECISION_IDENTITY_CONFLICT");return {outcome:prior.policy_decision,decision_id:prior.decision_id};}this.boundary.assert("decision_persist",{issue,pr,expected_head:head});const decision=this.ledger.recordOrLoad(candidate).decision;if(decision.policy_decision==="REPAIR"){this.boundary.assert("findings_publish",{issue,pr,expected_head:head});this.boundary.assert("repair_request",{issue,pr,expected_head:head});const marker=`decision_key=${decision.decision_key}`;this.bus.commentOnce("issue",issue,marker,`[OPERATOR-PROXY][REPAIR]\n\n${marker}\ndecision_id=${decision.decision_id}\nhead=${head}\nfindings=${safeJson(review.findings)}`);if(spec.executor==="agent_loop"){this.bus.reconcileLabel("issue",issue,"loop:repairing",["operator:repairing","loop:ci"]);this.bus.reconcileLabel("pr",pr,"loop:repairing",["operator:repairing","loop:ci"]);}}return {outcome:decision.policy_decision,decision_id:decision.decision_id};}
  ensureMerge(pr:number,head:string,base:string,decisionId:string){const spec=this.activeSpec,state=this.activeState;if(!spec||!state?.issue||state.pr!==pr||state.head_sha!==head||state.base_sha!==base||state.decision_id!==decisionId||!state.builder_session||!state.reviewer_session)throw new Error("merge lifecycle binding missing");const decision=this.ledger.load(decisionId);if(decision.pr!==pr||decision.head_sha!==head||decision.base_sha!==base)throw new Error("merge decision binding mismatch");const alreadyMerged=this.ledger.hasHead(head)||this.bus.prIdentity(pr).state==="MERGED";if(!alreadyMerged){const reviewed=this.review(pr,head,state.reviewer_session),recomputed=this.policy(spec,state.issue,pr,head,reviewed.output,state.builder_session,reviewed.session,state.repair_cycles);if(recomputed.outcome!=="APPROVE"||recomputed.decision_id!==decisionId)throw new Error("merge decision revalidation failed");}const merge=execute(this.bus,this.ledger,decision,false);if(!merge)throw new Error("governed merge not completed");this.boundary.bindPostMerge(merge);reconcileAuthorizationComment(this.bus,decision);return merge;}
  ensureInstall(spec:ProxySpec,merge:string){const path=installArtifactPath(spec);if(!path)throw new Error("install artifact target invalid");const artifactSha256=createHash("sha256").update(Buffer.from(this.bus.fileAt(path,merge),"utf8")).digest("hex");return this.coordinator.install(spec,merge,artifactSha256);}
  ensureRuntimePilot(spec:ProxySpec,merge:string){return this.coordinator.pilot(spec,merge);}
  reconcileCloseoutState(spec:ProxySpec,state:LifecycleRecord,store:LifecycleStore){
    if(state.state==="BLOCKED"&&state.last_error==="CI_FAILED")return state.base_sha===spec.expected_base_sha?this.reconcileBlockedCiChecks(spec,state,store):this.reconcileBlockedCiBase(spec,state,store);
    if(state.base_sha===spec.expected_base_sha)return state;
    if(!this.bus.isAncestor(state.base_sha,spec.expected_base_sha))throw new Error("closeout base ancestry invalid");
    if(["CI_PENDING","REVIEWING"].includes(state.state))return this.reconcileBlockedCiBase(spec,store.invalidatePostBuildBase(state),store);
    if(state.state==="MERGING")return this.reconcileBlockedCiBase(spec,this.invalidateFailedMerge(spec,state,store),store);
    if(["DISCOVERED","ADMITTED"].includes(state.state))return store.rebindUnstartedBase(state,spec.expected_base_sha);
    if(state.state==="BUILDING")return this.reconcilePreBuildBase(spec,state,store);
    if(["MERGED","CLOSEOUT_PENDING","CLOSEOUT_MERGED","TERMINAL_COMPLETED"].includes(state.state))return store.rebindPostMergeBase(state,spec.expected_base_sha);
    throw new Error("closeout base reconciliation denied");
  }
  private closeoutParentEvidence(spec:ProxySpec,merge:string){
    const state=this.activeState;
    if(!state||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id||state.state!=="CLOSEOUT_PENDING"||state.head_sha!==merge||!state.completed_effects.includes(`merge:${merge}`)||!state.issue||!state.pr||!state.builder_session||!state.reviewer_session||!state.decision_id)throw new Error("closeout parent lifecycle evidence missing");
    const decision=this.ledger.load(state.decision_id);
    const baseBound=decision.base_sha===state.base_sha||this.bus.isAncestor(decision.base_sha,state.base_sha);
    const common=decision.authorization_id===spec.authorization_id&&decision.repository===spec.repository&&decision.issue===state.issue&&decision.pr===state.pr&&state.base_sha===spec.expected_base_sha&&baseBound&&decision.roadmap_id===spec.roadmap_id&&decision.roadmap_item_id===spec.roadmap_item_id;
    const policyApproved=decision.policy_decision==="APPROVE"&&decision.allowed_action==="MERGE"&&this.ledger.hasHead(decision.head_sha);
    const ownerAuthorized="review_findings_count" in decision&&"review_consistent" in decision&&decision.risk==="CRITICAL"&&decision.deterministic_gate==="PASS"&&decision.codex_review==="PASS"&&decision.review_findings_count===0&&decision.review_consistent===true&&decision.policy_decision==="ESCALATE_TO_OWNER"&&decision.allowed_action==="NONE"&&this.bus.verifyOwnerAuthorizedMerge(state.issue,state.pr,decision.head_sha,decision.base_sha,merge)===merge;
    if(!common||!policyApproved&&!ownerAuthorized)throw new Error("closeout parent decision evidence mismatch");
    return {schema_version:1,parent_front_id:state.front_id,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,issue:state.issue,pr:state.pr,decision_id:decision.decision_id,authorization_mode:ownerAuthorized?"OWNER_CONSTITUTIONAL":"POLICY_APPROVED",base_sha:decision.base_sha,closeout_base_sha:state.base_sha,head_sha:decision.head_sha,merge_commit:merge,builder_session:state.builder_session,reviewer_session:state.reviewer_session};
  }
  async ensureCloseout(spec:ProxySpec,merge:string){this.boundary.assert("closeout_create",{issue:undefined});if(!spec.closeout)return this.coordinator.closeout(spec,merge);const c=spec.closeout,parentEvidence=safeJson(this.closeoutParentEvidence(spec,merge)),evidenceInstruction=`Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: ${parentEvidence}`;const closeout:ProxySpec={...spec,executor:c.executor,risk:c.risk,allowed_paths:c.allowed_paths,forbidden_paths:c.forbidden_paths,acceptance:[...c.acceptance,evidenceInstruction],test_commands:c.test_commands,objective:`${c.objective.trim()}\n\nPARENT_LIFECYCLE_EVIDENCE_JSON=${parentEvidence}`,work_branch:c.work_branch,deployment_mode:"NO_DEPLOY",install_target:undefined,front_id:c.front_id,test_profile:c.test_profile,max_executor_cycles:c.max_executor_cycles,closeout:undefined,closeout_only:true};const store=new LifecycleStore(join(this.root,"lifecycle"));const prior=store.load(closeout.front_id!);if(prior)this.reconcileCloseoutState(closeout,prior,store);const flow=new AutonomousFlow(store,this);let state=await flow.step(closeout);for(let i=0;i<20;i++){if(["CI_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=await flow.step(closeout);}if(state.state==="BLOCKED"||state.state==="ESCALATED")throw new Error(`closeout ${state.state}: ${state.last_error??"unknown"}`);return state.state==="TERMINAL_COMPLETED"?"PASS":"PENDING";}
  discoverNext(item:string){this.coordinator.discoverNext(item);}
}
