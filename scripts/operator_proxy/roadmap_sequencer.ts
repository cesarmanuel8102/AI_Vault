import {createHash} from "node:crypto";
import type {CloseoutMetadata,DeploymentMode,InstallTarget, LifecycleRecord, ProxySpec, Risk} from "./types.js";
import {AUTH, REPO} from "./policy_engine.js";
import {parseIssue,validateSpec} from "./spec_contract.js";
import {LifecycleStore} from "./lifecycle_store.js";

export const INTEGRATION_BRANCH="codex/own-capital-sustainable-return";
export const MANIFEST_PATH="docs/roadmap/BRAIN_101_MANIFEST.json";
export const ROADMAP_PATH="docs/roadmap/BRAIN_101_ROADMAP.md";
const sha256=(value:string)=>createHash("sha256").update(Buffer.from(value,"utf8")).digest("hex");

interface AutomationMetadata {
  front_id:string; objective:string; work_branch:string; executor:"agent_loop"|"codex_control_plane";
  risk:Risk; allowed_paths:string[]; forbidden_paths:string[]; acceptance:string[]; test_commands:string[];
  deployment_mode:DeploymentMode; install_target?:InstallTarget; test_profile?:"pilot"|"roadmap-doc"|"test-only"; max_executor_cycles?:number; closeout:CloseoutMetadata;
}
interface RoadmapItem {status:string; dependencies:string[]; automation?:AutomationMetadata}
interface Manifest {
  roadmap_id:string; roadmap_version:string; roadmap_path:string; roadmap_sha256:string; repository:string;
  integration_branch:string; approval_status:string; r0_status:string; human_final_authority:boolean;
  auto_merge:boolean; canonical_local_sync:boolean; live_trading_enabled:boolean; roadmap_items:Record<string,RoadmapItem>;
}
export interface SequencerSource {branchHead(branch:string):string; fileAt(path:string,ref:string):string; findOpenFront(front:string):number[]}
export interface SequencedItem {base_sha:string; manifest_sha256:string; spec:ProxySpec}
export interface ExecutableFrontBus {
  issueSnapshot(issue:number):{body:string};
  prIdentity(pr:number):{author?:{login?:string};baseRefName?:string;baseRefOid?:string;headRefName?:string;headRefOid?:string;headRepository?:{nameWithOwner?:string};isCrossRepository?:boolean;isDraft?:boolean;state?:string};
  isAncestor(older:string,newer:string):boolean;
}
export interface ExecutableFront {spec:ProxySpec;record?:LifecycleRecord;source:"ACTIVE_ITEM"|"NONTERMINAL_CLOSEOUT_CHILD"}

function exactUnique(values:string[],name:string){if(new Set(values).size!==values.length)throw new Error(`${name} contains duplicates`);}
function strings(value:unknown,name:string):string[]{if(!Array.isArray(value)||!value.every(x=>typeof x==="string")){throw new Error(`${name} invalid`);}exactUnique(value,name);return value;}
function closed(status:string|undefined){return typeof status==="string"&&status.startsWith("CLOSED_");}

export function sequenceRoadmap(source:SequencerSource):SequencedItem {
  const base=source.branchHead(INTEGRATION_BRANCH);
  if(!/^[0-9a-f]{40}$/.test(base))throw new Error("canonical branch head invalid");
  const manifestText=source.fileAt(MANIFEST_PATH,base); const roadmapText=source.fileAt(ROADMAP_PATH,base);
  const manifest=JSON.parse(manifestText) as Manifest;
  if(manifest.roadmap_id!=="BRAIN-101"||manifest.repository!==REPO||manifest.integration_branch!==INTEGRATION_BRANCH||manifest.approval_status!=="HUMAN_ADOPTED"||manifest.r0_status!=="CLOSED_HUMAN_ADOPTED"||manifest.human_final_authority!==true||manifest.auto_merge!==false||manifest.canonical_local_sync!==false||manifest.live_trading_enabled!==false||manifest.roadmap_path!==ROADMAP_PATH)throw new Error("canonical manifest governance invalid");
  if(manifest.roadmap_sha256!==sha256(roadmapText))throw new Error("canonical roadmap hash mismatch");
  const active=Object.entries(manifest.roadmap_items??{}).filter(([,item])=>item.status==="AUTHORIZED_ACTIVE");
  if(active.length!==1)throw new Error(`expected exactly one active roadmap item; found ${active.length}`);
  const [itemId,item]=active[0];if(!/^R\d+(?:\.\d+)?$/.test(itemId))throw new Error("active roadmap item id invalid");const dependencies=strings(item.dependencies,"dependencies").slice().sort();
  for(const dep of dependencies){if(!closed(manifest.roadmap_items[dep]?.status))throw new Error(`roadmap dependency not closed: ${dep}`);}
  const meta=item.automation; if(!meta)throw new Error("active roadmap item automation metadata missing");
  const allowed=strings(meta.allowed_paths,"allowed paths"); const forbidden=strings(meta.forbidden_paths,"forbidden paths");
  const acceptance=strings(meta.acceptance,"acceptance"); const tests=strings(meta.test_commands,"test commands");
  if(!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(meta.front_id)||!meta.objective.trim()||!["agent_loop","codex_control_plane"].includes(meta.executor)||!["LOW","MEDIUM","HIGH","CRITICAL"].includes(meta.risk)||!["NO_DEPLOY","INSTALL_ONLY","INSTALL_AND_RUNTIME_PILOT","DOCUMENTATION_CLOSEOUT"].includes(meta.deployment_mode))throw new Error("active roadmap automation metadata invalid");
  const installs=meta.deployment_mode==="INSTALL_ONLY"||meta.deployment_mode==="INSTALL_AND_RUNTIME_PILOT";
  if(installs!==!!meta.install_target||meta.install_target&&meta.install_target!=="agent_loop_worker")throw new Error("active roadmap install target invalid");
  if(source.findOpenFront(meta.front_id).length>1)throw new Error("duplicate governed fronts detected");
  if(meta.executor==="agent_loop"&&(!meta.test_profile||!Number.isInteger(meta.max_executor_cycles)||(meta.max_executor_cycles as number)<1||(meta.max_executor_cycles as number)>3))throw new Error("agent loop automation metadata invalid");
  const closeout=meta.closeout;if(!closeout||!["LOW","MEDIUM"].includes(closeout.risk))throw new Error("closeout metadata missing or invalid");strings(closeout.allowed_paths,"closeout allowed paths");strings(closeout.forbidden_paths,"closeout forbidden paths");strings(closeout.acceptance,"closeout acceptance");strings(closeout.test_commands,"closeout test commands");
  const manifestHash=sha256(manifestText);const spec:ProxySpec={schema_version:1,authorization_id:AUTH,repository:REPO,roadmap_id:manifest.roadmap_id,roadmap_version:manifest.roadmap_version,roadmap_item_id:itemId,expected_base_sha:base,executor:meta.executor,risk:meta.risk,allowed_paths:allowed,forbidden_paths:forbidden,acceptance,test_commands:tests,deployment_allowed:false,objective:meta.objective,work_branch:meta.work_branch,dependencies,deployment_mode:meta.deployment_mode,install_target:meta.install_target,front_id:meta.front_id,roadmap_sha256:manifest.roadmap_sha256,manifest_sha256:manifestHash,test_profile:meta.test_profile,max_executor_cycles:meta.max_executor_cycles,closeout};
  return {base_sha:base,manifest_sha256:manifestHash,spec:validateSpec(spec,true)};
}

/** Derives the only closeout child permitted by the immutable active item. */
export function closeoutSpec(parent:ProxySpec):ProxySpec {
  const closeout=parent.closeout;
  if(!closeout||!parent.front_id||!parent.work_branch)throw new Error("active item closeout metadata missing");
  return validateSpec({...parent,executor:closeout.executor,risk:closeout.risk,allowed_paths:[...closeout.allowed_paths],forbidden_paths:[...closeout.forbidden_paths],acceptance:[...closeout.acceptance],test_commands:[...closeout.test_commands],objective:closeout.objective,work_branch:closeout.work_branch,deployment_mode:"NO_DEPLOY",install_target:undefined,front_id:closeout.front_id,test_profile:closeout.test_profile,max_executor_cycles:closeout.max_executor_cycles,closeout:undefined,closeout_only:true},true);
}

const sameStrings=(left:readonly string[],right:readonly string[])=>left.length===right.length&&left.every((value,index)=>value===right[index]);
const nonterminal=(record:LifecycleRecord)=>record.state!=="TERMINAL_COMPLETED";

function assertCloseoutChild(bus:ExecutableFrontBus,parent:ProxySpec,child:ProxySpec,record:LifecycleRecord,parentRecord:LifecycleRecord){
  const issue=record.issue,prNumber=record.pr;
  if(record.front_id!==child.front_id||record.roadmap_item_id!==parent.roadmap_item_id||typeof issue!=="number"||!Number.isInteger(issue)||issue<=0||typeof prNumber!=="number"||!Number.isInteger(prNumber)||prNumber<=0)throw new Error("closeout lifecycle binding invalid");
  const parsed=parseIssue(bus.issueSnapshot(issue).body),historical=parsed.spec;
  const marker="\n\nPARENT_LIFECYCLE_EVIDENCE_JSON=",objective=historical.objective??"",markerIndex=objective.indexOf(marker),parentEvidence=markerIndex<0?undefined:objective.slice(markerIndex+marker.length);
  let evidence:any;try{evidence=parentEvidence?JSON.parse(parentEvidence):undefined;}catch{throw new Error("closeout parent evidence invalid");}
  const expectedInstruction=`Record this immutable parent lifecycle evidence exactly; do not infer, omit, or replace known values with null: ${parentEvidence}`;
  const parentExact=parentRecord.front_id===parent.front_id&&parentRecord.roadmap_item_id===parent.roadmap_item_id&&parentRecord.state==="CLOSEOUT_PENDING"&&!!parentRecord.issue&&!!parentRecord.pr&&!!parentRecord.head_sha&&!!parentRecord.decision_id&&parentRecord.completed_effects.includes(`merge:${parentRecord.head_sha}`)&&evidence?.schema_version===1&&evidence.parent_front_id===parentRecord.front_id&&evidence.roadmap_id===parent.roadmap_id&&evidence.roadmap_item_id===parent.roadmap_item_id&&evidence.issue===parentRecord.issue&&evidence.pr===parentRecord.pr&&evidence.decision_id===parentRecord.decision_id&&evidence.closeout_base_sha===parentRecord.head_sha&&evidence.merge_commit===parentRecord.head_sha&&evidence.builder_session===parentRecord.builder_session&&evidence.reviewer_session===parentRecord.reviewer_session;
  const exact=parsed.pr===prNumber&&historical.front_id===child.front_id&&historical.closeout_only===true&&historical.repository===parent.repository&&historical.authorization_id===parent.authorization_id&&historical.roadmap_id===parent.roadmap_id&&historical.roadmap_item_id===parent.roadmap_item_id&&historical.work_branch===child.work_branch&&historical.executor===child.executor&&historical.risk===child.risk&&historical.deployment_mode==="NO_DEPLOY"&&sameStrings(historical.allowed_paths,child.allowed_paths)&&sameStrings(historical.forbidden_paths,child.forbidden_paths)&&sameStrings(historical.acceptance.slice(0,child.acceptance.length),child.acceptance)&&historical.acceptance.length===child.acceptance.length+1&&historical.acceptance.at(-1)===expectedInstruction&&historical.objective===`${child.objective!.trim()}${marker}${parentEvidence}`&&sameStrings(historical.test_commands,child.test_commands)&&parentExact;
  if(!exact)throw new Error("closeout issue binding invalid");
  const pr=bus.prIdentity(prNumber),head=String(pr.headRefOid??""),ownerRepair=record.owner_payload_repair!==undefined;
  const branchHeadMatches=head===record.head_sha||ownerRepair&&typeof record.head_sha==="string"&&bus.isAncestor(record.head_sha,head);
  const baseMatches=pr.baseRefOid===record.base_sha||ownerRepair&&typeof pr.baseRefOid==="string"&&/^[0-9a-f]{40}$/.test(pr.baseRefOid);
  if(pr.author?.login!==parent.repository.split("/",1)[0]||pr.baseRefName!==INTEGRATION_BRANCH||!baseMatches||pr.headRefName!==child.work_branch||pr.headRepository?.nameWithOwner!==parent.repository||pr.isCrossRepository!==false||pr.isDraft!==true||pr.state!=="OPEN"||!branchHeadMatches)throw new Error("closeout PR binding invalid");
}

/** Resolves the lifecycle that is actually executable, rather than assuming the active parent is resumable. */
export function resolveExecutableFront(bus:ExecutableFrontBus,store:LifecycleStore,parent:ProxySpec,targetFrontId?:string):ExecutableFront {
  const child=closeoutSpec(parent),records=store.recordsForRoadmapItem(parent.roadmap_item_id),siblings=records.filter(record=>record.front_id!==parent.front_id&&nonterminal(record));
  if(targetFrontId!==undefined&&targetFrontId!==parent.front_id&&targetFrontId!==child.front_id)throw new Error("targeted front does not belong to active roadmap item");
  if(siblings.length>1)throw new Error("executable lifecycle ambiguity");
  const candidate=siblings[0];
  if(candidate){
    if(candidate.front_id!==child.front_id)throw new Error("nonterminal governed child is not the declared closeout front");
    const parentRecord=store.load(parent.front_id!);
    if(!parentRecord)throw new Error("closeout parent lifecycle missing");
    assertCloseoutChild(bus,parent,child,candidate,parentRecord);
    if(targetFrontId===parent.front_id)throw new Error("targeted parent bypasses nonterminal closeout child");
    store.recordExecutableChildPrecedence(parentRecord,candidate);
    return {spec:child,record:candidate,source:"NONTERMINAL_CLOSEOUT_CHILD"};
  }
  if(targetFrontId===child.front_id)throw new Error("targeted closeout lifecycle missing");
  return {spec:parent,record:store.load(parent.front_id!),source:"ACTIVE_ITEM"};
}
