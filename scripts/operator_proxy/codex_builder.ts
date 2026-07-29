import {execFileSync} from "node:child_process";
import {existsSync} from "node:fs";
import {isAbsolute} from "node:path";
import {redactedError,redactString} from "./redaction.js";
export function builderInvocation(codex:string,entrypoint=process.env.CODEX_ENTRYPOINT):{file:string;prefix:string[]}{if(!entrypoint)return {file:codex,prefix:[]};if(!isAbsolute(entrypoint)||!existsSync(entrypoint))throw new Error("Codex entrypoint invalid");return {file:codex,prefix:[entrypoint,"-c",'service_tier="fast"',"-c",'model_reasoning_effort="high"']};}
export function runBuilder(codex:string,prompt:string,cwd:string,session:string){const invocation=builderInvocation(codex);try{return redactString(execFileSync(invocation.file,[...invocation.prefix,"exec","--full-auto","-C",cwd,prompt],{encoding:"utf8",env:{...process.env,OPERATOR_PROXY_SESSION:session},timeout:900000,windowsHide:true}));}catch(error){throw new Error(redactedError(error));}}
