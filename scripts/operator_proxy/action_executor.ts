import type {NormalizedDecision} from "./types.js";
import {GitHubBus} from "./github_bus.js";
import {Ledger} from "./decision_ledger.js";

export function execute(bus:GitHubBus,ledger:Ledger,d:NormalizedDecision,dry:boolean){
  if(dry||d.policy_decision!=="APPROVE"||d.allowed_action!=="MERGE")return undefined;
  if(d.schema_version!==2||d.codex_review!=="PASS"||d.review_consistent!==true||d.review_findings_count!==0)throw new Error("merge denied by inconsistent reviewer decision");
  let merge:string;if(ledger.hasHead(d.head_sha)){ledger.ensureConsumed(d);merge=bus.verifyMerged(d.pr,d.head_sha,d.base_sha);}else {const current=bus.json(["pr","view",String(d.pr),"--json","baseRefOid,headRefOid,isDraft,state,mergeable"]);if(current.state==="MERGED")merge=bus.verifyMerged(d.pr,d.head_sha,d.base_sha);else {if(current.baseRefOid!==d.base_sha||current.headRefOid!==d.head_sha||current.state!=="OPEN"||current.isDraft!==true||current.mergeable!=="MERGEABLE")throw new Error("PR identity changed after decision");merge=bus.merge(d.pr,d.head_sha,d.base_sha,d.decision_id);}ledger.ensureConsumed(d);}return merge;
}
export function reconcileAuthorizationComment(bus:GitHubBus,d:NormalizedDecision){const marker=`decision_key=${d.decision_key}`;return bus.commentOnce("issue",d.issue,marker,`[OPERATOR-PROXY][AUTHORIZATION-CONSUMED]\n\n${marker}\nauthorization_id=${d.authorization_id}\ndecision_id=${d.decision_id}\nissue=${d.issue}\npr=${d.pr}\nbase_sha=${d.base_sha}\nhead_sha=${d.head_sha}\naction=MERGE\npolicy_sha256=${d.policy_sha256}`);}
