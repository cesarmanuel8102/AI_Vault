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
import {LEGACY_NEUTRALIZATION_TRAILER,LEGACY_REBUILD_TRAILER,PRIOR_UNATTESTED_HEAD_TRAILER,RESET_BASE_TRAILER,NEUTRALIZATION_HEAD_TRAILER,FRESH_BUILDER_HEAD_TRAILER} from "./builder_attempt_provenance.js";
import {execute,reconcileAuthorizationComment} from "./action_executor.js";
import {agentLoopIssueBody,issueBody,parseAgentLoopIssue,parseIssue} from "./spec_contract.js";
import {AutonomousFlow} from "./autonomous_flow.js";
import {LifecycleStore,validBlockedCiEffectChain,validBridgeAdoptionState} from "./lifecycle_store.js";
import type {ExternalEffectBoundary} from "./external_effect_guard.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {safeJson} from "./redaction.js";
import {AgentLoopBuilderAdapter} from "./agent_loop_builder_adapter.js";
import {classify} from "./risk_classifier.js";
import {INTEGRATION_BRANCH,MANIFEST_PATH,ROADMAP_PATH} from "./roadmap_sequencer.js";
import {commitAccessFromBus,verifyBuilderProvenance,decisionBoundToLineage as decisionBoundToLineageRole,normalizeObservedFacts,type CanonicalLifecycleSnapshot} from "./lineage.js";
import {deriveReconciliationPlan,validateInvariantSet,type PlannerPorts,type ReconciliationPlan} from "./reconciliation.js";

const FRESH_SUBJECT=(front:string)=>`feat(control-plane): complete ${front}`;
const NEUTRALIZATION_SUBJECT=(front:string)=>`chore(control-plane): neutralize ${front} legacy baseline`;

export function reviewEvidenceKey(policyKey:string,builderSession:string,builderModel:string){
  if(!/^[0-9a-f]{64}$/.test(policyKey)||!builderSession||!builderModel)throw new Error("review evidence identity invalid");
  return createHash("sha256").update(JSON.stringify({policy_key:policyKey,builder_session:builderSession,builder_model:builderModel})).digest("hex");
}

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
const roadmapBindingFields=new Set(["expected_base_sha","roadmap_sha256","manifest_sha256"]);
const sha256=(value:string)=>createHash("sha256").update(Buffer.from(value,"utf8")).digest("hex");
const serializedSpec=(spec:ProxySpec)=>Object.fromEntries(Object.entries(spec).filter(([,value])=>value!==undefined));
const exactSpecExceptHistoricalBinding=(current:ProxySpec,historical:ProxySpec)=>{
  current=serializedSpec(current) as ProxySpec;historical=serializedSpec(historical) as ProxySpec;
  const currentKeys=Object.keys(current).sort(),historicalKeys=Object.keys(historical).sort();
  if(JSON.stringify(currentKeys)!==JSON.stringify(historicalKeys))return false;
  return currentKeys.every(key=>roadmapBindingFields.has(key)||JSON.stringify((current as any)[key])===JSON.stringify((historical as any)[key]));
};
const canonicalDependencies=(value:unknown)=>Array.isArray(value)&&value.every(item=>typeof item==="string"&&/^R\d+(?:\.\d+)?$/.test(item))&&new Set(value).size===value.length?[...value].sort():undefined;

function safe<T>(operation:()=>T):T|undefined{try{return operation();}catch{return undefined;}}

export class ProductionEffects implements AutonomousEffects {
  readonly builder:GovernedBuilder;readonly agentLoopBuilder:AgentLoopBuilderAdapter;
  private store:LifecycleStore;
  private activeSpec?:ProxySpec;private activeState?:import("./types.js").LifecycleRecord;
  constructor(readonly bus:GitHubBus,readonly ledger:Ledger,readonly sourceRepo:string,readonly root:string,readonly boundary:ExternalEffectBoundary,readonly coordinator:LocalCoordinator=failClosedCoordinator){this.bus.setMutationGuard(this.boundary.assert.bind(this.boundary));this.builder=new GovernedBuilder(sourceRepo,join(root,"worktrees"),bus,this.boundary.assert.bind(this.boundary));this.agentLoopBuilder=new AgentLoopBuilderAdapter(bus);this.store=new LifecycleStore(join(root,"lifecycle"));}
  bindLifecycle(spec:ProxySpec,state:import("./types.js").LifecycleRecord){this.activeSpec=spec;this.activeState=state;this.boundary.bind(spec,state);}
  private bindObservedBlockedCiHead(spec:ProxySpec,state:LifecycleRecord){
    if(spec.executor!=="codex_control_plane"||!state.pr||!state.head_sha)return;
    const observed=String(this.bus.prIdentity(state.pr).headRefOid??"");
    if(observed!==state.head_sha)this.boundary.bindBlockedCiRecoveryObservedHead(observed);
  }
  private validHistoricalRoadmapBinding(current:ProxySpec,historical:ProxySpec,base:string){
    if(!exactSpecExceptHistoricalBinding(current,historical)||historical.expected_base_sha!==base||!/^[0-9a-f]{64}$/.test(historical.roadmap_sha256??"")||!/^[0-9a-f]{64}$/.test(historical.manifest_sha256??""))return false;
    const manifestText=this.bus.fileAt(MANIFEST_PATH,base),roadmapText=this.bus.fileAt(ROADMAP_PATH,base);
    let manifest:any;try{manifest=JSON.parse(manifestText);}catch{throw new Error("intermediate canonical manifest invalid");}
    const item=manifest?.roadmap_items?.[historical.roadmap_item_id],dependencies=canonicalDependencies(item?.dependencies);
    return manifest?.roadmap_id===historical.roadmap_id&&manifest?.roadmap_version===historical.roadmap_version&&manifest?.repository===historical.repository&&manifest?.integration_branch===INTEGRATION_BRANCH&&manifest?.approval_status==="HUMAN_ADOPTED"&&manifest?.r0_status==="CLOSED_HUMAN_ADOPTED"&&manifest?.human_final_authority===true&&manifest?.auto_merge===false&&manifest?.canonical_local_sync===false&&manifest?.live_trading_enabled===false&&manifest?.roadmap_path===ROADMAP_PATH&&manifest?.roadmap_sha256===sha256(roadmapText)&&historical.roadmap_sha256===sha256(roadmapText)&&historical.manifest_sha256===sha256(manifestText)&&item?.status==="AUTHORIZED_ACTIVE"&&JSON.stringify(dependencies)===JSON.stringify(historical.dependencies??[]);
  }
  ensureIssue(spec:ProxySpec){const existing=this.bus.findOpenFront(spec.front_id!);if(spec.executor==="agent_loop")return this.agentLoopBuilder.ensureIssue(spec,existing);if(existing.length>1)throw new Error("duplicate governed Issues");if(existing.length===1){const persisted=parseIssue(this.bus.issueBody(existing[0])).spec;if(JSON.stringify(persisted)!==JSON.stringify(spec))throw new Error("existing governed Issue spec mismatch");return existing[0];}return this.bus.createGovernedIssue(`feat(control-plane): ${spec.objective}`,issueBody(spec),"operator:building");}
  async ensureBuild(spec:ProxySpec,issue:number,session:string,repairCycle:number,previousHead?:string,retryReason?:"BUILDER_FAILURE"){return spec.executor==="agent_loop"?await this.agentLoopBuilder.observe(spec,issue,repairCycle,previousHead):await this.builder.build(spec,issue,session,repairCycle,retryReason);}
  ci(pr:number,head:string):CiResult {const p=this.bus.json(["pr","view",String(pr),"--json","headRefOid,headRefName"]);if(p.headRefOid!==head)throw new Error("CI head changed");const result=evaluateChecks(this.bus,head,String(p.headRefName));return !result.terminal?"PENDING":result.green?"PASS":"FAIL";}
  private agentLoopReceiptMessage(spec:ProxySpec,state:import("./types.js").LifecycleRecord,head:string){const current=this.bus.commitMessage(head),syncSubject=`chore(control-plane): synchronize ${spec.front_id} base`;if(current.split("\n",1)[0]!==syncSubject)return current;const builds=state.completed_effects.filter(value=>/^build:[0-9a-f]{40}$/.test(value)),candidate=builds.length===1?builds[0].slice(6):undefined;if(!candidate||state.repair_cycles!==0||state.builder_session!==`agent-loop-builder-${candidate}`||!state.completed_effects.includes(`base-sync:${head}`)||!this.bus.isAncestor(candidate,head))throw new Error("Agent Loop synchronized receipt evidence invalid");return this.bus.commitMessage(candidate);}
  private inspectRouterBuilderReceipt(head:string,baseSha:string,frontId:string):{model:string;headCommit:string;status:"VERIFIED"|"PROVENANCE_RECOVERY_REQUIRED"}{
    if(!/^[0-9a-f]{40}$/.test(head)||!/^[0-9a-f]{40}$/.test(baseSha)||!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(frontId))throw new Error("builder model receipt history invalid");
    if(!this.bus.isAncestor(baseSha,head))return {model:"",headCommit:"",status:"PROVENANCE_RECOVERY_REQUIRED"};
    const subject=`feat(control-plane): complete ${frontId}`;
    const syncSubject=`chore(control-plane): synchronize ${frontId} base`;
    const safeModel=/^[a-z0-9][a-z0-9._:/-]{2,127}$/;
    const safeProviderSession=/^[a-z0-9][a-z0-9._:/-]{2,127}$/;
    const allowedBackends=new Set(["codex_cli_openai","opencode_github_copilot","opencode_ollama"]);

    const commitParents=(sha:string)=>{
      const commit=JSON.parse(this.bus.call(["api",`repos/${this.bus.repo}/git/commits/${sha}`]));
      return Array.isArray(commit?.parents)?commit.parents.map((parent:any)=>String(parent?.sha??"")).filter((sha:string)=>/^[0-9a-f]{40}$/.test(sha)):[];
    };
    const commitTree=(sha:string)=>{
      const commit=JSON.parse(this.bus.call(["api",`repos/${this.bus.repo}/git/commits/${sha}`]));
      return typeof commit?.tree?.sha==="string"&&/^[0-9a-f]{40}$/.test(commit.tree.sha)?commit.tree.sha:"";
    };
    const trailer=(message:string,prefix:string)=>message.replace(/\r\n/g,"\n").split("\n").slice(1).filter(line=>line.startsWith(prefix)).map(line=>line.slice(prefix.length));
    const firstLine=(message:string)=>message.replace(/\r\n/g,"\n").split("\n",1)[0];

    const verifyFreshReceipt=(sha:string)=>{
      const message=this.bus.commitMessage(sha);
      if(firstLine(message)!==subject)return undefined;
      const lines=message.replace(/\r\n/g,"\n").split("\n");
      const values=(prefix:string)=>lines.slice(1).filter(line=>line.startsWith(prefix)).map(line=>line.slice(prefix.length));
      const backend=values("BUILDER_BACKEND="),model=values("BUILDER_MODEL="),provider=values("PROVIDER_SESSION="),fallback=values("FALLBACK_REASON=");
      if(backend.length!==1||!allowedBackends.has(backend[0])||model.length!==1||!safeModel.test(model[0])||provider.length!==1||!safeProviderSession.test(provider[0])||fallback.length>1)return undefined;
      return {model:model[0],headCommit:sha,status:"VERIFIED" as const};
    };

    const verifyLegacyRebuild=(sha:string)=>{
      const message=this.bus.commitMessage(sha);
      const parents=commitParents(sha);
      const tree=commitTree(sha);
      if(parents.length!==2)return undefined;
      const [n,r]=parents;
      const nMessage=this.bus.commitMessage(n),rMessage=this.bus.commitMessage(r);
      if(firstLine(message)!==subject)return undefined;
      const isLegacy=trailer(message,`${LEGACY_REBUILD_TRAILER}=`).length===1&&trailer(message,`${LEGACY_REBUILD_TRAILER}=`)[0]==="true";
      if(!isLegacy)return undefined;
      const nNeutral=trailer(nMessage,`${LEGACY_NEUTRALIZATION_TRAILER}=`).length===1&&trailer(nMessage,`${LEGACY_NEUTRALIZATION_TRAILER}=`)[0]==="true";
      if(!nNeutral||firstLine(nMessage)!==`chore(control-plane): neutralize ${frontId} legacy baseline`)return undefined;
      const priorHead=trailer(nMessage,`${PRIOR_UNATTESTED_HEAD_TRAILER}=`)[0];
      const resetBase=trailer(nMessage,`${RESET_BASE_TRAILER}=`)[0];
      const bridgeN=trailer(message,`${NEUTRALIZATION_HEAD_TRAILER}=`)[0];
      const bridgeR=trailer(message,`${FRESH_BUILDER_HEAD_TRAILER}=`)[0];
      if(!priorHead||!resetBase||!bridgeN||!bridgeR||bridgeN!==n||bridgeR!==r)return undefined;
      if(resetBase!==baseSha)return undefined;
      if(!this.bus.isAncestor(baseSha,priorHead)||!this.bus.isAncestor(baseSha,r))return undefined;
      const baseTree=commitTree(baseSha);
      if(commitTree(n)!==baseTree)return undefined;
      if(commitTree(sha)!==commitTree(r))return undefined;
      const fresh=verifyFreshReceipt(r);
      if(!fresh)return undefined;
      return {model:fresh.model,headCommit:r,status:"VERIFIED" as const};
    };

    let current=head,depth=0,candidate:{model:string;headCommit:string;status:"VERIFIED"}|undefined;
    while(current!==baseSha&&!this.bus.isAncestor(current,baseSha)&&depth++<64){
      const legacy=verifyLegacyRebuild(current);
      if(legacy)return legacy;
      const message=this.bus.commitMessage(current);
      if(firstLine(message)===syncSubject){
        const parents=commitParents(current);
        if(parents.length!==2||!this.bus.isAncestor(baseSha,parents[1]))return {model:"",headCommit:"",status:"PROVENANCE_RECOVERY_REQUIRED"};
        current=parents[0];
        continue;
      }
      const fresh=verifyFreshReceipt(current);
      if(!fresh)return {model:"",headCommit:"",status:"PROVENANCE_RECOVERY_REQUIRED"};
      if(!candidate)candidate=fresh;
      const parents=commitParents(current);
      if(parents.length===0)return {model:"",headCommit:"",status:"PROVENANCE_RECOVERY_REQUIRED"};
      current=parents[0];
    }
    if(candidate&&(current===baseSha||this.bus.isAncestor(current,baseSha)))return candidate;
    return {model:"",headCommit:"",status:"PROVENANCE_RECOVERY_REQUIRED"};
  }
  private anchoredRouterBuilderReceipt(state:LifecycleRecord,head:string,front:string){
    const anchored=state.builder_receipt_head_sha!==undefined||state.builder_receipt_base_sha!==undefined;
    if(!anchored)return this.inspectRouterBuilderReceipt(head,state.base_sha,front);
    const receiptHead=state.builder_receipt_head_sha,receiptBase=state.builder_receipt_base_sha;
    if(!receiptHead||!receiptBase||state.builder_session!==`builder-recovered:${head}`||!this.bus.isAncestor(receiptHead,head)||!this.bus.isAncestor(receiptBase,state.base_sha))throw new Error("persisted builder receipt anchor invalid");
    return this.inspectRouterBuilderReceipt(receiptHead,receiptBase,front);
  }
  review(pr:number,head:string,session:string) {const spec=this.activeSpec,state=this.activeState;if(!spec||!state?.issue||state.pr!==pr||state.head_sha!==head||!state.builder_session||!spec.front_id)throw new Error("review lifecycle binding missing");const policyKey=decisionKey(spec,state.issue,pr,state.base_sha,head),identity=this.bus.prIdentity(pr),files=(identity.files??[]).map((x:any)=>String(x.path)),reportPath="docs/agent_loop/pilot/EXECUTOR_REPORT.json",report=spec.executor==="agent_loop"&&files.includes(reportPath)?JSON.parse(this.bus.fileAt(reportPath,head)):undefined,receipt=spec.executor==="agent_loop"?inspectAgentLoopCommitModel(this.agentLoopReceiptMessage(spec,state,head),spec.front_id,report?.model):undefined,routerReceipt=spec.executor==="codex_control_plane"?this.anchoredRouterBuilderReceipt(state,head,spec.front_id):undefined,builderModel=receipt?.model??(routerReceipt?.status==="VERIFIED"?routerReceipt.model:undefined)??verifiedBuilderModel(spec.executor),reviewKey=reviewEvidenceKey(policyKey,state.builder_session,builderModel);if(receipt?.status==="MISSING")return {session:`reviewer:deterministic-receipt-repair:${head}`,output:{verdict:"CHANGES_REQUESTED",head_sha:head,summary:"Agent Loop commit evidence requires bounded regeneration",findings:[{severity:"P1",title:"Executor model receipt missing",evidence:"The exact Agent Loop candidate commit subject is valid, but the required AGENT_LOOP_EXECUTOR_MODEL trailer is absent.",required_correction:"Regenerate the candidate with the installed governed Agent Loop worker so the commit records exactly one configured executor model receipt."}]}};if(spec.executor==="codex_control_plane"&&routerReceipt?.status==="PROVENANCE_RECOVERY_REQUIRED")return {session:`reviewer:builder-provenance-recovery:${head}`,output:{verdict:"CHANGES_REQUESTED",head_sha:head,summary:"Builder model provenance requires a governed fresh rebuild",findings:[{severity:"P1",title:"Builder model receipt missing or invalid",evidence:"The control-plane candidate does not contain a valid BUILDER_MODEL receipt from a governed builder transaction. This may be an unattested legacy candidate or the provenance was lost.",required_correction:"Trigger BUILDER_PROVENANCE_RECOVERY_REQUIRED: run a fresh governed builder transaction from a verified clean baseline and produce a new HEAD containing a real BUILDER_BACKEND/BUILDER_MODEL/PROVIDER_SESSION receipt before review resumes."}]}};const input={repository:spec.repository,repositoryRoot:this.sourceRepo,pr,baseSha:state.base_sha,headSha:head,risk:spec.risk,changedFiles:files,builderSession:state.builder_session,builderModel},expected={issue:state.issue,pr,base_sha:state.base_sha,head_sha:head,front_id:spec.front_id,builder_session:state.builder_session,builder_model:builderModel};const cached=this.ledger.loadOrCreateReview(reviewKey,()=>{this.boundary.assert("reviewer_execute",{issue:state.issue,pr,expected_head:head});const run=new ReviewerRouter(join(this.root,"reviewer-router")).review(input);return {schema_version:1,...expected,requested_session:session,session:run.session,router_run:run,result:run.output};},value=>{validateReviewerEnvelope(value,expected,input);}).review as any;return {output:cached.result,session:cached.session};}
  policy(spec:ProxySpec,issue:number,pr:number,head:string,review:ReviewerOutput,builderSession:string,reviewerSession:string,repairCycles:number):PolicyResult {review=normalizeReviewerOutput(review,head);const key=decisionKey(spec,issue,pr,spec.expected_base_sha,head),evidence=collect(this.bus,issue,pr,reviewerSession,review,spec);evidence.builder_session=builderSession;evidence.review_session=reviewerSession;evidence.repair_cycles=repairCycles;const candidate=decide(spec,evidence),prior=this.ledger.findByKey(key)??this.ledger.findByHead(head);if(prior){if(!decisionMatchesCandidate(prior,candidate))throw new Error("DECISION_IDENTITY_CONFLICT");return {outcome:prior.policy_decision,decision_id:prior.decision_id};}this.boundary.assert("decision_persist",{issue,pr,expected_head:head});const decision=this.ledger.recordOrLoad(candidate).decision;if(decision.policy_decision==="REPAIR"){this.boundary.assert("findings_publish",{issue,pr,expected_head:head});this.boundary.assert("repair_request",{issue,pr,expected_head:head});const marker=`decision_key=${decision.decision_key}`;this.bus.commentOnce("issue",issue,marker,`[OPERATOR-PROXY][REPAIR]\n\n${marker}\ndecision_id=${decision.decision_id}\nhead=${head}\nfindings=${safeJson(review.findings)}`);if(spec.executor==="agent_loop"){this.bus.reconcileLabel("issue",issue,"loop:repairing",["operator:repairing","loop:ci"]);this.bus.reconcileLabel("pr",pr,"loop:repairing",["operator:repairing","loop:ci"]);}}return {outcome:decision.policy_decision,decision_id:decision.decision_id};}
  ensureMerge(pr:number,head:string,base:string,decisionId:string){const spec=this.activeSpec,state=this.activeState;if(!spec||!state?.issue||state.pr!==pr||state.head_sha!==head||state.base_sha!==base||state.decision_id!==decisionId||!state.builder_session||!state.reviewer_session)throw new Error("merge lifecycle binding missing");const decision=this.ledger.load(decisionId);if(decision.pr!==pr||decision.head_sha!==head||decision.base_sha!==base)throw new Error("merge decision binding mismatch");const alreadyMerged=this.ledger.hasHead(head)||this.bus.prIdentity(pr).state==="MERGED";if(!alreadyMerged){const reviewed=this.review(pr,head,state.reviewer_session),recomputed=this.policy(spec,state.issue,pr,head,reviewed.output,state.builder_session,reviewed.session,state.repair_cycles);if(recomputed.outcome!=="APPROVE"||recomputed.decision_id!==decisionId)throw new Error("merge decision revalidation failed");}const merge=execute(this.bus,this.ledger,decision,false);if(!merge)throw new Error("governed merge not completed");this.boundary.bindPostMerge(merge);reconcileAuthorizationComment(this.bus,decision);return merge;}
  ensureInstall(spec:ProxySpec,merge:string){const path=installArtifactPath(spec);if(!path)throw new Error("install artifact target invalid");const artifactSha256=createHash("sha256").update(Buffer.from(this.bus.fileAt(path,merge),"utf8")).digest("hex");return this.coordinator.install(spec,merge,artifactSha256);}
  ensureRuntimePilot(spec:ProxySpec,merge:string){return this.coordinator.pilot(spec,merge);}
  // =========================================================================
  // Plan-driven reconciliation pipeline
  //
  // OBSERVE -> normalizeObservedFacts() -> CanonicalLifecycleSnapshot
  //         -> deriveReconciliationPlan()  (finite domain moves)
  //         -> validateInvariantSet()      (single safety gate)
  //         -> applyPlan()                 (one applier per domain move)
  //
  // This replaces the accumulated incident-shaped reconcile* dispatchers.
  // =========================================================================
  private plannerPorts(spec: ProxySpec, state: LifecycleRecord): PlannerPorts {
    const frontId = spec.front_id ?? state.front_id;
    return {
      checksGreenAtHead: head => safe(() => {const checks = evaluateChecks(this.bus, head, spec.work_branch ?? ""); return !!checks.terminal && !!checks.green;}) ?? false,
      authorizedBaseIsCanonicalTip: () => safe(() => (this.bus.remoteBranchHead(INTEGRATION_BRANCH) ?? "") === spec.expected_base_sha) ?? false,
      recordedAdoptionEvent: record => new LifecycleStore(join(this.root, "lifecycle")).verifiedSynchronizedBuilderAdoption(record),
      loadDecision: id => this.ledger.load(id),
      verifyReceipt: (receiptHead, receiptBase) => this.inspectRouterBuilderReceipt(receiptHead, receiptBase, frontId).status === "VERIFIED",
      verifyBridgeCandidate: (nextBase, nextHead) => safe(() => this.inspectBridgeCandidate(spec, {...state, base_sha: nextBase, head_sha: nextHead})) !== undefined,
      decisionBoundToLineage: decision => decisionBoundToLineageRole(decision, spec, state, this.bus),
    };
  }
  derivePlan(spec: ProxySpec, state: LifecycleRecord): ReconciliationPlan {
    const snapshot = normalizeObservedFacts(spec, state, {bus: this.bus, loadDecision: id => safe(() => this.ledger.load(id))});
    return deriveReconciliationPlan(snapshot, this.plannerPorts(spec, state));
  }
  /** Non-mutating dry-run: outputs the normalized snapshot, lineage, invariants and plan. */
  dryRunReconciliation(spec: ProxySpec, state: LifecycleRecord) {
    const snapshot = normalizeObservedFacts(spec, state, {bus: this.bus, loadDecision: id => safe(() => this.ledger.load(id))});
    const plan = deriveReconciliationPlan(snapshot, this.plannerPorts(spec, state));
    const invariants = validateInvariantSet(snapshot, plan, this.plannerPorts(spec, state));
    return {snapshot, plan, invariants};
  }
  applyPlan(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore, plan: ReconciliationPlan): LifecycleRecord {
    switch (plan.move) {
      case "NOOP": return state;
      case "REBIND_UNSTARTED_BASE": return store.rebindUnstartedBase(state, spec.expected_base_sha);
      case "REBIND_PRE_BUILD_BASE": return this.rebindPreBuildBaseApplier(spec, state, store);
      case "REBIND_POST_MERGE_BASE": return store.rebindPostMergeBase(state, spec.expected_base_sha);
      case "RESUME_INITIAL_BUILD": return state.base_sha === spec.expected_base_sha ? store.resumeInitialBuilderFailure(state) : store.resumeInitialBuilderFailureAtAdvancedBase(state, spec.expected_base_sha);
      case "RESUME_RECORDED_BUILD": return store.resumeRecordedBuilderRetry(state);
      case "ADOPT_PUBLISHED_INITIAL_CANDIDATE": {
        // For a decided bridge adoption (CI_PENDING/REVIEWING with no reviewer)
        // the store applies the bridge; for an initial retry the candidate is
        // published and synchronized. The state shape distinguishes them.
        if (["CI_PENDING", "REVIEWING"].includes(state.state) && state.pr && state.builder_session) {
          const bridge = safe(() => this.inspectBridgeCandidate(spec, state));
          if (bridge) return store.adoptBridgeCandidate(state, bridge.nextBase, bridge.nextHead);
        }
        return this.adoptPublishedInitialCandidate(spec, state, store);
      }
      case "ADOPT_PUBLISHED_REPAIR_CANDIDATE": return this.adoptBlockedBuilderCandidate(spec, state, store);
      case "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE": return this.adoptVerifiedSynchronizedCandidate(spec, state, store);
      case "REVERT_INVALIDATED_ADOPTION": return this.revertInvalidatedAdoption(spec, state, store);
      case "SYNCHRONIZE_CANDIDATE": {
        // Undecided post-build evidence is invalidated before recovery: an
        // unreviewed candidate never carries across a base advance.
        if (["CI_PENDING", "REVIEWING"].includes(state.state) && !state.reviewer_session && !state.decision_id) {
          return this.synchronizeCandidate(spec, store.invalidatePostBuildBase(state), store);
        }
        // A builder-failure origin preserves the immutable decision evidence
        // while resuming the build (exact domain semantics of the failure path).
        if (state.state === "BLOCKED" && /^BUILDER_FAILED:[A-Z_]+$/.test(state.last_error ?? "") && state.reviewer_session && state.decision_id) {
          return this.synchronizeForBuilderFailure(spec, state, store);
        }
        if (state.state === "BUILDING" && state.reviewer_session && state.decision_id) {
          return this.synchronizeRepairDecided(spec, state, store);
        }
        return this.synchronizeCandidate(spec, state, store);
      }
      case "REOPEN_CI": return store.recoverBlockedCiChecks(state);
      case "REQUEST_DETERMINISTIC_REPAIR": return this.requestDeterministicRepair(spec, state, store);
      case "EXHAUST_REPAIR": return store.exhaustBlockedCiRepair(state);
      case "ADOPT_EXTERNAL_MERGE": return this.adoptExternalMerge(spec, state, store) ?? (() => {throw new Error("external merge adoption denied");})();
      case "RECOVER_NEGATED_RISK_ESCALATION": return this.recoverNegatedRiskEscalationApplier(spec, state, store);
      case "INVALIDATE_FAILED_MERGE": return this.synchronizeCandidate(spec, this.invalidateFailedMerge(spec, state, store), store);
      case "ESCALATE_OWNER": throw new Error("reconciliation requires owner authority: " + plan.reason);
      default: throw new Error("reconciliation plan is not executable: " + plan.move + " (" + plan.reason + ")");
    }
  }
  /** OBSERVE -> plan -> invariants -> apply. The authoritative recovery entry point. */
  reconcile(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore): LifecycleRecord {
    const dry = this.dryRunReconciliation(spec, state);
    if (dry.invariants.violations.length) throw new Error("reconciliation invariants violated: " + dry.invariants.violations.join(", "));
    return this.applyPlan(spec, state, store, dry.plan);
  }
  // ---- appliers (domain-move parameterized; boundary + Issue contract shared) ----
  private rebindPreBuildBaseApplier(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    if (state.base_sha === spec.expected_base_sha) return state;
    if (this.bus.remoteBranchHead(spec.work_branch!) || this.bus.prCandidatesByBranch(spec.work_branch!).length) throw new Error("pre-build base reconciliation denied: published candidate exists");
    const snapshot = this.bus.issueSnapshot(state.issue!);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== "operator:building") throw new Error("pre-build Issue state invalid");
    const oldSpec = {...spec, expected_base_sha: state.base_sha};
    const oldBody = issueBody(oldSpec), nextBody = issueBody(spec);
    const parsed = parseIssue(snapshot.body);
    if (parsed.pr || snapshot.body !== oldBody && snapshot.body !== nextBody) throw new Error("pre-build Issue contract mismatch");
    this.boundary.bind(spec, state);
    if (snapshot.body === oldBody) this.bus.replaceIssueBodyExact(state.issue!, oldBody, nextBody);
    const updated = store.rebindPreBuildBase(state, spec.expected_base_sha);
    this.bindLifecycle(spec, updated);
    return updated;
  }
  private adoptPublishedInitialCandidate(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const candidates = this.bus.prCandidatesByBranch(spec.work_branch!);
    const trusted = candidates.filter((candidate: any) => candidate?.author?.login === spec.repository.split("/", 1)[0] && candidate?.baseRefName === INTEGRATION_BRANCH && candidate?.baseRefOid === state.base_sha && candidate?.headRefName === spec.work_branch && candidate?.headRepository?.nameWithOwner === spec.repository && candidate?.isCrossRepository === false && candidate?.isDraft === true && candidate?.state === "OPEN" && Number.isInteger(Number(candidate?.number)) && /^[0-9a-f]{40}$/.test(String(candidate?.headRefOid ?? "")));
    if (trusted.length !== 1) throw new Error(`published candidate count invalid: ${trusted.length}`);
    const selected = trusted[0];
    const prNumber = Number(selected.number);
    const pr = this.bus.prIdentity(prNumber);
    const candidateHead = String(selected.headRefOid);
    const files = (pr.files ?? []).map((entry: any) => String(entry.path));
    const identity = pr.author?.login === spec.repository.split("/", 1)[0] && pr.baseRefName === INTEGRATION_BRANCH && pr.baseRefOid === state.base_sha && pr.headRefName === spec.work_branch && pr.headRefOid === candidateHead && pr.headRepository?.nameWithOwner === spec.repository && pr.isCrossRepository === false && pr.isDraft === true && pr.state === "OPEN" && ["MERGEABLE", "UNKNOWN"].includes(pr.mergeable) && files.length > 0 && files.every((path: string) => pathAllowed(path, spec)) && this.bus.remoteBranchHead(spec.work_branch!) === candidateHead && this.bus.isAncestor(state.base_sha, candidateHead);
    if (!identity || this.inspectRouterBuilderReceipt(candidateHead, state.base_sha, spec.front_id!).status !== "VERIFIED") throw new Error("published candidate identity invalid");
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const parsed = parseIssue(snapshot.body);
    const historicalBase = parsed.spec.expected_base_sha;
    const oldBody = boundIssueBody(parsed.spec, prNumber), nextBody = boundIssueBody(spec, prNumber);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== "operator:building" || parsed.pr !== prNumber || snapshot.body !== oldBody || !historicalBase || !this.validHistoricalRoadmapBinding(spec, parsed.spec, historicalBase) || !this.bus.isAncestor(historicalBase, state.base_sha)) throw new Error("published candidate Issue identity invalid");
    const builderSession = `builder-recovered:${candidateHead}`;
    const recoveryState = {...state, state: "BLOCKED" as const, last_error: "CI_FAILED", pr: prNumber, head_sha: candidateHead, builder_session: builderSession, completed_effects: [`issue:${state.issue}`, `build:${candidateHead}`]};
    this.boundary.beginBlockedCiRecovery(spec, recoveryState);
    try {
      const nextHead = this.builder.synchronizeBlockedCiBase(spec, recoveryState);
      this.boundary.bindBlockedCiRecoveryHead(nextHead);
      this.bus.replaceIssueBodyExact(state.issue!, snapshot.body, nextBody, nextHead);
      const updated = store.adoptInitialRetryCandidate(state, spec.expected_base_sha, prNumber, candidateHead, nextHead, builderSession);
      this.bindLifecycle(spec, updated);
      return updated;
    } finally { this.boundary.endBlockedCiRecovery(); }
  }
  private adoptBlockedBuilderCandidate(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const workBranch = spec.work_branch, oldHead = state.head_sha;
    if (!workBranch || !oldHead) throw new Error("blocked builder candidate evidence missing");
    const candidates = this.bus.prCandidatesByBranch(workBranch);
    const trusted = candidates.filter((candidate: any) => candidate?.author?.login === spec.repository.split("/", 1)[0] && candidate?.baseRefName === INTEGRATION_BRANCH && candidate?.baseRefOid === state.base_sha && candidate?.headRefName === workBranch && candidate?.headRepository?.nameWithOwner === spec.repository && candidate?.isCrossRepository === false && candidate?.isDraft === true && candidate?.state === "OPEN" && Number.isInteger(Number(candidate?.number)) && /^[0-9a-f]{40}$/.test(String(candidate?.headRefOid ?? "")));
    if (trusted.length !== 1) throw new Error(`blocked builder candidate count invalid: ${trusted.length}`);
    const selected = trusted[0];
    const prNumber = Number(selected.number);
    const pr = this.bus.prIdentity(prNumber);
    const candidateHead = String(selected.headRefOid);
    const files = (pr.files ?? []).map((entry: any) => String(entry.path));
    const identity = pr.author?.login === spec.repository.split("/", 1)[0] && pr.baseRefName === INTEGRATION_BRANCH && pr.baseRefOid === state.base_sha && pr.headRefName === workBranch && pr.headRefOid === candidateHead && pr.headRepository?.nameWithOwner === spec.repository && pr.isCrossRepository === false && pr.isDraft === true && pr.state === "OPEN" && ["MERGEABLE", "UNKNOWN"].includes(pr.mergeable) && files.length > 0 && files.every((path: string) => pathAllowed(path, spec)) && this.bus.remoteBranchHead(workBranch) === candidateHead && this.bus.isAncestor(oldHead, candidateHead);
    if (!identity || this.inspectRouterBuilderReceipt(candidateHead, state.base_sha, spec.front_id!).status !== "VERIFIED") throw new Error("blocked builder candidate identity invalid");
    const checks = evaluateChecks(this.bus, candidateHead, workBranch);
    if (!checks.terminal || !checks.green) throw new Error("blocked builder candidate CI not green");
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const parsed = parseIssue(snapshot.body);
    const expectedBody = boundIssueBody(spec, prNumber);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== "operator:building" || parsed.pr !== prNumber || snapshot.body !== expectedBody) throw new Error("blocked builder candidate Issue identity invalid");
    const updated = store.adoptBlockedBuilderCandidate(state, candidateHead, prNumber, `builder-recovered:${candidateHead}`);
    this.bindLifecycle(spec, updated);
    return updated;
  }
  private adoptVerifiedSynchronizedCandidate(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const decision = state.decision_id ? this.ledger.load(state.decision_id) : undefined;
    if (!decision) throw new Error("synchronized candidate decision missing");
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const expectedBody = boundIssueBody({...spec, expected_base_sha: state.base_sha}, state.pr!);
    const pr = this.bus.prIdentity(state.pr!);
    const files = (pr.files ?? []).map((entry: any) => String(entry.path));
    const identity = snapshot.state === "OPEN" && snapshot.labels.length === 1 && snapshot.labels[0] === blockedCiIssuePhase(spec) && snapshot.body === expectedBody && pr.author?.login === spec.repository.split("/", 1)[0] && pr.baseRefName === INTEGRATION_BRANCH && pr.baseRefOid === state.base_sha && pr.headRefName === spec.work_branch && pr.headRefOid === state.head_sha && pr.headRepository?.nameWithOwner === spec.repository && pr.isCrossRepository === false && pr.isDraft === true && pr.state === "OPEN" && ["MERGEABLE", "UNKNOWN"].includes(pr.mergeable) && files.length > 0 && files.every((path: string) => pathAllowed(path, spec)) && this.bus.remoteBranchHead(spec.work_branch!) === state.head_sha;
    if (!identity || this.inspectRouterBuilderReceipt(decision.head_sha, decision.base_sha, spec.front_id!).status !== "VERIFIED") throw new Error("synchronized candidate identity invalid");
    const checks = evaluateChecks(this.bus, state.head_sha!, spec.work_branch!);
    if (!checks.terminal || !checks.green) throw new Error("synchronized candidate CI not green");
    const synchronized = state.base_sha === spec.expected_base_sha ? state : this.reconcileBuilderFailureBase(spec, state, store);
    const updated = store.adoptVerifiedSynchronizedBuilderCandidate(synchronized, `builder-recovered:${synchronized.head_sha}`, decision.head_sha, decision.base_sha);
    this.bindLifecycle(spec, updated);
    return updated;
  }
  private revertInvalidatedAdoption(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const falseDecision = state.decision_id ? this.ledger.load(state.decision_id) : undefined;
    const adoption = store.verifiedSynchronizedBuilderAdoption(state);
    const priorDecision = this.ledger.load(String(adoption.prior_decision_id ?? ""));
    const receiptHead = priorDecision.head_sha, receiptBase = priorDecision.base_sha;
    const adoptionExact = Number.isInteger(adoption.repair_cycle) && adoption.repair_cycle > 0 && Array.isArray(adoption.prior_effects) && adoption.prior_effects.includes(`build:${receiptHead}`);
    const decisionExact = !!falseDecision && falseDecision.schema_version === 2 && falseDecision.decision_id === state.decision_id && falseDecision.policy_sha256 === POLICY_SHA256 && falseDecision.policy_decision === "REPAIR" && falseDecision.allowed_action === "REQUEST_REPAIR" && decisionBoundToLineageRole(falseDecision, spec, state, this.bus);
    // The prior decision binds through the immutable adoption event: its head is
    // the recorded provenance root of the synchronized candidate, and ancestry
    // closes the chain to the current state.
    const priorHeadRecorded = Array.isArray(adoption.prior_effects) && (adoption.prior_effects.includes(`build:${receiptHead}`) || adoption.prior_effects.includes(`base-sync:${receiptHead}`));
    const priorExact = priorDecision.schema_version === 2 && priorDecision.decision_id === adoption.prior_decision_id && priorDecision.policy_decision === "REPAIR" && priorDecision.allowed_action === "REQUEST_REPAIR" && (priorDecision.authorization_id === spec.authorization_id && priorDecision.repository === spec.repository && priorDecision.issue === state.issue && priorDecision.pr === state.pr && priorDecision.roadmap_id === spec.roadmap_id && priorDecision.roadmap_item_id === spec.roadmap_item_id) && (priorHeadRecorded || decisionBoundToLineageRole(priorDecision, spec, state, this.bus)) && adoptionExact && this.bus.isAncestor(receiptHead, state.head_sha!) && this.bus.isAncestor(receiptBase, state.base_sha);
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const expectedBody = boundIssueBody(spec, state.pr!);
    const pr = this.bus.prIdentity(state.pr!);
    const files = (pr.files ?? []).map((entry: any) => String(entry.path));
    const identity = snapshot.state === "OPEN" && snapshot.labels.length === 1 && snapshot.labels[0] === blockedCiIssuePhase(spec) && snapshot.body === expectedBody && pr.author?.login === spec.repository.split("/", 1)[0] && pr.baseRefName === INTEGRATION_BRANCH && pr.baseRefOid === state.base_sha && pr.headRefName === spec.work_branch && pr.headRefOid === state.head_sha && pr.headRepository?.nameWithOwner === spec.repository && pr.isCrossRepository === false && pr.isDraft === true && pr.state === "OPEN" && pr.mergeable === "MERGEABLE" && files.length > 0 && files.every((path: string) => pathAllowed(path, spec)) && this.bus.remoteBranchHead(spec.work_branch!) === state.head_sha;
    const checks = evaluateChecks(this.bus, state.head_sha!, spec.work_branch!);
    if (!decisionExact || !priorExact || !identity || !checks.terminal || !checks.green || this.inspectRouterBuilderReceipt(receiptHead, receiptBase, spec.front_id!).status !== "VERIFIED") throw new Error("invalidated adoption reconciliation denied");
    const updated = store.recoverFalseBuilderProvenanceRepair(state, adoption, receiptHead, receiptBase);
    this.bindLifecycle(spec, updated);
    return updated;
  }
  private synchronizeRepairDecided(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const oldSpec = {...spec, expected_base_sha: state.base_sha};
    const oldBody = boundIssueBody(oldSpec, state.pr!), nextBody = boundIssueBody(spec, state.pr!);
    const parsed = parseIssue(snapshot.body);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== blockedCiIssuePhase(spec) || parsed.pr !== state.pr || JSON.stringify(parsed.spec) !== JSON.stringify(snapshot.body === oldBody ? oldSpec : spec) || snapshot.body !== oldBody && snapshot.body !== nextBody) throw new Error("repair base Issue identity invalid");
    if (spec.executor === "agent_loop") parseAgentLoopIssue(snapshot.body, snapshot.body === oldBody ? oldSpec : spec);
    const branchState = {...state, state: "BLOCKED" as const, last_error: "CI_FAILED", repair_cycles: 0, reviewer_session: undefined, decision_id: undefined};
    this.boundary.beginBlockedCiRecovery(spec, branchState);
    try {
      const nextHead = this.builder.synchronizeBlockedCiBase(spec, branchState);
      this.boundary.bindBlockedCiRecoveryHead(nextHead);
      if (snapshot.body === oldBody) this.bus.replaceIssueBodyExact(state.issue!, oldBody, nextBody, nextHead);
      const updated = store.recoverRepairBase(state, spec.expected_base_sha, nextHead);
      this.bindLifecycle(spec, updated);
      return updated;
    } finally { this.boundary.endBlockedCiRecovery(); }
  }
  private synchronizeCandidate(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const oldSpec = {...spec, expected_base_sha: state.base_sha};
    const oldBody = boundIssueBody(oldSpec, state.pr!), nextBody = boundIssueBody(spec, state.pr!);
    const parsed = parseIssue(snapshot.body);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== blockedCiIssuePhase(spec)) throw new Error("synchronization Issue state invalid");
    if (parsed.pr !== state.pr) throw new Error("synchronization Issue contract mismatch");
    let recoveryState = state, issueSpec: ProxySpec = snapshot.body === oldBody ? oldSpec : spec;
    let intermediateBridged = false;
    if (snapshot.body !== oldBody && snapshot.body !== nextBody) {
      const pr = this.bus.prIdentity(state.pr!);
      const files = (pr.files ?? []).map((x: any) => String(x.path));
      const intermediateBase = String(pr.baseRefOid ?? ""), intermediateHead = String(pr.headRefOid ?? "");
      const intermediateSpec = parsed.spec, intermediateBody = boundIssueBody(intermediateSpec, state.pr!);
      const exact = typeof spec.work_branch === "string" && typeof state.head_sha === "string" && pr.author?.login === spec.repository.split("/", 1)[0] && pr.baseRefName === INTEGRATION_BRANCH && pr.headRefName === spec.work_branch && pr.headRepository?.nameWithOwner === spec.repository && pr.isCrossRepository === false && pr.isDraft === true && pr.state === "OPEN" && pr.mergeable === "MERGEABLE" && this.bus.remoteBranchHead(spec.work_branch) === intermediateHead && files.length > 0 && files.every((path: string) => pathAllowed(path, spec)) && snapshot.body === intermediateBody && this.validHistoricalRoadmapBinding(spec, intermediateSpec, intermediateBase) && this.bus.isAncestor(state.base_sha, intermediateBase) && this.bus.isAncestor(intermediateBase, spec.expected_base_sha) && this.bus.isAncestor(state.head_sha, intermediateHead);
      if (!exact) throw new Error("synchronization intermediate bridge identity invalid");
      recoveryState = store.stageBlockedCiBridge(state, intermediateBase, intermediateHead);
      issueSpec = intermediateSpec;
      intermediateBridged = true;
    } else if (JSON.stringify(parsed.spec) !== JSON.stringify(issueSpec)) throw new Error("synchronization Issue spec mismatch");
    if (spec.executor === "agent_loop") parseAgentLoopIssue(snapshot.body, issueSpec);
    const branchState = {...recoveryState, state: "BLOCKED" as const, last_error: "CI_FAILED", repair_cycles: 0, reviewer_session: undefined, decision_id: undefined};
    this.boundary.beginBlockedCiRecovery(spec, branchState);
    try {
      const nextHead = this.builder.synchronizeBlockedCiBase(spec, branchState);
      this.boundary.bindBlockedCiRecoveryHead(nextHead);
      if (snapshot.body === oldBody) this.bus.replaceIssueBodyExact(state.issue!, oldBody, nextBody, nextHead);
      else if (intermediateBridged && snapshot.body !== nextBody) this.bus.replaceIssueBodyExact(state.issue!, snapshot.body, nextBody, nextHead);
      const updated = store.recoverBlockedCiBase(recoveryState, spec.expected_base_sha, nextHead);
      this.bindLifecycle(spec, updated);
      return updated;
    } finally { this.boundary.endBlockedCiRecovery(); }
  }
  private synchronizeForBuilderFailure(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const decision = state.decision_id ? this.ledger.load(state.decision_id) : undefined;
    if (decision) state = store.compactBuilderFailureEffectChain(state, decision.head_sha);
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const oldSpec = {...spec, expected_base_sha: state.base_sha};
    const oldBody = boundIssueBody(oldSpec, state.pr!), nextBody = boundIssueBody(spec, state.pr!);
    const parsed = parseIssue(snapshot.body);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== blockedCiIssuePhase(spec) || parsed.pr !== state.pr || JSON.stringify(parsed.spec) !== JSON.stringify(snapshot.body === oldBody ? oldSpec : spec) || snapshot.body !== oldBody && snapshot.body !== nextBody) throw new Error("builder failure base Issue identity invalid");
    if (spec.executor === "agent_loop") parseAgentLoopIssue(snapshot.body, snapshot.body === oldBody ? oldSpec : spec);
    const branchState = {...state, state: "BLOCKED" as const, last_error: "CI_FAILED", repair_cycles: 0, reviewer_session: undefined, decision_id: undefined};
    this.boundary.beginBlockedCiRecovery(spec, branchState);
    try {
      this.bindObservedBlockedCiHead(spec, branchState);
      const nextHead = this.builder.synchronizeBlockedCiBase(spec, branchState);
      this.boundary.bindBlockedCiRecoveryHead(nextHead);
      if (snapshot.body === oldBody) this.bus.replaceIssueBodyExact(state.issue!, oldBody, nextBody, nextHead);
      const updated = store.recoverBuilderFailureBase(state, spec.expected_base_sha, nextHead);
      this.bindLifecycle(spec, updated);
      return updated;
    } finally { this.boundary.endBlockedCiRecovery(); }
  }
  private requestDeterministicRepair(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const expectedBody = boundIssueBody(spec, state.pr!);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== blockedCiIssuePhase(spec) || snapshot.body !== expectedBody) throw new Error("deterministic repair Issue identity invalid");
    if (spec.executor === "agent_loop") parseAgentLoopIssue(snapshot.body, spec);
    const pr = this.bus.prIdentity(state.pr!);
    const files = (pr.files ?? []).map((x: any) => String(x.path));
    if (pr.author?.login !== "cesarmanuel8102" || pr.baseRefName !== "codex/own-capital-sustainable-return" || pr.baseRefOid !== state.base_sha || pr.headRefName !== spec.work_branch || pr.headRefOid !== state.head_sha || pr.headRepository?.nameWithOwner !== "cesarmanuel8102/AI_Vault" || pr.isCrossRepository !== false || pr.isDraft !== true || pr.state !== "OPEN" || pr.mergeable !== "MERGEABLE" || files.length === 0 || !files.every((path: string) => pathAllowed(path, spec)) || this.bus.remoteBranchHead(spec.work_branch!) !== state.head_sha) throw new Error("deterministic repair PR identity invalid");
    const ci = this.ci(state.pr!, state.head_sha!);
    if (ci === "PENDING") throw new Error("deterministic repair CI not terminal");
    if (ci === "PASS") return store.recoverBlockedCiChecks(state);
    const evaluated = evaluateChecks(this.bus, state.head_sha!, spec.work_branch!);
    if (!evaluated.terminal || evaluated.green) throw new Error("deterministic repair CI evidence inconsistent");
    if (state.repair_cycles >= 2) return store.exhaustBlockedCiRepair(state);
    const failed = evaluated.checks.filter((check: any) => check.status === "COMPLETED" && !(["SUCCESS", "SKIPPED"].includes(check.conclusion))).map((check: any) => String(check.name)).sort();
    const evidence = failed.length ? failed.join(", ") : "required CI contract set incomplete";
    const review: ReviewerOutput = {verdict: "CHANGES_REQUESTED", head_sha: state.head_sha!, summary: "Deterministic CI requires a bounded candidate repair", findings: [{severity: "P1", title: "Governed CI contract failed", evidence, required_correction: "Repair only the failing deterministic contracts within the existing allowlist and publish a new candidate HEAD."}]};
    const reviewerSession = `reviewer:deterministic-ci:${state.head_sha}`;
    this.boundary.beginBlockedCiRepair(spec, state);
    try {
      const decision = this.policy(spec, state.issue!, state.pr!, state.head_sha!, review, state.builder_session!, reviewerSession, state.repair_cycles);
      if (decision.outcome !== "REPAIR") throw new Error("deterministic repair policy denied");
      const marker = `decision_key=${decisionKey(spec, state.issue!, state.pr!, state.base_sha, state.head_sha!)}`;
      this.boundary.assert("findings_publish", {issue: state.issue, pr: state.pr, expected_head: state.head_sha});
      this.boundary.assert("repair_request", {issue: state.issue, pr: state.pr, expected_head: state.head_sha});
      this.bus.commentOnce("issue", state.issue!, marker, `[OPERATOR-PROXY][REPAIR]\n\n${marker}\ndecision_id=${decision.decision_id}\nhead=${state.head_sha}\nfindings=${safeJson(review.findings)}`);
      const updated = store.resumeBlockedCiRepair(state, reviewerSession, decision.decision_id);
      this.bindLifecycle(spec, updated);
      return updated;
    } finally { this.boundary.endBlockedCiRepair(); }
  }
  private adoptExternalMerge(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    if (!state.pr) return undefined;
    const pr = this.bus.prIdentity(state.pr);
    const files = (pr.files ?? []).map((x: any) => String(x.path));
    if (this.bus.repo !== spec.repository || pr.author?.login !== spec.repository.split("/", 1)[0] || pr.baseRefName !== INTEGRATION_BRANCH || pr.baseRefOid !== state.base_sha || pr.headRefName !== spec.work_branch || pr.headRepository?.nameWithOwner !== spec.repository || pr.isCrossRepository !== false || pr.state !== "MERGED" || pr.isDraft !== false || files.length === 0 || !files.every((path: string) => pathAllowed(path, spec))) return undefined;
    const candidateHead = String(pr.headRefOid ?? "");
    if (!/^[0-9a-f]{40}$/.test(candidateHead) || candidateHead === state.head_sha || !this.bus.isAncestor(state.head_sha!, candidateHead) || this.bus.remoteBranchHead(spec.work_branch!) !== candidateHead) return undefined;
    const merge = this.bus.verifyMerged(state.pr!, candidateHead, state.base_sha);
    const currentBase = this.bus.remoteBranchHead(INTEGRATION_BRANCH) ?? "";
    const baseAdvanced = merge !== currentBase && this.bus.isAncestor(merge, currentBase);
    if (currentBase !== spec.expected_base_sha || merge !== currentBase && !baseAdvanced) return undefined;
    const checks = evaluateChecks(this.bus, candidateHead, spec.work_branch!);
    if (!checks.terminal || !checks.green || !checks.checks.some((check: any) => check.name === "review" && check.status === "COMPLETED" && check.conclusion === "SUCCESS")) return undefined;
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const expectedBody = boundIssueBody({...spec, expected_base_sha: state.base_sha}, state.pr!);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== blockedCiIssuePhase(spec) || snapshot.body !== expectedBody) return undefined;
    if (spec.executor === "agent_loop") parseAgentLoopIssue(snapshot.body, {...spec, expected_base_sha: state.base_sha});
    const updated = store.adoptExternallyMergedPr(state, spec.expected_base_sha, candidateHead, merge, "review", baseAdvanced);
    this.bindLifecycle(spec, updated);
    return updated;
  }
  private recoverNegatedRiskEscalationApplier(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const snapshot = this.bus.issueSnapshot(state.issue!);
    const oldSpec = {...spec, expected_base_sha: state.base_sha};
    const oldBody = boundIssueBody(oldSpec, state.pr!), nextBody = boundIssueBody(spec, state.pr!);
    const parsed = parseIssue(snapshot.body);
    if (snapshot.state !== "OPEN" || snapshot.labels.length !== 1 || snapshot.labels[0] !== blockedCiIssuePhase(spec) || parsed.pr !== state.pr || JSON.stringify(parsed.spec) !== JSON.stringify(snapshot.body === oldBody ? oldSpec : spec) || snapshot.body !== oldBody && snapshot.body !== nextBody) throw new Error("negated risk escalation Issue identity invalid");
    if (spec.executor === "agent_loop") parseAgentLoopIssue(snapshot.body, snapshot.body === oldBody ? oldSpec : spec);
    this.boundary.beginNegatedRiskRecovery(spec, state);
    try {
      const branchState = {...state, state: "BLOCKED" as const, last_error: "CI_FAILED", reviewer_session: undefined, decision_id: undefined};
      const nextHead = this.builder.synchronizeBlockedCiBase(spec, branchState);
      this.boundary.bindBlockedCiRecoveryHead(nextHead);
      if (snapshot.body === oldBody) this.bus.replaceIssueBodyExact(state.issue!, oldBody, nextBody, nextHead);
      const updated = store.recoverNegatedRiskEscalation(state, spec.expected_base_sha, nextHead);
      this.bindLifecycle(spec, updated);
      return updated;
    } finally { this.boundary.endBlockedCiRecovery(); }
  }
  invalidateFailedMerge(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const decision = state.decision_id ? this.ledger.load(state.decision_id) : undefined;
    const pr = state.pr ? this.bus.prIdentity(state.pr) : undefined;
    const files = (pr?.files ?? []).map((x: any) => String(x.path));
    const baseTip = pr?.baseRefName ? this.bus.remoteBranchHead(pr.baseRefName) : undefined;
    const acceptedPrBase = pr?.baseRefOid === state.base_sha || pr?.baseRefOid === spec.expected_base_sha;
    const exact = decision && decision.authorization_id === spec.authorization_id && decision.repository === spec.repository && decision.policy_sha256 === POLICY_SHA256 && ["LOW", "MEDIUM"].includes(decision.risk) && decision.policy_decision === "APPROVE" && decision.allowed_action === "MERGE" && decision.issue === state.issue && decision.pr === state.pr && decision.base_sha === state.base_sha && decision.head_sha === state.head_sha && decision.roadmap_id === spec.roadmap_id && decision.roadmap_item_id === spec.roadmap_item_id && !this.ledger.hasHead(state.head_sha!) && state.base_sha !== spec.expected_base_sha && this.bus.isAncestor(state.base_sha, spec.expected_base_sha) && pr?.author?.login === "cesarmanuel8102" && pr.baseRefName === "codex/own-capital-sustainable-return" && baseTip === spec.expected_base_sha && acceptedPrBase && pr.headRefName === spec.work_branch && pr.headRefOid === state.head_sha && pr.headRepository?.nameWithOwner === "cesarmanuel8102/AI_Vault" && pr.isCrossRepository === false && pr.isDraft === true && pr.state === "OPEN" && files.length > 0 && files.every((path: string) => pathAllowed(path, spec)) && this.bus.remoteBranchHead(spec.work_branch!) === state.head_sha;
    if (!exact) throw new Error("failed merge recovery identity invalid");
    const runId = this.bus.failedGovernedMerge(state.decision_id!);
    const updated = store.invalidateFailedMerge(state, runId);
    this.bindLifecycle(spec, updated);
    return updated;
  }

  // ---------------------------------------------------------------------
  // Legacy recovery entry points, preserved as thin plan-driven delegates.
  //
  // Historical callers and contract tests reference these names. Each
  // delegate routes through the authoritative snapshot -> plan -> invariant
  // pipeline; optionally pinning the expected domain move keeps the test
  // contract meaningful (the same state must plan to the same move).
  // ---------------------------------------------------------------------
  reconcileCloseoutState(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    // A pending initial-retry published candidate routes through its guarded
    // adoption before any generic planning.
    if (state.state === "BUILDING" && state.repair_cycles === 1 && state.builder_retry_reason === "BUILDER_FAILURE" && !state.pr && !state.head_sha) {
      return this.reconcileInitialRetryPublishedCandidate(spec, state, store);
    }
    // A blocked closeout under CI failure routes through the blocked CI entries
    // before any base rebinding (exact historical dispatch order).
    if (state.state === "BLOCKED" && state.last_error === "CI_FAILED") {
      return state.base_sha === spec.expected_base_sha ? this.reconcileBlockedCiChecks(spec, state, store) : this.reconcileBlockedCiBase(spec, state, store);
    }
    // A fully attested neutralization bridge is adopted only when ordinary
    // ancestry does not hold: it legitimately crosses a divergent historical
    // base, and ordinary recovery never pays the bridge-inspection cost.
    if (state.base_sha !== spec.expected_base_sha && ["CI_PENDING", "REVIEWING"].includes(state.state) && !state.reviewer_session && !state.decision_id && !safe(() => this.bus.isAncestor(state.base_sha, spec.expected_base_sha))) {
      const bridge = safe(() => this.inspectBridgeCandidate(spec, state));
      if (bridge) return this.applyPlan(spec, state, store, {move: "ADOPT_PUBLISHED_INITIAL_CANDIDATE", reason: "fully attested neutralization bridge adopted before ancestry fallback", lineage: undefined});
    }
    // Undecided post-build evidence at a stale base follows the invalidation-
    // then-recovery sequence through the blocked CI entry.
    if (state.base_sha !== spec.expected_base_sha && ["CI_PENDING", "REVIEWING"].includes(state.state) && !state.reviewer_session && !state.decision_id && state.builder_session) {
      return this.reconcileBlockedCiBase(spec, store.invalidatePostBuildBase(state), store);
    }
    return this.reconcilePinned(spec, state, store, undefined);
  }
  reconcilePreBuildBase(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    return this.reconcilePinned(spec, state, store, "REBIND_PRE_BUILD_BASE");
  }
  reconcileBlockedCiBase(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const plan = this.derivePlan(spec, state);
    return this.applyPlan(spec, state, store, plan);
  }
  reconcileBlockedCiChecks(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const plan = this.derivePlan(spec, state);
    if (plan.move !== "REOPEN_CI" && plan.move !== "REQUEST_DETERMINISTIC_REPAIR" && plan.move !== "EXHAUST_REPAIR") {
      throw new Error("blocked CI check reconciliation denied: plan=" + plan.move);
    }
    return this.applyPlan(spec, state, store, plan);
  }
  reconcileRepairBase(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    return this.reconcilePinned(spec, state, store, "SYNCHRONIZE_CANDIDATE");
  }
  reconcileBuilderFailureBase(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const plan = this.derivePlan(spec, state);
    if (plan.move === "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE") {
      return this.adoptVerifiedSynchronizedCandidateViaSynchronization(spec, state, store);
    }
    return this.reconcilePinned(spec, state, store, "SYNCHRONIZE_CANDIDATE");
  }
  reconcileInitialRetryPublishedCandidate(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    return this.reconcilePinned(spec, state, store, "ADOPT_PUBLISHED_INITIAL_CANDIDATE");
  }
  reconcileNegatedRiskEscalation(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    return this.reconcilePinned(spec, state, store, "RECOVER_NEGATED_RISK_ESCALATION");
  }
  reconcileExternallyMergedBuilderFailure(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const plan = this.derivePlan(spec, state);
    if (plan.move !== "ADOPT_EXTERNAL_MERGE") return undefined;
    // Adoption is optional evidence: hostile or drifted external state stays
    // unadopted (undefined), never a silent passthrough of the blocked state.
    return this.adoptExternalMerge(spec, state, store);
  }
  reconcileVerifiedSynchronizedBuilderCandidate(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    return this.reconcilePinned(spec, state, store, "ADOPT_VERIFIED_SYNCHRONIZED_CANDIDATE");
  }
  reconcileFalseBuilderProvenanceRepair(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    return this.reconcilePinned(spec, state, store, "REVERT_INVALIDATED_ADOPTION");
  }
  private reconcilePinned(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore, expectedMove: string | undefined) {
    const dry = this.dryRunReconciliation(spec, state);
    if (expectedMove !== undefined && dry.plan.move !== expectedMove) {
      throw new Error("reconciliation denied: state plans to " + dry.plan.move + " (" + dry.plan.reason + ")");
    }
    if (dry.invariants.violations.length) throw new Error("reconciliation invariants violated: " + dry.invariants.violations.join(", "));
    return this.applyPlan(spec, state, store, dry.plan);
  }
  private adoptVerifiedSynchronizedCandidateViaSynchronization(spec: ProxySpec, state: LifecycleRecord, store: LifecycleStore) {
    const synchronized = this.synchronizeForBuilderFailure(spec, state, store);
    const plan = this.dryRunReconciliation(spec, synchronized).plan;
    return this.applyPlan(spec, synchronized, store, plan);
  }

  inspectBridgeCandidate(spec: ProxySpec, state: LifecycleRecord): {nextBase: string; nextHead: string} | undefined {
    if (state.base_sha === spec.expected_base_sha) return undefined;
    if (!validBridgeAdoptionState(state)) return undefined;
    try {
      const pr = this.bus.prIdentity(state.pr!);
      const files = (pr.files ?? []).map((x: any) => String(x.path)).sort();
      const expectedAuthor = spec.repository.split("/", 1)[0];
      if (this.bus.repo !== spec.repository || !expectedAuthor || pr.author?.login !== expectedAuthor || pr.baseRefName !== INTEGRATION_BRANCH || pr.baseRefOid !== spec.expected_base_sha || pr.headRefName !== spec.work_branch || pr.headRepository?.nameWithOwner !== spec.repository || pr.isCrossRepository !== false || pr.isDraft !== true || pr.state !== "OPEN" || pr.mergeable !== "MERGEABLE") return undefined;
      const remote = this.bus.remoteBranchHead(spec.work_branch!);
      if (!remote || pr.headRefOid !== remote || remote !== state.head_sha) return undefined;
      if (files.length === 0) return undefined;
      if (!files.every((path: string) => pathAllowed(path, spec))) return undefined;
      const receipt = verifyBuilderProvenance(commitAccessFromBus(this.bus), state.head_sha!, spec.expected_base_sha, spec.front_id!, (older, newer) => this.bus.isAncestor(older, newer));
      if (receipt.status !== "VERIFIED") return undefined;
      return {nextBase: spec.expected_base_sha, nextHead: state.head_sha!};
    } catch {
      return undefined;
    }
  }
  private closeoutParentEvidence(spec:ProxySpec,merge:string){
    const state=this.activeState;
    if(!state||state.front_id!==spec.front_id||state.roadmap_item_id!==spec.roadmap_item_id||state.state!=="CLOSEOUT_PENDING"||state.head_sha!==merge||!state.completed_effects.includes(`merge:${merge}`)||!state.issue||!state.pr)throw new Error("closeout parent lifecycle evidence missing");
    if(state.merge_reconciliation){const r=state.merge_reconciliation;if(r.source!=="GITHUB_EXTERNALLY_MERGED_PR"||r.issue!==state.issue||r.pr!==state.pr||r.merge_commit_sha!==merge||r.original_base_sha===spec.expected_base_sha||r.original_state_head_sha===r.candidate_head_sha||r.candidate_head_sha===merge||r.reviewer_check!=="review"||state.base_sha!==spec.expected_base_sha||!state.builder_session)throw new Error("external merge closeout evidence mismatch");return {schema_version:1,parent_front_id:state.front_id,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,issue:state.issue,pr:state.pr,authorization_mode:"EXTERNAL_MERGE_RECONCILED",base_sha:r.original_base_sha,closeout_base_sha:merge,head_sha:r.candidate_head_sha,merge_commit:merge,builder_session:state.builder_session,reviewer_check:r.reviewer_check};}
    if(!state.builder_session||!state.reviewer_session||!state.decision_id)throw new Error("closeout parent lifecycle evidence missing");
    const decision=this.ledger.load(state.decision_id);
    const baseBound=decision.base_sha===state.base_sha||this.bus.isAncestor(decision.base_sha,state.base_sha);
    const common=decision.authorization_id===spec.authorization_id&&decision.repository===spec.repository&&decision.issue===state.issue&&decision.pr===state.pr&&state.base_sha===spec.expected_base_sha&&baseBound&&decision.roadmap_id===spec.roadmap_id&&decision.roadmap_item_id===spec.roadmap_item_id;
    const policyApproved=decision.policy_decision==="APPROVE"&&decision.allowed_action==="MERGE"&&this.ledger.hasHead(decision.head_sha);
    const ownerAuthorized="review_findings_count" in decision&&"review_consistent" in decision&&decision.risk==="CRITICAL"&&decision.deterministic_gate==="PASS"&&decision.codex_review==="PASS"&&decision.review_findings_count===0&&decision.review_consistent===true&&decision.policy_decision==="ESCALATE_TO_OWNER"&&decision.allowed_action==="NONE"&&this.bus.verifyOwnerAuthorizedMerge(state.issue,state.pr,decision.head_sha,decision.base_sha,merge)===merge;
    if(!common||!policyApproved&&!ownerAuthorized)throw new Error("closeout parent decision evidence mismatch");
    return {schema_version:1,parent_front_id:state.front_id,roadmap_id:spec.roadmap_id,roadmap_item_id:spec.roadmap_item_id,issue:state.issue,pr:state.pr,decision_id:decision.decision_id,authorization_mode:ownerAuthorized?"OWNER_CONSTITUTIONAL":"POLICY_APPROVED",base_sha:decision.base_sha,closeout_base_sha:merge,head_sha:decision.head_sha,merge_commit:merge,builder_session:state.builder_session,reviewer_session:state.reviewer_session};
  }
  async ensureCloseout(spec:ProxySpec,merge:string){this.boundary.assert("closeout_create",{issue:undefined});if(!spec.closeout)return this.coordinator.closeout(spec,merge);const c=spec.closeout,parentEvidence=safeJson(this.closeoutParentEvidence(spec,merge)),evidenceInstruction=`Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: ${parentEvidence}`;const closeout:ProxySpec={...spec,executor:c.executor,risk:c.risk,allowed_paths:c.allowed_paths,forbidden_paths:c.forbidden_paths,acceptance:[...c.acceptance,evidenceInstruction],test_commands:c.test_commands,objective:`${c.objective.trim()}\n\nPARENT_LIFECYCLE_EVIDENCE_JSON=${parentEvidence}`,work_branch:c.work_branch,deployment_mode:"NO_DEPLOY",install_target:undefined,front_id:c.front_id,test_profile:c.test_profile,max_executor_cycles:c.max_executor_cycles,closeout:undefined,closeout_only:true};const store=new LifecycleStore(join(this.root,"lifecycle"));const prior=store.load(closeout.front_id!);if(prior)this.reconcile(closeout,prior,store);const flow=new AutonomousFlow(store,this);let state=await flow.step(closeout);for(let i=0;i<20;i++){if(["CI_PENDING","BLOCKED","ESCALATED","TERMINAL_COMPLETED"].includes(state.state))break;state=await flow.step(closeout);}if(state.state==="BLOCKED"||state.state==="ESCALATED")throw new Error(`closeout ${state.state}: ${state.last_error??"unknown"}`);return state.state==="TERMINAL_COMPLETED"?"PASS":"PENDING";}
  discoverNext(item:string){this.coordinator.discoverNext(item);}
}
