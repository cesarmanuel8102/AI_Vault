import {appendFileSync,existsSync,mkdirSync,readFileSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import type {ProxySpec} from "./types.js";
import type {LocalCoordinator} from "./production_effects.js";
import type {EffectAssertion} from "./external_effect_guard.js";
import {containsSensitiveData,redactSensitiveData,safeJson} from "./redaction.js";

type Kind="install"|"runtime-pilot";
const SHA40=/^[0-9a-f]{40}$/;const SHA256=/^[0-9a-f]{64}$/;
export const AGENT_LOOP_INSTALL_PROFILE={
  install_target:"agent_loop_worker" as const,
  installer_profile:"agent_loop_v157_transaction",
  artifact_path:"scripts/agent_loop/local_worker/agent_worker.py",
  transaction_marker:"V157_DEPLOY_RECOVERY_CONTRACT_PASS",
};

function installIdentity(spec:ProxySpec,sha:string,artifactSha256:string){
  if(!SHA40.test(sha)||!SHA256.test(artifactSha256)||!spec.front_id||spec.install_target!==AGENT_LOOP_INSTALL_PROFILE.install_target)throw new Error("coordinator install identity invalid");
  return {sha,repository:spec.repository,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,...AGENT_LOOP_INSTALL_PROFILE,artifact_sha256:artifactSha256};
}

export class RequestCoordinator implements LocalCoordinator {
  readonly requests:string;readonly receipts:string;
  constructor(readonly root:string,readonly assertEffect:EffectAssertion){this.requests=join(root,"requests");this.receipts=join(root,"receipts");mkdirSync(this.requests,{recursive:true});mkdirSync(this.receipts,{recursive:true});}
  private paths(kind:Kind,sha:string,front?:string){if(!SHA40.test(sha))throw new Error("coordinator SHA invalid");const suffix=kind==="install"?`${front}-${sha}`:sha;if(kind==="install"&&!front)throw new Error("coordinator install front missing");return {request:join(this.requests,`${kind}-${suffix}.json`),receipt:join(this.receipts,`${kind}-${suffix}.json`)};}
  installReceiptPresent(spec:ProxySpec,sha:string){if(spec.install_target!==AGENT_LOOP_INSTALL_PROFILE.install_target||!spec.front_id)throw new Error("coordinator install identity invalid");return existsSync(this.paths("install",sha,spec.front_id).receipt);}
  private installReceipt(spec:ProxySpec,sha:string,artifactSha256:string){
    const identity=installIdentity(spec,sha,artifactSha256),paths=this.paths("install",sha,spec.front_id);if(!existsSync(paths.receipt))return false;
    this.assertEffect("installation_receipt");const value=JSON.parse(readFileSync(paths.receipt,"utf8"));if(containsSensitiveData(value))throw new Error("coordinator receipt contains sensitive data");
    const expectedKeys=["artifact_path","artifact_sha256","config_sha256_after","config_sha256_before","front_id","install_target","installed_sha256","installer_profile","kind","repository","roadmap_item_id","schema_version","sha","source_sha256","status","task_state","transaction_marker"].sort();
    if(value.schema_version!==2||value.kind!=="install"||value.status!=="PASS"||JSON.stringify(Object.keys(value).sort())!==JSON.stringify(expectedKeys)||Object.entries(identity).some(([key,expected])=>value[key]!==expected)||value.source_sha256!==artifactSha256||value.installed_sha256!==artifactSha256||value.config_sha256_before!==value.config_sha256_after||!SHA256.test(value.config_sha256_before)||value.task_state!=="Disabled")throw new Error("coordinator receipt invalid");
    return true;
  }
  private installRequest(spec:ProxySpec,sha:string,artifactSha256:string){const identity=installIdentity(spec,sha,artifactSha256),path=this.paths("install",sha,spec.front_id).request;if(!existsSync(path)){this.assertEffect("installation_request");const value=redactSensitiveData({schema_version:2,kind:"install",...identity,created_utc:new Date().toISOString()});writeFileSync(path,`${JSON.stringify(value,null,2)}\n`,{flag:"wx"});}}
  private pilotReceipt(sha:string){const paths=this.paths("runtime-pilot",sha);if(!existsSync(paths.receipt))return false;this.assertEffect("pilot_receipt");const value=JSON.parse(readFileSync(paths.receipt,"utf8"));if(containsSensitiveData(value))throw new Error("coordinator receipt contains sensitive data");if(value.schema_version!==1||value.kind!=="runtime-pilot"||value.sha!==sha||value.status!=="PASS"||Object.keys(value).some(k=>!["schema_version","kind","sha","status"].includes(k)))throw new Error("coordinator receipt invalid");return true;}
  private pilotRequest(sha:string,spec:ProxySpec){const path=this.paths("runtime-pilot",sha).request;if(!existsSync(path)){this.assertEffect("pilot_request");const value=redactSensitiveData({schema_version:1,kind:"runtime-pilot",sha,front_id:spec.front_id,roadmap_item_id:spec.roadmap_item_id,created_utc:new Date().toISOString()});writeFileSync(path,`${JSON.stringify(value,null,2)}\n`,{flag:"wx"});}}
  install(spec:ProxySpec,merge:string,artifactSha256:string){if(this.installReceipt(spec,merge,artifactSha256))return "PASS" as const;this.installRequest(spec,merge,artifactSha256);return "LOCAL_PRIVILEGE_REQUIRED" as const;}
  pilot(spec:ProxySpec,merge:string){if(this.pilotReceipt(merge))return "PASS" as const;this.pilotRequest(merge,spec);return "PENDING" as const;}
  closeout(){return "PENDING" as const;}
  discoverNext(item:string){this.assertEffect("next_item_activate");appendFileSync(join(this.root,"events.jsonl"),`${safeJson({event:"next_authorized_item_discovery_requested",completed_item:item,created_utc:new Date().toISOString()})}\n`);}
}
