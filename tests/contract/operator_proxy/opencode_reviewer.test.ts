import test from "node:test";
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdirSync,mkdtempSync,readFileSync,rmSync,symlinkSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname,join} from "node:path";
import {OpenCodeReviewerBackend,parseJsonl} from "../../../scripts/operator_proxy/opencode_reviewer.js";

const head="b".repeat(40),base="a".repeat(40);
function fixture(){const root=mkdtempSync(join(tmpdir(),"opencode-review-")),entry=join(root,"opencode");writeFileSync(entry,"");return {root,entry};}

test("uses node plus OpenCode JS entrypoint, lossless prompt, and no API/GitHub token",()=>{
  const f=fixture(),old={node:process.env.OPERATOR_PROXY_NODE_PATH,entry:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT,api:process.env.OPENAI_API_KEY};process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;process.env.OPENAI_API_KEY="must-not-propagate";
  const calls:{file:string;args:string[];options:any;prompt?:string}[]=[];let statuses=0;const largeDiff=`diff --git a/a b/a\n+${"safe".repeat(30000)}`;
  const runner=(file:string,args:string[],options:any)=>{const promptIndex=args.indexOf("--file"),prompt=promptIndex>=0?readFileSync(args[promptIndex+1],"utf8"):undefined;calls.push({file,args,options,prompt});if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status")){statuses++;return "";}if(args.includes("diff"))return largeDiff;if(file===process.execPath)return `${JSON.stringify({type:"text",sessionID:"provider-session",part:{type:"text",text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n`;return "";};
  try{const result=new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner).review({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"MEDIUM",changedFiles:["a"],builderSession:"builder"},"reviewer-session");assert.equal(result.output.verdict,"PASS");const call=calls.find(x=>x.file===process.execPath&&x.args[0]===f.entry)!;assert.ok(call);assert.equal(call.options.env.OPENAI_API_KEY,undefined);assert.equal(call.options.env.GH_TOKEN,undefined);assert.ok(call.args.every(arg=>arg.length<32767));assert.match(call.prompt!,/BEGIN_COMPLETE_DIFF/);assert.ok(call.prompt!.includes(largeDiff));assert.match(call.args[call.args.indexOf("--file")-1],/attached immutable diff/);assert.equal(call.args.at(-1),call.args[call.args.indexOf("--file")+1]);assert.equal(statuses,2);}
  finally{old.node===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=old.node;old.entry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=old.entry;old.api===undefined?delete process.env.OPENAI_API_KEY:process.env.OPENAI_API_KEY=old.api;}
});

test("blocks tool calls and post-review mutations",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  let status=0;const runner=(file:string,args:string[])=>{if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return ++status===1?"":" M changed";if(args.includes("diff"))return "safe";if(file===process.execPath)return `${JSON.stringify({type:"text",sessionID:"provider-session",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n`;return "";};
  try{assert.throws(()=>new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any).review({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"MEDIUM",changedFiles:["a"],builderSession:"builder"},"session"),/workspace mutated/);}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("accepts exactly one fenced JSON object but rejects surrounding prose",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;let mode="fenced";
  const runner=(file:string,args:string[])=>{if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return "safe";if(file===process.execPath){const json=JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]}),text=mode==="fenced"?`\`\`\`json\n${json}\n\`\`\``:`Result:\n${json}`;return `${JSON.stringify({type:"text",sessionID:`provider-${mode}`,part:{text}})}\n`;}return "";};
  try{const backend=new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any),input={repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW" as const,changedFiles:["a"],builderSession:"builder"};assert.equal(backend.review(input,"fenced").output.verdict,"PASS");mode="prose";assert.throws(()=>backend.review(input,"prose"),/reviewer JSON invalid/);}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("fetches an absent immutable review commit before creating the worktree",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;
  const available=new Set([base]),calls:string[][]=[];const runner=(_file:string,args:string[])=>{calls.push(args);if(args.includes("--format")&&args.includes("json"))return `${JSON.stringify({type:"text",sessionID:"provider-session",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n`;if(args.includes("cat-file")){const sha=args.at(-1)!.replace(/\^\{commit\}$/g,"");if(!available.has(sha))throw new Error("missing");return "";}if(args.includes("fetch")){available.add(args.at(-1)!);return "";}if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status"))return "";if(args.includes("diff"))return "safe";return "";};
  try{assert.equal(new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner as any).review({repository:"qualification",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"LOW",changedFiles:["a"],builderSession:"builder"},"fetch").output.verdict,"PASS");const fetch=calls.find(args=>args.includes("fetch"))!;assert.deepEqual(fetch.slice(-5),["fetch","--no-tags","--no-write-fetch-head","origin",head]);assert.ok(calls.findIndex(args=>args.includes("fetch"))<calls.findIndex(args=>args.includes("worktree")));}
  finally{oldNode===undefined?delete process.env.OPERATOR_PROXY_NODE_PATH:process.env.OPERATOR_PROXY_NODE_PATH=oldNode;oldEntry===undefined?delete process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=oldEntry;}
});

test("fails closed before worktree creation when a review commit cannot be fetched",()=>{
  const f=fixture(),oldNode=process.env.OPERATOR_PROXY_NODE_PATH,oldEntry=process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT;process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;let worktree=false;
  const runner=(_file:string,args:string[])=>{if(args.includes("cat-file")||args.includes("fetch"))throw new Error("unavailable");if(args.includes("worktree")&&args.includes("add")){worktree=true;return "";}return "";};
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
  assert.equal(parseJsonl(`${event("read",{filePath:"scripts/a.ts",offset:0,limit:1})}\n${final}\n`,head,workspace).output.verdict,"PASS");
  assert.equal(parseJsonl(`${event("glob",{pattern:"scripts/**/*.ts",path:"scripts"})}\n${event("grep",{pattern:"safe",path:"scripts",include:"*.ts"})}\n${final}\n`,head,workspace).output.verdict,"PASS");
  assert.equal(parseJsonl(`${event("glob",{pattern:"**/*.ts"})}\n${final}\n`,head,workspace).output.verdict,"PASS");
  assert.equal(parseJsonl(`${event("grep",{pattern:"safe",include:"*.ts"})}\n${final}\n`,head,workspace).output.verdict,"PASS");
  assert.throws(()=>parseJsonl(`${event("list",{path:"scripts"})}\n${final}\n`,head,workspace),/tool call/);
  assert.throws(()=>parseJsonl(`${event("read",{filePath:join(f.root,"outside")})}\n${final}\n`,head,workspace),/outside workspace/);
  assert.throws(()=>parseJsonl(`${event("read",{filePath:"../outside.ts"})}\n${final}\n`,head,workspace),/outside workspace/);
  assert.throws(()=>parseJsonl(`${event("read",{filePath:"scripts/\u0000a.ts"})}\n${final}\n`,head,workspace),/path invalid/);
  assert.throws(()=>parseJsonl(`${event("glob",{pattern:"../**/*"})}\n${final}\n`,head,workspace),/pattern invalid/);
  assert.throws(()=>parseJsonl(`${JSON.stringify({type:"tool_use",sessionID:"provider",part:{tool:"read",state:{status:"malicious",input:{filePath:file}}}})}\n${final}\n`,head,workspace),/tool evidence invalid/);
  assert.throws(()=>parseJsonl(`${Array.from({length:17},()=>event("glob",{pattern:"**/*.ts"})).join("\n")}\n${final}\n`,head,workspace),/limit exceeded/);
});

test("resolves relative reviewer reads against detached workspace even when process CWD differs",()=>{
  const workspace=mkdtempSync(join(tmpdir(),"opencode-relative-workspace-")),scripts=join(workspace,"scripts"),file=join(scripts,"a.ts");mkdirSync(scripts,{recursive:true});writeFileSync(file,"safe\n");
  const outside=mkdtempSync(join(tmpdir(),"opencode-process-cwd-"));
  const final=JSON.stringify({type:"text",sessionID:"provider",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}});
  const event=JSON.stringify({type:"tool_use",sessionID:"provider",part:{tool:"read",state:{status:"completed",input:{filePath:"scripts/a.ts",offset:0,limit:1}}}});
  const original=process.cwd();
  process.chdir(outside);
  try{assert.equal(parseJsonl(`${event}\n${final}\n`,head,workspace).output.verdict,"PASS");}
  finally{process.chdir(original);rmSync(workspace,{recursive:true,force:true});rmSync(outside,{recursive:true,force:true});}
});

test("rejects symlink targeting outside workspace when supported",()=>{
  const workspace=mkdtempSync(join(tmpdir(),"opencode-symlink-workspace-")),outside=mkdtempSync(join(tmpdir(),"opencode-symlink-outside-")),target=join(outside,"secret.ts");writeFileSync(target,"secret\n");
  const link=join(workspace,"leak.ts");let platformNote:string|undefined;
  function isPrivilegeError(e:any){
    if(e?.code==="EPERM"||e?.code==="EACCES")return true;
    const text=String(e?.stderr??e?.message??"").toLowerCase();
    return /privilege|administrator|operation not permitted|access is denied/.test(text);
  }
  try{
    if(process.platform==="win32"){
      try{execFileSync("cmd",["/c","mklink",link,target],{encoding:"utf8",windowsHide:true});}
      catch(first:any){
        if(isPrivilegeError(first))throw first;
        try{execFileSync("cmd",["/c","mklink","/J",link,dirname(target)],{encoding:"utf8",windowsHide:true});}
        catch(second:any){if(isPrivilegeError(second))throw second;else throw second;}
      }
    }else{symlinkSync(target,link);}
    const final=JSON.stringify({type:"text",sessionID:"provider",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}});
    const event=JSON.stringify({type:"tool_use",sessionID:"provider",part:{tool:"read",state:{status:"completed",input:{filePath:"leak.ts",offset:0,limit:1}}}});
    assert.throws(()=>parseJsonl(`${event}\n${final}\n`,head,workspace),/outside workspace/);
  }catch(e:any){
    if(isPrivilegeError(e)){
      platformNote=`${process.platform} symlink/junction creation requires elevated privileges; containment logic validated by traversal tests`;
    }else{throw e;}
  }finally{
    rmSync(workspace,{recursive:true,force:true});rmSync(outside,{recursive:true,force:true});
    if(platformNote)console.log(platformNote);
  }
});

test("rejects directory symlink or junction escaping workspace for glob and grep",()=>{
  const workspace=mkdtempSync(join(tmpdir(),"opencode-escape-workspace-")),outside=mkdtempSync(join(tmpdir(),"opencode-escape-outside-")),outsideFile=join(outside,"secret.ts");writeFileSync(outsideFile,"secret\n");
  const link=join(workspace,"escape-dir");let platformNote:string|undefined;
  function isPrivilegeError(e:any){
    if(e?.code==="EPERM"||e?.code==="EACCES")return true;
    const text=String(e?.stderr??e?.message??"").toLowerCase();
    return /privilege|administrator|operation not permitted|access is denied/.test(text);
  }
  try{
    if(process.platform==="win32"){
      try{execFileSync("cmd",["/c","mklink","/J",link,outside],{encoding:"utf8",windowsHide:true});}
      catch(e:any){if(isPrivilegeError(e))throw e;else throw e;}
    }else{symlinkSync(outside,link,"dir");}
    const final=JSON.stringify({type:"text",sessionID:"provider",part:{text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}});
    const globEvent=JSON.stringify({type:"tool_use",sessionID:"provider",part:{tool:"glob",state:{status:"completed",input:{path:"escape-dir",pattern:"**/*.ts"}}}});
    const grepEvent=JSON.stringify({type:"tool_use",sessionID:"provider",part:{tool:"grep",state:{status:"completed",input:{path:"escape-dir",pattern:"secret",include:"*.ts"}}}});
    assert.throws(()=>parseJsonl(`${globEvent}\n${final}\n`,head,workspace),/outside workspace/);
    assert.throws(()=>parseJsonl(`${grepEvent}\n${final}\n`,head,workspace),/outside workspace/);
  }catch(e:any){
    if(isPrivilegeError(e)){
      platformNote=`PLATFORM_NOT_APPLICABLE ${process.platform} directory junction/symlink creation requires elevated privileges; containment logic validated by traversal tests`;
    }else{throw e;}
  }finally{
    rmSync(workspace,{recursive:true,force:true});rmSync(outside,{recursive:true,force:true});
    if(platformNote)console.log(platformNote);
  }
});
