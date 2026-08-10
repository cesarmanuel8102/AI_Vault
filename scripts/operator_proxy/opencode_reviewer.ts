import {createHash} from "node:crypto";
import {execFileSync} from "node:child_process";
import {existsSync,mkdtempSync,readFileSync,realpathSync,rmSync,statSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {isAbsolute,join,relative,resolve} from "node:path";
import type {ReviewerBackend,ReviewerAttempt,ReviewerInput} from "./reviewer_backend.js";
import {ReviewerBackendError} from "./reviewer_backend.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {redactedError,redactSensitiveData,redactString} from "./redaction.js";

type NativeRunner=(file:string,args:string[],options:{cwd?:string;env?:NodeJS.ProcessEnv;timeout:number;maxBuffer:number})=>string;
const native:NativeRunner=(file,args,options)=>execFileSync(file,args,{...options,encoding:"utf8"});
const safeModel=/^ollama-cloud\/[a-z0-9][a-z0-9.:-]{2,127}$/;

export function resolveOpenCodeRuntime(env=process.env){
  const node=env.OPERATOR_PROXY_NODE_PATH??process.execPath;
  const entry=env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT??join(env.APPDATA??"","npm","node_modules","opencode-ai","bin","opencode");
  for(const [name,value] of [["node",node],["OpenCode entrypoint",entry]] as const){if(!isAbsolute(value)||!existsSync(value)||!statSync(value).isFile())throw new ReviewerBackendError(`${name} unavailable`,"REVIEWER_RUNTIME_UNAVAILABLE");}
  return {node:realpathSync(node),entrypoint:realpathSync(entry)};
}

function git(runner:NativeRunner,repo:string,args:string[]){return runner(process.env.GIT_PATH??"git",["-C",repo,...args],{timeout:60000,maxBuffer:64*1024*1024}).trim();}
function ensureReviewCommit(runner:NativeRunner,repo:string,sha:string){
  if(!/^[a-f0-9]{40}$/.test(sha))throw new ReviewerBackendError("review commit identity invalid","REVIEW_IDENTITY_MISMATCH");
  try{git(runner,repo,["cat-file","-e",`${sha}^{commit}`]);return;}catch{}
  try{git(runner,repo,["fetch","--no-tags","--no-write-fetch-head","origin",sha]);git(runner,repo,["cat-file","-e",`${sha}^{commit}`]);}
  catch{throw new ReviewerBackendError("review commit unavailable","REVIEW_IDENTITY_MISMATCH");}
}
function assertImmutable(runner:NativeRunner,repo:string,input:ReviewerInput){
  if(git(runner,repo,["rev-parse","HEAD"])!==input.headSha)throw new ReviewerBackendError("review HEAD mismatch","REVIEW_IDENTITY_MISMATCH");
  if(git(runner,repo,["merge-base",input.baseSha,input.headSha])!==input.baseSha)throw new ReviewerBackendError("review base mismatch","REVIEW_IDENTITY_MISMATCH");
  if(git(runner,repo,["status","--porcelain","--untracked-files=all"]))throw new ReviewerBackendError("review workspace mutated","REVIEWER_WRITE_ATTEMPT");
}
const MAX_SUMMARY=200;
const MAX_PROMPT_SIZE=256*1024;
const MAX_EVIDENCE_PROJECTION_SIZE=4*1024;
const MAX_EVIDENCE_UNPROJECTED_SIZE=16*1024;
const MAX_EVIDENCE_FACTS=256;
const MAX_EVIDENCE_FACT_VALUE_SIZE=1024;
const MAX_FINDING_TITLE=60;
const MAX_FINDING_EVIDENCE=200;
const MAX_FINDING_CORRECTION=120;
const MAX_FINDING_COUNT=6;

function hashString(value:string){return createHash("sha256").update(value,"utf8").digest("hex");}

export function canonicalizeEvidence(value:unknown):unknown{
  const stack=new Set<unknown>();
  function visit(v:unknown,path:string):unknown{
    if(v===null)return null;
    const t=typeof v;
    if(t==="string"||t==="number"||t==="boolean"){
      if(t==="number"&&(!Number.isFinite(v as number)))throw new ReviewerBackendError(`non-JSON number at ${path}`,"REVIEWER_INVALID_INPUT");
      return v;
    }
    if(Array.isArray(v)){
      if(stack.has(v))throw new ReviewerBackendError(`cycle at ${path}`,"REVIEWER_INVALID_INPUT");
      stack.add(v);
      try{return v.map((item,i)=>visit(item,`${path}[${i}]`));}finally{stack.delete(v);}
    }
    if(t==="object"){
      if(stack.has(v))throw new ReviewerBackendError(`cycle at ${path}`,"REVIEWER_INVALID_INPUT");
      stack.add(v);
      try{
        const entries=Object.entries(v as Record<string,unknown>).sort(([a],[b])=>a.localeCompare(b));
        const out:Record<string,unknown>={};
        for(const [k,val] of entries){
          const checked=redactString(k);
          if(checked!==k)throw new ReviewerBackendError("panel evidence key contains sensitive data","REVIEWER_INVALID_INPUT");
          out[k]=visit(val,path?`${path}.${k}`:k);
        }
        return out;
      }finally{stack.delete(v);}
    }
    throw new ReviewerBackendError(`non-JSON value at ${path}`,"REVIEWER_INVALID_INPUT");
  }
  return visit(value,"");
}

const RELEVANT_PATH_KEYS=new Set(["type","head","head_sha","reviewed_head","verdict","classification","adjudication","status","finding_count","severity","title","evidence","required_correction","observation","observations","summary"]);
const SAFE_SUFFIXES=["_sha256","_model","_session","_head","_head_sha"];
const EXACT_SAFE_KEYS=new Set(["sha256","model","session"]);
const RELEVANT_NAME_PARTS=/\b(classification|adjudication|observation|finding_count)\b/;
function isRelevantPath(path:string){
  const segments=path.split(/[\.\[\]]+/).filter(Boolean);
  return segments.some(k=>RELEVANT_PATH_KEYS.has(k)||EXACT_SAFE_KEYS.has(k)||SAFE_SUFFIXES.some(s=>k.endsWith(s))||RELEVANT_NAME_PARTS.test(k));
}

function collectRelevantFacts(canonical:unknown):{path:string;value:unknown}[]{
  const facts:{path:string;value:unknown}[]=[];
  function walk(v:unknown,path:string){
    if(v===null||typeof v!=="object"){
      if(isRelevantPath(path)){
        const serialized=JSON.stringify(v);
        if(Buffer.byteLength(serialized,"utf8")>MAX_EVIDENCE_FACT_VALUE_SIZE)throw new ReviewerBackendError("panel evidence fact value too large","REVIEWER_INVALID_INPUT");
        facts.push({path,value:v});
      }
      return;
    }
    if(Array.isArray(v)){
      v.forEach((item,i)=>walk(item,`${path}[${i}]`));
    }else{
      for(const [k,val] of Object.entries(v as Record<string,unknown>)){walk(val,path?`${path}.${k}`:k);}
    }
  }
  walk(canonical,"");
  facts.sort((a,b)=>a.path.localeCompare(b.path));
  return facts;
}

export function projectPanelEvidence(evidence:unknown):{projection:string;sha256:string}{
  const canonical=canonicalizeEvidence(evidence);
  const rawCanonical=JSON.stringify(canonical);
  if(Buffer.byteLength(rawCanonical,"utf8")>MAX_EVIDENCE_UNPROJECTED_SIZE)throw new ReviewerBackendError("panel evidence too large to project","REVIEWER_INVALID_INPUT");
  const sha256=hashString(rawCanonical);
  const redacted=redactSensitiveData(canonical);
  const facts=collectRelevantFacts(redacted);
  if(facts.length>MAX_EVIDENCE_FACTS)throw new ReviewerBackendError("panel evidence fact count overflow","REVIEWER_INVALID_INPUT");
  const projectionObj={projection_version:1,complete_evidence_sha256:sha256,facts};
  const projection=JSON.stringify(projectionObj);
  if(Buffer.byteLength(projection,"utf8")>MAX_EVIDENCE_PROJECTION_SIZE)throw new ReviewerBackendError("panel evidence projection overflow","REVIEWER_INVALID_INPUT");
  return {projection,sha256};
}
function reviewPrompt(input:ReviewerInput,diff:string){
  const staticLines:string[]=[
    "You are an independent read-only code reviewer. Return exactly one bare JSON object with keys verdict, head_sha, summary, findings.",
    "verdict must be exactly PASS only if findings=[]; CHANGES_REQUESTED only for repairable P1/P2; BLOCKED for P0, uncertainty, or invalid input.",
    "summary must be a concise plain-text sentence under 200 characters. No Markdown.",
    "findings is an array, maximum 6 entries. Each finding has severity (P0|P1|P2), title (max 60 chars), evidence (max 200 chars), required_correction (max 120 chars).",
    "Return exactly one bare JSON object. Do not wrap it in Markdown code fences, code blocks, or prose. The response must be only JSON.",
    `REPOSITORY=${input.repository}`,`PR=${input.pr}`,`BASE_SHA=${input.baseSha}`,`HEAD_SHA=${input.headSha}`,`RISK=${input.risk}`,
    `BUILDER_SESSION=${input.builderSession}`,`CHANGED_FILES=${JSON.stringify(input.changedFiles)}`,
  ];
  let projectionLine:string|undefined;
  if(input.panelEvidence!==undefined){
    const {projection,sha256}=projectPanelEvidence(input.panelEvidence);
    projectionLine=`PANEL_EVIDENCE_SHA256=${sha256}\nPANEL_EVIDENCE_PROJECTION=${projection}\nUse the projection as the only panel evidence; do not invent, restate, or quote it.`;
  }
  const staticPart=staticLines.join("\n");
  const parts=[staticPart];
  if(projectionLine)parts.push(projectionLine);
  parts.push("BEGIN_COMPLETE_DIFF",diff,"END_COMPLETE_DIFF");
  const prompt=parts.join("\n");
  if(Buffer.byteLength(prompt,"utf8")>MAX_PROMPT_SIZE)throw new ReviewerBackendError("review prompt exceeds bounded budget","REVIEWER_INVALID_INPUT");
  return prompt;
}
const READ_ONLY_TOOLS=new Set(["read","glob","grep"]),MAX_READ_ONLY_TOOLS=16;
function insideWorkspace(workspace:string,value:string,existing:boolean){
  if(value.includes("\0"))throw new ReviewerBackendError("reviewer path invalid","REVIEWER_WRITE_ATTEMPT");
  const root=realpathSync(workspace);let target:string;
  try{target=existing?realpathSync(value):resolve(root,value);}catch{throw new ReviewerBackendError("reviewer path outside workspace","REVIEWER_WRITE_ATTEMPT");}
  const rel=relative(root,target);
  if(rel===""||!rel.startsWith("..")&&!isAbsolute(rel))return;
  throw new ReviewerBackendError("reviewer path outside workspace","REVIEWER_WRITE_ATTEMPT");
}
function validateTool(part:any,workspace:string){
  const tool=String(part?.tool??""),state=part?.state,input=state?.input;
  if(!READ_ONLY_TOOLS.has(tool))throw new ReviewerBackendError("reviewer attempted a tool call","REVIEWER_WRITE_ATTEMPT");
  if(!state||typeof state.status!=="string"||!["completed","error","cancelled"].includes(state.status)||!input||typeof input!=="object"||Array.isArray(input))throw new ReviewerBackendError("reviewer tool evidence invalid","REVIEWER_INVALID_TRANSPORT");
  const keys=Object.keys(input).sort(),allowed=tool==="read"?["filePath","limit","offset"]:tool==="glob"?["path","pattern"]:["include","path","pattern"];
  if(keys.some(key=>!allowed.includes(key)))throw new ReviewerBackendError("reviewer tool arguments invalid","REVIEWER_WRITE_ATTEMPT");
  if(tool==="read"){
    if(typeof input.filePath!=="string"||input.filePath.length>4096||typeof input.offset!=="undefined"&&(!Number.isInteger(input.offset)||input.offset<0||input.offset>1_000_000)||typeof input.limit!=="undefined"&&(!Number.isInteger(input.limit)||input.limit<1||input.limit>100_000))throw new ReviewerBackendError("reviewer read arguments invalid","REVIEWER_WRITE_ATTEMPT");
    insideWorkspace(workspace,input.filePath,true);
  } else {
    if(typeof input.pattern!=="string"||input.pattern.length<1||input.pattern.length>4096||input.pattern.includes("\0")||/(^|[\\/])\.\.([\\/]|$)|^(?:[a-z]:|\\\\|\/)/i.test(input.pattern))throw new ReviewerBackendError("reviewer pattern invalid","REVIEWER_WRITE_ATTEMPT");
    if(input.path!==undefined){if(typeof input.path!=="string"||input.path.length>4096)throw new ReviewerBackendError("reviewer path invalid","REVIEWER_WRITE_ATTEMPT");insideWorkspace(workspace,input.path,false);}
    if(tool==="grep"&&input.include!==undefined&&(typeof input.include!=="string"||input.include.length<1||input.include.length>4096||/(^|[\\/])\.\.([\\/]|$)|^(?:[a-z]:|\\\\|\/)/i.test(input.include)))throw new ReviewerBackendError("reviewer include invalid","REVIEWER_WRITE_ATTEMPT");
  }
}
export function parseJsonl(stdout:string,head:string,workspace:string){
  const texts:string[]=[],sessions=new Set<string>();
  let tools=0,truncated=false;
  for(const line of stdout.split(/\r?\n/).filter(Boolean)){
    let event:any;try{event=JSON.parse(line);}catch{throw new ReviewerBackendError("OpenCode JSONL invalid","REVIEWER_INVALID_TRANSPORT");}
    const session=typeof event?.sessionID==="string"?event.sessionID:typeof event?.part?.sessionID==="string"?event.part.sessionID:"";
    if(session)sessions.add(session);
    if(event?.type==="text"&&typeof event?.part?.text==="string"&&event.part.text.trim())texts.push(event.part.text.trim());
    if(event?.type==="step_finish"&&event?.part?.reason==="length")truncated=true;
    if(event?.type==="step-finish"&&event?.part?.reason==="length")truncated=true;
    if(event?.info?.finish==="length")truncated=true;
    if(event?.type==="tool_use"){if(++tools>MAX_READ_ONLY_TOOLS)throw new ReviewerBackendError("reviewer tool call limit exceeded","REVIEWER_WRITE_ATTEMPT");validateTool(event.part,workspace);}
  }
  if(truncated)throw new ReviewerBackendError("OpenCode response truncated by length","REVIEWER_OUTPUT_TRUNCATED",true);
  if(texts.length!==1||sessions.size!==1)throw new ReviewerBackendError("reviewer final response ambiguous","REVIEWER_INVALID_OUTPUT");
  const raw=texts[0],fenced=raw.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i),payload=fenced?fenced[1]:raw;
  let value:unknown;try{value=JSON.parse(payload);}catch{throw new ReviewerBackendError("reviewer JSON invalid","REVIEWER_INVALID_OUTPUT");}
  enforceReviewerResponseBounds(value);
  try{return {output:normalizeReviewerOutput(value,head),providerSession:[...sessions][0]};}catch(error){throw new ReviewerBackendError(redactedError(error),"REVIEWER_INVALID_OUTPUT");}
}
function enforceReviewerResponseBounds(value:unknown){
  if(!value||typeof value!=="object")throw new ReviewerBackendError("reviewer output invalid","REVIEWER_INVALID_OUTPUT");
  const candidate=value as Record<string,unknown>;
  if(typeof candidate.summary!=="string"||candidate.summary.length===0||candidate.summary.length>MAX_SUMMARY)throw new ReviewerBackendError("reviewer summary invalid","REVIEWER_INVALID_OUTPUT");
  if(!Array.isArray(candidate.findings)||candidate.findings.length>MAX_FINDING_COUNT)throw new ReviewerBackendError("reviewer findings invalid","REVIEWER_INVALID_OUTPUT");
  for(const finding of candidate.findings){
    if(!finding||typeof finding!=="object"||Array.isArray(finding))throw new ReviewerBackendError("reviewer finding invalid","REVIEWER_INVALID_OUTPUT");
    const f=finding as Record<string,unknown>;
    if(typeof f.title!=="string"||f.title.length===0||f.title.length>MAX_FINDING_TITLE)throw new ReviewerBackendError("reviewer finding title invalid","REVIEWER_INVALID_OUTPUT");
    if(typeof f.evidence!=="string"||f.evidence.length===0||f.evidence.length>MAX_FINDING_EVIDENCE)throw new ReviewerBackendError("reviewer finding evidence invalid","REVIEWER_INVALID_OUTPUT");
    if(typeof f.required_correction!=="string"||f.required_correction.length===0||f.required_correction.length>MAX_FINDING_CORRECTION)throw new ReviewerBackendError("reviewer finding required_correction invalid","REVIEWER_INVALID_OUTPUT");
  }
  if(candidate.verdict==="PASS"&&candidate.findings.length>0)throw new ReviewerBackendError("reviewer PASS with findings invalid","REVIEWER_INVALID_OUTPUT");
}

export class OpenCodeReviewerBackend implements ReviewerBackend {
  constructor(readonly model:string,private readonly runner:NativeRunner=native){if(!safeModel.test(model))throw new Error("reviewer model invalid");}
  review(input:ReviewerInput,session:string):ReviewerAttempt{
    const startedUtc=new Date().toISOString(),runtime=resolveOpenCodeRuntime(),temp=mkdtempSync(join(tmpdir(),"operator-review-")),workspace=join(temp,"workspace");
    let worktreeAdded=false;
    try{
      if(!/^[a-f0-9]{40}$/.test(input.baseSha)||!/^[a-f0-9]{40}$/.test(input.headSha))throw new ReviewerBackendError("review commit identity invalid","REVIEW_IDENTITY_MISMATCH");
      ensureReviewCommit(this.runner,input.repositoryRoot,input.baseSha);
      ensureReviewCommit(this.runner,input.repositoryRoot,input.headSha);
      this.runner(process.env.GIT_PATH??"git",["-C",input.repositoryRoot,"worktree","add","--detach",workspace,input.headSha],{timeout:120000,maxBuffer:32*1024*1024});
      worktreeAdded=true;
      assertImmutable(this.runner,workspace,input);
      const diff=git(this.runner,workspace,["diff","--no-ext-diff","--binary",`${input.baseSha}...${input.headSha}`]);
      const configPath=join(temp,"opencode.json"),config={
        agent:{"brain-opencode-reviewer":{
          description:"Independent read-only repository reviewer.",mode:"primary",model:this.model,
          permission:{read:"allow",glob:"allow",grep:"allow",list:"deny",edit:"deny",write:"deny",create_file:"deny",bash:"deny",task:"deny",external_directory:"deny",webfetch:"deny",websearch:"deny",question:"deny",todowrite:"deny"},
        }},
      };
      writeFileSync(configPath,JSON.stringify(config));
      const promptPath=join(temp,"review-prompt.txt");writeFileSync(promptPath,reviewPrompt(input,diff),"utf8");
      const env:NodeJS.ProcessEnv={...process.env,OPENCODE_CONFIG:configPath};delete env.OPENAI_API_KEY;delete env.GH_TOKEN;delete env.GITHUB_TOKEN;
      let stdout:string;
      try{stdout=this.runner(runtime.node,[runtime.entrypoint,"run","--dir",workspace,"--model",this.model,"--agent","brain-opencode-reviewer","--format","json","--title",session,"--thinking","false","Review the attached immutable diff and return the required JSON.","--file",promptPath],{cwd:workspace,env,timeout:900000,maxBuffer:64*1024*1024});}
      catch(error){throw new ReviewerBackendError(redactedError(error),"REVIEWER_TRANSPORT_FAILURE",true);}
      assertImmutable(this.runner,workspace,input);
      const parsed=parseJsonl(stdout,input.headSha,workspace);return {output:parsed.output,providerSession:parsed.providerSession,backend:"opencode_ollama",model:this.model,session,startedUtc,completedUtc:new Date().toISOString()};
    } finally {
      if(worktreeAdded)try{this.runner(process.env.GIT_PATH??"git",["-C",input.repositoryRoot,"worktree","remove","--force",workspace],{timeout:120000,maxBuffer:32*1024*1024});}catch{}
      if(temp.startsWith(tmpdir()))rmSync(temp,{recursive:true,force:true});
    }
  }
}
