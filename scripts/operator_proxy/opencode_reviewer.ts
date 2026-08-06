import {execFileSync} from "node:child_process";
import {existsSync,mkdtempSync,readFileSync,realpathSync,rmSync,statSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {isAbsolute,join,relative,resolve} from "node:path";
import type {ReviewerBackend,ReviewerAttempt,ReviewerInput} from "./reviewer_backend.js";
import {ReviewerBackendError} from "./reviewer_backend.js";
import {normalizeReviewerOutput} from "./review_contract.js";
import {redactedError} from "./redaction.js";

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
function reviewPrompt(input:ReviewerInput,diff:string){return [
  "You are an independent read-only code reviewer. Analyze the complete immutable diff below.",
  `REPOSITORY=${input.repository}`,`PR=${input.pr}`,`BASE_SHA=${input.baseSha}`,`HEAD_SHA=${input.headSha}`,`RISK=${input.risk}`,
  `BUILDER_SESSION=${input.builderSession}`,`CHANGED_FILES=${JSON.stringify(input.changedFiles)}`,
  ...(input.panelEvidence?[`PANEL_EVIDENCE=${JSON.stringify(input.panelEvidence)}`,"Act as the independent arbiter. Evaluate the diff and the conflicting panel evidence; do not merely vote."]:[]),
  "Return exactly one bare JSON object with keys verdict, head_sha, summary, findings.",
  "verdict must be PASS only with zero findings; CHANGES_REQUESTED only for repairable P1/P2; BLOCKED for P0, authority uncertainty, or invalid evidence.",
  "Each finding must have severity, title, evidence, required_correction. Do not use Markdown. The immutable diff is embedded; inspection is optional. Only read, glob, and grep may inspect the detached workspace. Do not use list, mutate files, execute commands, create tasks, access networks, or access external directories.",
  "BEGIN_COMPLETE_DIFF",diff,"END_COMPLETE_DIFF",
].join("\n");}
const READ_ONLY_TOOLS=new Set(["read","glob","grep"]),MAX_READ_ONLY_TOOLS=16;
function insideWorkspace(workspace:string,value:string,existing:boolean){
  if(value.includes("\0")||/^\\\\[?.*|^\\\\\?\\|^\\\\\.\\|^[a-z]:/i.test(value)&&!isAbsolute(value))throw new ReviewerBackendError("reviewer path invalid","REVIEWER_WRITE_ATTEMPT");
  const root=realpathSync(workspace);let target:string;
  try{target=existing?realpathSync(value):resolve(root,value);}catch{throw new ReviewerBackendError("reviewer path outside workspace","REVIEWER_WRITE_ATTEMPT");}
  const rel=relative(root,target);
  if(rel===""||!rel.startsWith("..")&&!isAbsolute(rel))return;
  throw new ReviewerBackendError("reviewer path outside workspace","REVIEWER_WRITE_ATTEMPT");
}
function validateTool(part:any,workspace:string){
  const tool=String(part?.tool??""),state=part?.state,input=state?.input;
  if(!READ_ONLY_TOOLS.has(tool))throw new ReviewerBackendError("reviewer attempted a tool call","REVIEWER_WRITE_ATTEMPT");
  if(!state||typeof state.status!=="string"||!/[a-z]/i.test(state.status)||!input||typeof input!=="object"||Array.isArray(input))throw new ReviewerBackendError("reviewer tool evidence invalid","REVIEWER_INVALID_TRANSPORT");
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
  let tools=0;
  for(const line of stdout.split(/\r?\n/).filter(Boolean)){
    let event:any;try{event=JSON.parse(line);}catch{throw new ReviewerBackendError("OpenCode JSONL invalid","REVIEWER_INVALID_TRANSPORT");}
    const session=typeof event?.sessionID==="string"?event.sessionID:typeof event?.part?.sessionID==="string"?event.part.sessionID:"";
    if(session)sessions.add(session);
    if(event?.type==="text"&&typeof event?.part?.text==="string"&&event.part.text.trim())texts.push(event.part.text.trim());
    if(event?.type==="tool_use"){if(++tools>MAX_READ_ONLY_TOOLS)throw new ReviewerBackendError("reviewer tool call limit exceeded","REVIEWER_WRITE_ATTEMPT");validateTool(event.part,workspace);}
  }
  if(texts.length!==1||sessions.size!==1)throw new ReviewerBackendError("reviewer final response ambiguous","REVIEWER_INVALID_OUTPUT");
  const raw=texts[0],fenced=raw.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i),payload=fenced?fenced[1]:raw;
  let value:unknown;try{value=JSON.parse(payload);}catch{throw new ReviewerBackendError("reviewer JSON invalid","REVIEWER_INVALID_OUTPUT");}
  try{return {output:normalizeReviewerOutput(value,head),providerSession:[...sessions][0]};}catch(error){throw new ReviewerBackendError(redactedError(error),"REVIEWER_INVALID_OUTPUT");}
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
