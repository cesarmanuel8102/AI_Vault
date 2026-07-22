import {execFileSync} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";

type NativeRunner=(file:string,args:string[],options:{encoding:"utf8";windowsHide:true;timeout:number;cwd?:string})=>string;
const nativeRunner:NativeRunner=(file,args,options)=>execFileSync(file,args,options);

export class GitHubBus {
  constructor(
    readonly gh="gh",
    readonly repo="cesarmanuel8102/AI_Vault",
    readonly git=process.env.GIT_PATH??"git",
    readonly repoDir=process.env.OPERATOR_PROXY_REPO??"",
    readonly run:NativeRunner=nativeRunner,
  ){}

  call(args:string[]){return this.run(this.gh,args,{encoding:"utf8",windowsHide:true,timeout:120000});}
  gitCall(args:string[],cwd=this.repoDir){return this.run(this.git,args,{encoding:"utf8",windowsHide:true,timeout:120000,cwd});}
  json(args:string[]){return JSON.parse(this.call([...args,"--repo",this.repo]));}
  queued(){return this.json(["issue","list","--state","open","--label","operator:queued","--json","number,title,body,labels"]);}
  fileAt(path:string,ref:string){const raw=this.call(["api",`repos/${this.repo}/contents/${path}?ref=${ref}`,"--jq",".content"]);return Buffer.from(raw.replace(/\s/g,""),"base64").toString("utf8");}
  repairCount(issue:number){const comments=this.json(["issue","view",String(issue),"--json","comments"]).comments??[];return comments.filter((c:any)=>String(c.body??"").includes("[OPERATOR-PROXY][REPAIR]")).length;}
  comment(issue:number,body:string){this.call(["issue","comment",String(issue),"--repo",this.repo,"--body",body]);}
  prComment(pr:number,body:string){this.call(["pr","comment",String(pr),"--repo",this.repo,"--body",body]);}
  label(kind:"issue"|"pr",n:number,add:string,remove:string[]=[]){for(const old of remove)this.call([kind,"edit",String(n),"--repo",this.repo,"--remove-label",old]);this.call([kind,"edit",String(n),"--repo",this.repo,"--add-label",add]);}

  merge(pr:number,head:string,base:string,decisionId:string){
    if(!this.repoDir)throw new Error("operator proxy repository required for merge");
    const meta=this.json(["pr","view",String(pr),"--json","baseRefName,baseRefOid,headRefName,headRefOid,isDraft,state,mergeable"]);
    if(meta.baseRefName!=="codex/own-capital-sustainable-return"||meta.baseRefOid!==base||meta.headRefOid!==head||meta.isDraft!==true||meta.state!=="OPEN"||meta.mergeable!=="MERGEABLE")throw new Error("PR identity changed before merge");
    const remote=this.gitCall(["ls-remote","origin",`refs/heads/${meta.baseRefName}`]).trim().split(/\s+/)[0];
    if(remote!==base)throw new Error("remote base moved before merge");
    this.gitCall(["fetch","--no-tags","origin",`+refs/heads/${meta.headRefName}:refs/remotes/origin/operator-head`]);
    if(this.gitCall(["rev-parse","refs/remotes/origin/operator-head"]).trim()!==head)throw new Error("remote head mismatch before merge");

    const parent=mkdtempSync(join(tmpdir(),"operator-proxy-merge-"));
    const worktree=join(parent,"worktree");
    let added=false,ready=false;
    try{
      this.gitCall(["worktree","add","--detach",worktree,base]);added=true;
      this.gitCall(["config","user.name","AI Vault Operator Proxy"],worktree);
      this.gitCall(["config","user.email","operator-proxy@users.noreply.github.com"],worktree);
      this.gitCall(["merge","--no-ff","-m",`Merge PR #${pr} via Operator Proxy decision ${decisionId}`,head],worktree);
      const parts=this.gitCall(["rev-list","--parents","-n","1","HEAD"],worktree).trim().split(/\s+/);
      if(parts.length!==3||parts[1]!==base||parts[2]!==head)throw new Error("local merge parents mismatch");
      this.call(["pr","ready",String(pr),"--repo",this.repo]);ready=true;
      try{this.gitCall(["push","origin",`HEAD:refs/heads/${meta.baseRefName}`],worktree);ready=false;}
      catch(error){this.call(["pr","ready",String(pr),"--undo","--repo",this.repo]);ready=false;throw error;}
      const merged=this.json(["pr","view",String(pr),"--json","state,mergeCommit"]);
      if(merged.state!=="MERGED"||!/^[0-9a-f]{40}$/.test(merged.mergeCommit?.oid??""))throw new Error("governed merge not confirmed");
      const parents=this.call(["api",`repos/${this.repo}/git/commits/${merged.mergeCommit.oid}`,"--jq",".parents[].sha"]).trim().split(/\s+/);
      if(parents.length!==2||parents[0]!==base||parents[1]!==head)throw new Error("governed merge parents mismatch");
    } finally {
      if(ready){try{this.call(["pr","ready",String(pr),"--undo","--repo",this.repo]);}catch{}}
      if(added){try{this.gitCall(["worktree","remove",worktree]);}catch{}}
      rmSync(parent,{recursive:true,force:true});
    }
  }
}
