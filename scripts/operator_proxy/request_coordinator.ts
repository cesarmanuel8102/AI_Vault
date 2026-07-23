import {appendFileSync,existsSync,mkdirSync,readFileSync,writeFileSync} from "node:fs";
import {join} from "node:path";
import type {ProxySpec} from "./types.js";
import type {LocalCoordinator} from "./production_effects.js";

type Kind="install"|"runtime-pilot";
export class RequestCoordinator implements LocalCoordinator {
  readonly requests:string;readonly receipts:string;
  constructor(readonly root:string){this.requests=join(root,"requests");this.receipts=join(root,"receipts");mkdirSync(this.requests,{recursive:true});mkdirSync(this.receipts,{recursive:true});}
  private paths(kind:Kind,sha:string){if(!/^[0-9a-f]{40}$/.test(sha))throw new Error("coordinator SHA invalid");return {request:join(this.requests,`${kind}-${sha}.json`),receipt:join(this.receipts,`${kind}-${sha}.json`)};}
  private receipt(kind:Kind,sha:string){const paths=this.paths(kind,sha);if(!existsSync(paths.receipt))return false;const value=JSON.parse(readFileSync(paths.receipt,"utf8"));if(value.schema_version!==1||value.kind!==kind||value.sha!==sha||value.status!=="PASS")throw new Error("coordinator receipt invalid");return true;}
  private request(kind:Kind,sha:string,spec?:ProxySpec){const path=this.paths(kind,sha).request;if(!existsSync(path))writeFileSync(path,`${JSON.stringify({schema_version:1,kind,sha,front_id:spec?.front_id,roadmap_item_id:spec?.roadmap_item_id,created_utc:new Date().toISOString()},null,2)}\n`,{flag:"wx"});}
  install(merge:string){if(this.receipt("install",merge))return "PASS" as const;this.request("install",merge);return "LOCAL_PRIVILEGE_REQUIRED" as const;}
  pilot(spec:ProxySpec,merge:string){if(this.receipt("runtime-pilot",merge))return "PASS" as const;this.request("runtime-pilot",merge,spec);return "PENDING" as const;}
  closeout(){return "PENDING" as const;}
  discoverNext(item:string){appendFileSync(join(this.root,"events.jsonl"),`${JSON.stringify({event:"next_authorized_item_discovery_requested",completed_item:item,created_utc:new Date().toISOString()})}\n`);}
}
