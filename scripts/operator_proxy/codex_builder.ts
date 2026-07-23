import {execFileSync} from "node:child_process";
export function runBuilder(codex:string,prompt:string,cwd:string,session:string){return execFileSync(codex,["exec","--full-auto","-C",cwd,prompt],{encoding:"utf8",env:{...process.env,OPERATOR_PROXY_SESSION:session},timeout:900000,windowsHide:true});}
