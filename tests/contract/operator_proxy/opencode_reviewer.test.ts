import test from "node:test";
import assert from "node:assert/strict";
import {mkdirSync,mkdtempSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {OpenCodeReviewerBackend} from "../../../scripts/operator_proxy/opencode_reviewer.js";

const head="b".repeat(40),base="a".repeat(40);
function fixture(){const root=mkdtempSync(join(tmpdir(),"opencode-review-")),entry=join(root,"opencode");writeFileSync(entry,"");return {root,entry};}

test("uses node plus OpenCode JS entrypoint, lossless prompt, and no API/GitHub token",()=>{
  const f=fixture(),old={node:process.env.OPERATOR_PROXY_NODE_PATH,entry:process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT,api:process.env.OPENAI_API_KEY};process.env.OPERATOR_PROXY_NODE_PATH=process.execPath;process.env.OPERATOR_PROXY_OPENCODE_ENTRYPOINT=f.entry;process.env.OPENAI_API_KEY="must-not-propagate";
  const calls:{file:string;args:string[];options:any}[]=[];let statuses=0;
  const runner=(file:string,args:string[],options:any)=>{calls.push({file,args,options});if(args.includes("worktree")&&args.includes("add")){mkdirSync(args[args.indexOf("--detach")+1],{recursive:true});return "";}if(args.includes("rev-parse"))return head;if(args.includes("merge-base"))return base;if(args.includes("status")){statuses++;return "";}if(args.includes("diff"))return "diff --git a/a b/a\n+safe";if(file===process.execPath)return `${JSON.stringify({type:"text",sessionID:"provider-session",part:{type:"text",text:JSON.stringify({verdict:"PASS",head_sha:head,summary:"ok",findings:[]})}})}\n`;return "";};
  try{const result=new OpenCodeReviewerBackend("ollama-cloud/glm-5.2",runner).review({repository:"cesarmanuel8102/AI_Vault",repositoryRoot:f.root,pr:1,baseSha:base,headSha:head,risk:"MEDIUM",changedFiles:["a"],builderSession:"builder"},"reviewer-session");assert.equal(result.output.verdict,"PASS");const call=calls.find(x=>x.file===process.execPath&&x.args[0]===f.entry)!;assert.ok(call);assert.equal(call.options.env.OPENAI_API_KEY,undefined);assert.equal(call.options.env.GH_TOKEN,undefined);assert.match(String(call.args.at(-1)),/BEGIN_COMPLETE_DIFF[\s\S]*\+safe/);assert.equal(statuses,2);}
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
