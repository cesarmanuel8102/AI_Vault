import type {ProxySpec} from "./types.js";
import {AUTH,REPO} from "./policy_engine.js";
import {containsSensitiveData} from "./redaction.js";

const validStrings=(value:unknown)=>Array.isArray(value)&&value.every(x=>typeof x==="string"&&x.length>0)&&new Set(value).size===value.length;
const invalidPath=(path:string)=>path.includes("\\")||path.startsWith("/")||/^[A-Za-z]:/.test(path)||path.split("/").includes("..")||path.includes("//");
const agentBranchPrefix=(profile:ProxySpec["test_profile"])=>profile==="pilot"?"agent/pilot-":profile==="roadmap-doc"?"agent/roadmap-doc-":profile==="test-only"?"agent/test-only-":"";
function validWorkBranch(spec:Pick<ProxySpec,"executor"|"test_profile"|"work_branch">){if(!spec.work_branch||spec.work_branch.includes("..")||spec.work_branch.includes("//"))return false;const prefix=spec.executor==="codex_control_plane"?"control-plane/":agentBranchPrefix(spec.test_profile);return !!prefix&&spec.work_branch.startsWith(prefix)&&/^[a-z0-9][a-z0-9._/-]{5,160}$/.test(spec.work_branch);}

export function validateSpec(spec:ProxySpec,requireAutomation=false):ProxySpec {
  if(containsSensitiveData(spec))throw new Error("operator proxy spec contains sensitive data");
  const arrays=[spec.allowed_paths,spec.forbidden_paths,spec.acceptance,spec.test_commands];
  const validArrays=arrays.every(validStrings);
  if(spec.schema_version!==1||spec.authorization_id!==AUTH||spec.repository!==REPO||spec.roadmap_id!=="BRAIN-101"||!/^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$/i.test(spec.roadmap_version)||!/^R\d+(?:\.\d+)?$/.test(spec.roadmap_item_id)||!/^[0-9a-f]{40}$/.test(spec.expected_base_sha)||!["agent_loop","codex_control_plane"].includes(spec.executor)||!["LOW","MEDIUM","HIGH","CRITICAL"].includes(spec.risk)||spec.deployment_allowed!==false||!validArrays)throw new Error("operator proxy spec invalid");
  if(spec.dependencies){if(!Array.isArray(spec.dependencies)||!spec.dependencies.every(x=>/^R\d+(?:\.\d+)?$/.test(x))||new Set(spec.dependencies).size!==spec.dependencies.length)throw new Error("operator proxy dependencies invalid");}
  if([...spec.allowed_paths,...spec.forbidden_paths].some(invalidPath))throw new Error("operator proxy path invalid");
  if(requireAutomation&&(!spec.front_id||!spec.work_branch||!spec.objective||!spec.deployment_mode))throw new Error("operator proxy automation metadata missing");
  if(spec.front_id&&!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(spec.front_id))throw new Error("operator proxy front id invalid");
  if(spec.work_branch&&!validWorkBranch(spec))throw new Error("operator proxy work branch invalid");
  if(spec.closeout){
    const c=spec.closeout;const groups=[c.allowed_paths,c.forbidden_paths,c.acceptance,c.test_commands];
    const badAgentLoop=c.executor==="agent_loop"&&(!c.test_profile||!Number.isInteger(c.max_executor_cycles)||(c.max_executor_cycles as number)<1||(c.max_executor_cycles as number)>3);
    if(!groups.every(validStrings)||c.allowed_paths.length===0||c.acceptance.length===0||c.test_commands.length===0||!c.front_id||!c.objective.trim()||!c.work_branch||!["agent_loop","codex_control_plane"].includes(c.executor)||!["LOW","MEDIUM"].includes(c.risk)||[...c.allowed_paths,...c.forbidden_paths].some(invalidPath)||!validWorkBranch(c)||!/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(c.front_id)||badAgentLoop)throw new Error("operator proxy closeout invalid");
  }
  return spec;
}

export function parseIssue(body:string):{spec:ProxySpec,pr?:number}{
  const marker="OPERATOR_PROXY_SPEC";const first=body.indexOf(marker);const second=body.indexOf(marker,first+marker.length);
  if(first<0||second<0)throw new Error("operator proxy spec missing");
  const spec=validateSpec(JSON.parse(body.slice(first+marker.length,second).trim()) as ProxySpec);
  const matches=[...body.matchAll(/OPERATOR_PROXY_PR:\s*(\d+)/g)];if(matches.length>1)throw new Error("multiple operator proxy PR bindings");
  return {spec,pr:matches.length?Number(matches[0][1]):undefined};
}

export function issueBody(spec:ProxySpec){validateSpec(spec,true);return `FRONT_ID: ${spec.front_id}\n\nOPERATOR_PROXY_SPEC\n${JSON.stringify(spec,null,2)}\nOPERATOR_PROXY_SPEC\n`;}

const requiredAgentForbidden=["memory/semantic/","memory/rollback","tmp_agent/state/","tmp_agent/brain_v9/trading/","financial_autonomy/","tmp_agent/brain_v9/core/session.py"];
function agentLoopSpec(spec:ProxySpec){validateSpec(spec,true);if(spec.executor!=="agent_loop"||!spec.test_profile||!spec.max_executor_cycles||spec.max_executor_cycles<1||spec.max_executor_cycles>3||!spec.roadmap_sha256||!spec.manifest_sha256||!/^[0-9a-f]{64}$/.test(spec.roadmap_sha256)||!/^[0-9a-f]{64}$/.test(spec.manifest_sha256))throw new Error("agent loop issue metadata missing");const allowed=new Set(spec.allowed_paths),trusted=spec.test_profile==="pilot"?allowed.size===2&&allowed.has("docs/agent_loop/pilot/PILOT_MARKER.md")&&allowed.has("docs/agent_loop/pilot/EXECUTOR_REPORT.json"):allowed.size>0&&allowed.size<=20&&[...allowed].every(path=>spec.test_profile==="roadmap-doc"?(path==="ROADMAP_STATUS.json"||path.startsWith("docs/roadmap/")):path.startsWith("tests/"));if(!trusted||!requiredAgentForbidden.every(path=>spec.forbidden_paths.includes(path)))throw new Error("agent loop profile boundary invalid");return {schema_version:1,front_id:spec.front_id,repo:spec.repository,owner:"cesarmanuel8102",base_branch:"codex/own-capital-sustainable-return",expected_base_sha:spec.expected_base_sha,work_branch:spec.work_branch,objective:spec.objective,test_profile:spec.test_profile,max_kimi_cycles:spec.max_executor_cycles,allowed_paths:spec.allowed_paths,forbidden_paths:spec.forbidden_paths,roadmap_id:spec.roadmap_id,roadmap_version:spec.roadmap_version,roadmap_sha256:spec.roadmap_sha256,roadmap_item_id:spec.roadmap_item_id,dependencies:spec.dependencies??[],human_final_authority:true};}
export function agentLoopIssueBody(spec:ProxySpec){const agent=agentLoopSpec(spec);return `${issueBody(spec)}\n<!-- AGENT_LOOP_SPEC\n${JSON.stringify(agent,null,2)}\nAGENT_LOOP_SPEC -->\n`;}
export function parseAgentLoopIssue(body:string,expected:ProxySpec){const matches=[...body.matchAll(/<!--\s*AGENT_LOOP_SPEC\s*(\{[\s\S]*?\})\s*AGENT_LOOP_SPEC\s*-->/g)];if(matches.length!==1)throw new Error("agent loop spec missing or duplicate");let actual;try{actual=JSON.parse(matches[0][1]);}catch{throw new Error("agent loop spec invalid");}if(JSON.stringify(actual)!==JSON.stringify(agentLoopSpec(expected)))throw new Error("agent loop spec mismatch");return actual;}
