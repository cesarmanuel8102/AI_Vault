import {createHash} from "node:crypto";
import type {CloseoutMetadata,DeploymentMode,InstallTarget, ProxySpec, Risk} from "./types.js";
import {AUTH, REPO} from "./policy_engine.js";
import {validateSpec} from "./spec_contract.js";

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
