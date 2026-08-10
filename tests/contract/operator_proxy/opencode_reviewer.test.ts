import test from "node:test";
import assert from "node:assert/strict";
import {mkdirSync,mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {OpenCodeReviewerBackend,parseJsonl,projectPanelEvidence} from "../../../scripts/operator_proxy/opencode_reviewer.js";
import {ReviewerBackendError} from "../../../scripts/operator_proxy/reviewer_backend.js";

const head="b".repeat(40),base="a".repeat(40);
function fixture(){const root=mkdtempSync(join(tmpdir(),"opencode-review-")),entry=join(root,"opencode");writeFileSync(entry,"");return {root,entry};}

test("uses node plus OpenCode JS entrypoint, full diff retained, and no API/GitHub token",()=>{
  const f=fixture(),old={node:process.env.OPERATOR_PROXY_NODE_PATH,entry:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT,api:process.env.OPENAI_API_KEY};process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;process.env.OPENAI_API_KEY="must-not-propagate";
  const calls:{file:string;args:string[];options:any;prompt?:string}[]=[];let statuses=0;const safeDiff=`diff --git a/a b/a\n+${"safe".repeat(100)}`;
  const runner=(file:string,args:string[],options:any)=>{const promptIndex=args.indexOf("--file"),prompt=promptIndex>=0?readFileSync(args[promptIndex+1],"utf8"):undefined;calls.push({file,args,options,prompt});if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status")){statuses++;return "";}if(args.includes("diff"))return safeDiff;if(file===process.execPath)return `${JSON.stringify({type:"text",sessionID:"provider-session",part:{type:"text",text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n`;return "";}
  try{const result=new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner).review({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"MEDIUM",changedFiles:["a"],builderSession:"builder"},"reviewer-session");assert.equal(result.output.verdict,"PASS");const call=calls.find(x=>x.file===process.execPath&&x.args[0]===f.entry)!;assert.ok(call);assert.equal(call.options.env.OPENAI_API_KEY,undefined);assert.equal(call.options.env.GH_TOKEN,undefined);assert.ok(call.args.every(arg=>arg.length<32767));assert.match(call.prompt!,/BEGIN_COMPLETE_DIFF/);assert.ok(call.prompt!.includes(safeDiff));assert.equal(call.prompt!.includes("[DIFF_TRUNCATED_BY_BOUNDED_PROMPT_BUDGET]"),false);assert.match(call.args[call.args.indexOf("--file")-1],/attached immutable diff/);assert.equal(call.args.at(-1),call.args[call.args.indexOf("--file")+1]);assert.equal(statuses,2);}
  finally{old.node===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=old.node;old.entry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=old.entry;old.api===undefined?delete process.env.OPENAI_API_KEY:process.env.OPENAI_API_KEY=old.api;}
});

test("blocks tool calls and post-review mutations",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  let status=0;const runner=(file:string,args:string[])=>{if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return ++status===1?"":" M changed";if(args.includes("diff"))return "safe";if(file===process.execPath)return `${JSON.stringify({type:"text",sessionID:"provider-session",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n`;return "";}
  try{assert.throws(()=>new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any).review({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"MEDIUM",changedFiles:["a"],builderSession:"builder"},"session"),/workspace mutated/);}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("accepts exactly one fenced JSON object but rejects surrounding prose",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;let mode="fenced";
  const runner=(file:string,args:string[])=>{if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return "safe";if(file===process.execPath){const json=JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]}),text=mode==="fenced"?`\`\`\`json\n${json}\n\`\`\``: `Result:\n${json}`;return `${JSON.stringify({type:"text",sessionID:`provider-${mode}`,part:{text}})}\n`;}return "";}
  try{const backend=new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any),input={repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW" as const,changedFiles:["a"],builderSession:"builder"};assert.equal(backend.review(input,"fenced").output.verdict,"PASS");mode="prose";assert.throws(()=>backend.review(input,"prose"),/reviewer JSON invalid/);}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("fetches an absent immutable review commit before creating the worktree",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  const available=new Set([base]),calls:string[][]=[];const runner=(_file:string,args:string[])=>{calls.push(args);if(args.includes("--format")&&args.includes("json"))return `${JSON.stringify({type:"text",sessionID:"provider-session",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n`;if(args.includes("cat-file")){const sha=args.at(-1)!.replace(/\^\{commit\}$/g,"");if(!available.has(sha))throw new Error("missing");return "";}if(args.includes("fetch")){available.add(args.at(-1)!);return "";}if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return "safe";return "";}
  try{assert.equal(new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any).review({repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW",changedFiles:["a"],builderSession:"builder"},"fetch").output.verdict,"PASS");const fetch=calls.find(args=>args.includes("fetch"))!;assert.deepEqual(fetch.slice(-5),["fetch","--no-tags","--no-write-fetch-head","origin",head]);assert.ok(calls.findIndex(args=>args.includes("fetch"))<calls.findIndex(args=>args.includes("worktree")));}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("fails closed before worktree creation when a review commit cannot be fetched",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;let worktree=false;
  const runner=(_file:string,args:string[])=>{if(args.includes("cat-file")||args.includes("fetch"))throw new Error("unavailable");if(args.includes("worktree")&&args.includes("add")){worktree=true;return "";}return "";}
  try{assert.throws(()=>new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any).review({repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW",changedFiles:["a"],builderSession:"builder"},"blocked"),/review commit unavailable/);assert.equal(worktree,false);}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("rejects an invalid review SHA before native Git or model execution",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;let calls=0;
  try{assert.throws(()=>new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",()=>{calls++;return "";}).review({repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:"not-a-sha",risk:"LOW",changedFiles:["a"],builderSession:"builder"},"invalid"),/review commit identity invalid/);assert.equal(calls,0);}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("validates captured read glob grep tool events and rejects list, escapes, and over-limit calls",()=>{
  const f=fixture(),workspace=join(f.root,"workspace"),file=join(workspace,"scripts","a.ts");mkdirSync(join(workspace,"scripts"),{recursive:true});writeFileSync(file,"safe\n");
  const final=JSON.stringify({type:"text",sessionID:"provider",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}});
  const event=(tool:string,input:object)=>JSON.stringify({type:"tool_use",sessionID:"provider",part:{tool,state:{status:"completed",input}}});
  assert.equal(parseJsonl(`${event("read",{filePath:file,offset:0,limit:1})}\n${final}\n`,head,workspace).output.verdict,"PASS");
  assert.equal(parseJsonl(`${event("glob",{pattern:"scripts/**/*.ts"})}\n${event("grep",{pattern:"safe",path:"scripts",include:"*.ts"})}\n${final}\n`,head,workspace).output.verdict,"PASS");
  assert.throws(()=>parseJsonl(`${event("list",{path:"scripts"})}\n${final}\n`,head,workspace),/tool call/);
  assert.throws(()=>parseJsonl(`${event("read",{filePath:join(f.root,"outside")})}\n${final}\n`,head,workspace),/outside workspace/);
  assert.throws(()=>parseJsonl(`${event("glob",{pattern:"../**/*"})}\n${final}\n`,head,workspace),/pattern invalid/);
  assert.throws(()=>parseJsonl(`${JSON.stringify({type:"tool_use",sessionID:"provider",part:{tool:"read",state:{status:"malicious",input:{filePath:file}}}})}\n${final}\n`,head,workspace),/tool evidence invalid/);
  assert.throws(()=>parseJsonl(`${Array.from({length:17},()=>event("glob",{pattern:"**/*.ts"})).join("\n")}\n${final}\n`,head,workspace),/limit exceeded/);
});

function setupReview(diff:string="safe"){
  const f=fixture();process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  const runner=(file:string,args:string[])=>{if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";};if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return diff;return "";},
    cleanup=(oldNode: string|undefined, oldEntry: string|undefined)=>{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;};
  return {f,runner,cleanup};
}
function modelLine(payload:object){return `${JSON.stringify({type:"text",sessionID:"provider",part:{text:JSON.stringify(payload)}})}\n`;}

function runReview(runner:any){return new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any).review({repository:"qualification",repositoryRoot:fixture().root,pr:1,baseSha:base,headSha:head,risk:"LOW",changedFiles:["a"],builderSession:"builder"},"session");}

test("normal PASS accepted",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.equal(runReview((file:string,args:string[])=>{if(file===process.execPath){const payload={verdict:"PASS",head_sha:head,summary:"ok",findings:[]};return modelLine(payload);}return runner(file,args);}).output.verdict,"PASS");}
  finally{cleanup(oldNode,oldEntry);}
});

test("CHANGES_REQUESTED accepted with findings",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{const result=runReview((file:string,args:string[])=>{if(file===process.execPath){return modelLine({verdict:"CHANGES_REQUESTED",head_sha:head,summary:"fix",findings:[{severity:"P2",title:"t",evidence:"e",required_correction:"c"}]});}return runner(file,args);});assert.equal(result.output.verdict,"CHANGES_REQUESTED");assert.equal(result.output.findings.length,1);}
  finally{cleanup(oldNode,oldEntry);}
});

test("wrong HEAD fails closed",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return modelLine({verdict:"PASS",head_sha:"c".repeat(40),summary:"ok",findings:[]});return runner(file,args);}),/reviewer output invalid/);}
  finally{cleanup(oldNode,oldEntry);}
});

test("truncation without text throws transient REVIEWER_OUTPUT_TRUNCATED",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath){return `${JSON.stringify({type:"reasoning",sessionID:"provider",part:{reasoning:"partial"}})}\n${JSON.stringify({type:"step_finish",sessionID:"provider",part:{reason:"length"}})}\n${JSON.stringify({info:{finish:"length"}})}\n`;}return runner(file,args);}),(err:any)=>err instanceof ReviewerBackendError&&err.message.includes("truncated")&&err.failureClass==="REVIEWER_OUTPUT_TRUNCATED"&&err.transient===true);}
  finally{cleanup(oldNode,oldEntry);}
});

const truncEvent=(type:string,runner:any)=>(file:string,args:string[])=>{if(file===process.execPath){return `${JSON.stringify({type:"text",sessionID:"provider",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n${JSON.stringify({type,sessionID:"provider",part:{reason:"length"}})}\n`;}return runner(file,args);};

test("detects step_finish reason length truncation",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview(truncEvent("step_finish",runner)),(err:any)=>err.failureClass==="REVIEWER_OUTPUT_TRUNCATED"&&err.transient===true);}
  finally{cleanup(oldNode,oldEntry);}
});

test("detects step-finish reason length truncation",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview(truncEvent("step-finish",runner)),(err:any)=>err.failureClass==="REVIEWER_OUTPUT_TRUNCATED"&&err.transient===true);}
  finally{cleanup(oldNode,oldEntry);}
});

test("detects info finish length truncation",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath){return `${JSON.stringify({type:"text",sessionID:"provider",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n${JSON.stringify({info:{finish:"length"}})}\n`;}return runner(file,args);}),(err:any)=>err.failureClass==="REVIEWER_OUTPUT_TRUNCATED"&&err.transient===true);}
  finally{cleanup(oldNode,oldEntry);}
});

test("truncation with partial text throws transient REVIEWER_OUTPUT_TRUNCATED",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath){return `${JSON.stringify({type:"text",sessionID:"provider",part:{text:'{"verdict":"PASS"'}})}\n${JSON.stringify({type:"step_finish",sessionID:"provider",part:{reason:"length"}})}\n`;}return runner(file,args);}),(err:any)=>err.failureClass==="REVIEWER_OUTPUT_TRUNCATED"&&err.transient===true);}
  finally{cleanup(oldNode,oldEntry);}
});

test("malformed JSON with normal finish is non-transient REVIEWER_INVALID_OUTPUT",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath){return `${JSON.stringify({type:"text",sessionID:"provider",part:{text:"not-json"}})}\n${JSON.stringify({type:"step_finish",sessionID:"provider",part:{reason:"stop"}})}\n`;}return runner(file,args);}),(err:any)=>err.failureClass==="REVIEWER_INVALID_OUTPUT"&&err.transient===false);}
  finally{cleanup(oldNode,oldEntry);}
});

test("two final JSON objects rejected as ambiguous",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  try{assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath){const p=modelLine({verdict:"PASS",head_sha:head,summary:"ok",findings:[]});return p+p;}return runner(file,args);}),/ambiguous/);}
  finally{cleanup(oldNode,oldEntry);}
});

test("projection emits required facts and excludes raw panel evidence",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  const panel={primary:{model:"m",session:"s",head:head,head_sha:"c".repeat(40),reviewed_head:head,verdict:"PASS",findings:[],finding_count:0,summary:"ok",source:{sha256:"abc123",runtime_reproduction_sha256:"rsha",codex_evidence_sha256:"esha",fresh_codex_session:"csess"},extra:"should not appear"},verifier:{model:"m2",session:"s2",classification:"CHANGES_REQUESTED",adjudication:"ACCEPT",findings:[{severity:"P2",title:"title",evidence:"evidence",required_correction:"c",observation:"note"}],summary:"fix"}};
  let prompt:string|undefined;
  const runner=(file:string,args:string[])=>{const promptIndex=args.indexOf("--file");if(promptIndex>=0)prompt=readFileSync(args[promptIndex+1],"utf8");if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";};if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return "safe";if(file===process.execPath)return modelLine({verdict:"PASS",head_sha:head,summary:"ok",findings:[]});return "";},
    cleanup=()=>{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;};
  try{new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner).review({repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW",changedFiles:["a"],builderSession:"builder",panelEvidence:panel},"session");assert.ok(prompt);assert.match(prompt!,/PANEL_EVIDENCE_SHA256/);assert.match(prompt!,/PANEL_EVIDENCE_PROJECTION/);const projectionMatch=prompt!.match(/PANEL_EVIDENCE_PROJECTION=([^\n]+)/);assert.ok(projectionMatch);const projection=JSON.parse(projectionMatch![1]);assert.equal(projection.projection_version,1);assert.equal(typeof projection.complete_evidence_sha256,"string");assert.ok(Array.isArray(projection.facts));const paths=projection.facts.map((fact:any)=>fact.path);    assert.ok(paths.includes("primary.head"));assert.ok(paths.includes("primary.head_sha"));assert.ok(paths.includes("primary.reviewed_head"));assert.ok(paths.includes("primary.model"));assert.ok(paths.includes("primary.session"));assert.ok(paths.includes("primary.verdict"));assert.ok(paths.includes("primary.finding_count"));assert.ok(paths.includes("verifier.classification"));assert.ok(paths.includes("verifier.adjudication"));assert.ok(paths.includes("verifier.model"));assert.ok(paths.includes("verifier.session"));assert.ok(paths.includes("verifier.findings[0].severity"));assert.ok(paths.includes("verifier.findings[0].evidence"));assert.ok(paths.includes("verifier.findings[0].observation"));assert.ok(paths.includes("primary.source.sha256"));assert.ok(paths.includes("primary.source.runtime_reproduction_sha256"));assert.ok(paths.includes("primary.source.codex_evidence_sha256"));assert.ok(paths.includes("primary.source.fresh_codex_session"));assert.equal(projection.facts.some((fact:any)=>fact.path.includes("extra")),false);assert.equal(prompt!.includes(JSON.stringify(panel)),false);}
  finally{cleanup();}
});

test("same evidence in different object insertion order yields identical projection and hash",()=>{
  const a={z:{head:head,verdict:"PASS"},y:{model:"m",session:"s"}};
  const b={y:{session:"s",model:"m"},z:{verdict:"PASS",head:head}};
  const pa=projectPanelEvidence(a);
  const pb=projectPanelEvidence(b);
  assert.equal(pa.sha256,pb.sha256);
  assert.equal(pa.projection,pb.projection);
});

test("cyclic evidence fails closed",()=>{
  const a:any={head:head,verdict:"PASS"};a.self=a;
  assert.throws(()=>projectPanelEvidence(a),/cycle/);
});

test("oversized unprojectable evidence fails closed",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  const panel={x:"x".repeat(20*1024)};
  const runner=(file:string,args:string[])=>{if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";};if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return "safe";return "";},
    cleanup=()=>{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;};
  try{assert.throws(()=>new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner).review({repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW",changedFiles:["a"],builderSession:"builder",panelEvidence:panel},"session"),/panel evidence/);}
  finally{cleanup();}
});

test("oversized prompt fails before model execution",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  let modelCalled=false;
  const hugeDiff="diff\n+"+"x".repeat(256*1024);
  const panel={primary:{head:head,verdict:"PASS",model:"m",session:"s"}};
  const runner=(file:string,args:string[])=>{if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";};if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return hugeDiff;if(file===process.execPath){modelCalled=true;return "";};return "";},
    cleanup=()=>{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;};
  try{assert.throws(()=>new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner).review({repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW",changedFiles:["a"],builderSession:"builder",panelEvidence:panel},"session"),/bounded budget/);assert.equal(modelCalled,false);}
  finally{cleanup();}
});

test("independent response bounds fail closed",()=>{
  const {f,runner,cleanup}=setupReview();const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  const good={verdict:"PASS",head_sha:head,summary:"ok",findings:[]};
  const line=(payload:object)=>modelLine(payload);
  try{
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,summary:""});return runner(file,args);}),/reviewer summary invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,summary:"x".repeat(201)});return runner(file,args);}),/reviewer summary invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,verdict:"CHANGES_REQUESTED",findings:[{severity:"P2",title:"x".repeat(61),evidence:"e",required_correction:"c"}]});return runner(file,args);}),/reviewer finding title invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,verdict:"CHANGES_REQUESTED",findings:[{severity:"P2",title:"",evidence:"e",required_correction:"c"}]});return runner(file,args);}),/reviewer finding title invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,verdict:"CHANGES_REQUESTED",findings:[{severity:"P2",title:"t",evidence:"x".repeat(201),required_correction:"c"}]});return runner(file,args);}),/reviewer finding evidence invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,verdict:"CHANGES_REQUESTED",findings:[{severity:"P2",title:"t",evidence:"",required_correction:"c"}]});return runner(file,args);}),/reviewer finding evidence invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,verdict:"CHANGES_REQUESTED",findings:[{severity:"P2",title:"t",evidence:"e",required_correction:"x".repeat(121)}]});return runner(file,args);}),/reviewer finding required_correction invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,verdict:"CHANGES_REQUESTED",findings:[{severity:"P2",title:"t",evidence:"e",required_correction:""}]});return runner(file,args);}),/reviewer finding required_correction invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,findings:[{severity:"P2",title:"t",evidence:"e",required_correction:"c"}]});return runner(file,args);}),/reviewer PASS with findings invalid/);
    assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return line({...good,verdict:"CHANGES_REQUESTED",findings:Array.from({length:7},(_,i)=>({severity:"P2",title:`f${i}`,evidence:"e",required_correction:"c"}))});return runner(file,args);}),/reviewer findings invalid/);
  }finally{cleanup(oldNode,oldEntry);}
});

test("unchanged separation still enforced with bounded projection",()=>{
  const {f,runner,cleanup}=setupReview("diff --git a/a b/a\n+change");const oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;
  let statusCount=0;const mutatedRunner=(file:string,args:string[])=>{if(args.includes("status")){statusCount++;if(statusCount===2){return " M changed";}}return runner(file,args);};
  try{assert.throws(()=>runReview((file:string,args:string[])=>{if(file===process.execPath)return modelLine({verdict:"PASS",head_sha:head,summary:"ok",findings:[]});return mutatedRunner(file,args);}),/workspace mutated/);}
  finally{cleanup(oldNode,oldEntry);}
});
