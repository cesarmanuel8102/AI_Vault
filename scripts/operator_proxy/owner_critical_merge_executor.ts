import type {OwnerAuthorizedCriticalMerge} from "./types.js";
import {OwnerCriticalMergeReceiptLedger,type OwnerCriticalMergeReceiptEvent} from "./owner_critical_merge_receipt_ledger.js";

export interface OwnerCriticalMergeBoundary {authorizeOwnerCriticalMerge(context:{authorization:OwnerAuthorizedCriticalMerge},receipt:OwnerCriticalMergeReceiptEvent):unknown;assertOwnerCriticalMerge(capability:unknown):void}
export interface OwnerCriticalMergeBus {mergeOwnerAuthorizedCritical(authorization:OwnerAuthorizedCriticalMerge):string;verifyMerged(pr:number,head:string,base:string):string}
export interface OwnerCriticalMergeExecutionInput {authorization:OwnerAuthorizedCriticalMerge;receipts:OwnerCriticalMergeReceiptLedger;revalidate:(authorization:OwnerAuthorizedCriticalMerge)=>void;boundary:OwnerCriticalMergeBoundary;bus:OwnerCriticalMergeBus}
export interface CriticalMergeResult {merge_commit_sha:string;reconciled:boolean}

const sha40=(value:string)=>/^[0-9a-f]{40}$/.test(value);
const exact=(receipt:OwnerCriticalMergeReceiptEvent,authorization:OwnerAuthorizedCriticalMerge)=>receipt.critical_merge_key===authorization.critical_merge_key&&receipt.authorization_id===authorization.authorization_id&&receipt.repository===authorization.repository&&receipt.issue===authorization.issue&&receipt.front_id===authorization.front_id&&receipt.pr===authorization.pr&&receipt.base_branch===authorization.base_branch&&receipt.base_sha===authorization.base_sha&&receipt.head_branch===authorization.head_branch&&receipt.head_sha===authorization.head_sha&&receipt.policy_decision_id===authorization.policy_decision_id&&receipt.policy_decision_key===authorization.policy_decision_key;

function viewOrAppend(receipts:OwnerCriticalMergeReceiptLedger,authorization:OwnerAuthorizedCriticalMerge):OwnerCriticalMergeReceiptEvent {
  try{return receipts.deriveReceiptView(authorization.critical_merge_key);}catch(error){if(!String(error).includes("critical merge receipt missing"))throw error;return receipts.appendVerified(authorization);}
}

export function executeOwnerAuthorizedCriticalMerge(input:OwnerCriticalMergeExecutionInput):CriticalMergeResult {
  input.revalidate(input.authorization);
  let receipt=viewOrAppend(input.receipts,input.authorization);
  if(!exact(receipt,input.authorization))throw new Error("owner critical merge receipt identity invalid");
  if(receipt.phase==="MERGED_BOUND"){
    input.revalidate(input.authorization);
    if(!receipt.merge_commit_sha||input.bus.verifyMerged(input.authorization.pr,input.authorization.head_sha,input.authorization.base_sha)!==receipt.merge_commit_sha)throw new Error("owner critical merge reconciliation invalid");
    return {merge_commit_sha:receipt.merge_commit_sha,reconciled:true};
  }
  if(receipt.phase==="VERIFIED")receipt=input.receipts.consume(input.authorization.critical_merge_key);
  if(receipt.phase==="CONSUMED")receipt=input.receipts.markMergeDispatched(input.authorization.critical_merge_key);
  if(receipt.phase!=="MERGE_DISPATCHED"||!exact(receipt,input.authorization))throw new Error("owner critical merge dispatch receipt invalid");
  input.revalidate(input.authorization);
  const capability=input.boundary.authorizeOwnerCriticalMerge({authorization:input.authorization},receipt);
  input.boundary.assertOwnerCriticalMerge(capability);
  const merge_commit_sha=input.bus.mergeOwnerAuthorizedCritical(input.authorization);
  if(!sha40(merge_commit_sha)||input.bus.verifyMerged(input.authorization.pr,input.authorization.head_sha,input.authorization.base_sha)!==merge_commit_sha)throw new Error("owner critical merge not confirmed");
  const bound=input.receipts.bindMergedSha(input.authorization.critical_merge_key,merge_commit_sha);
  if(!exact(bound,input.authorization)||bound.merge_commit_sha!==merge_commit_sha)throw new Error("owner critical merge binding invalid");
  return {merge_commit_sha,reconciled:false};
}
