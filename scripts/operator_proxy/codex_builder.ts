import {execFileSync} from "node:child_process";
import {redactedError,redactString} from "./redaction.js";
export function runBuilder(codex:string,prompt:string,cwd:string,session:string){try{return redactString(execFileSync(codex,["exec","--full-auto","-C",cwd,prompt],{encoding:"utf8",env:{...process.env,OPERATOR_PROXY_SESSION:session},timeout:900000,windowsHide:true}));}catch(error){throw new Error(redactedError(error));}}
