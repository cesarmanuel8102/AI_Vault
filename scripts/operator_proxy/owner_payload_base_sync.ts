import type {OwnerAuthorizedPayloadRepairGrant} from "./types.js";
import type {OwnerRepairEffectiveBaseBinding as LedgerOwnerRepairEffectiveBaseBinding} from "./owner_repair_effective_base.js";
import type {OwnerRepairRuntimeSupportEvent} from "./owner_repair_runtime_support.js";

export type OwnerRepairEffectiveBaseBinding=LedgerOwnerRepairEffectiveBaseBinding;
type OwnerPayloadBaseSyncBinding=Pick<OwnerRepairEffectiveBaseBinding,"grant_key"|"front_id"|"authorization_id"|"build_attempt_id"|"frozen_base_sha"|"effective_base_sha"|"failed_head_sha"|"build_dispatched_event_sha256"|"canonical_branch"|"installed_runtime_sha"|"event_sha256">;
type OwnerPayloadRuntimeSupport=Pick<OwnerRepairRuntimeSupportEvent,"grant_key"|"front_id"|"authorization_id"|"build_attempt_id"|"effective_base_sha"|"effective_base_binding_sha256"|"runtime_support_sha"|"event_sha256">;

const SHA40=/^[0-9a-f]{40}$/;
const SHA64=/^[0-9a-f]{64}$/;

export interface OwnerPayloadBaseSyncProvenance {
  frozen_base_sha:string;
  effective_base_sha:string;
  binding_event_sha256:string;
  synchronized_head_sha:string;
  runtime_support_sha?:string;
  runtime_support_event_sha256?:string;
}
export interface OwnerPayloadBaseSyncReceiptProvenance {frozen_base_sha:string;effective_base_sha:string;binding_event_sha256:string;runtime_support_sha?:string;runtime_support_event_sha256?:string}

export function ownerPayloadBaseSyncSubject(frontId:string):string{return `chore(control-plane): synchronize owner payload ${frontId} base`;}

export function assertOwnerRepairEffectiveBaseBinding(binding:OwnerRepairEffectiveBaseBinding,grant:OwnerAuthorizedPayloadRepairGrant,buildAttemptId:string,bindingSha?:string):void {
  const exact=binding.grant_key===grant.grant_key&&binding.front_id===grant.front_id&&binding.authorization_id===grant.authorization_id&&binding.build_attempt_id===buildAttemptId&&binding.frozen_base_sha===grant.canonical_base_sha&&binding.failed_head_sha===grant.failed_head_sha&&binding.canonical_branch==="codex/own-capital-sustainable-return"&&binding.installed_runtime_sha===binding.effective_base_sha&&SHA40.test(binding.frozen_base_sha)&&SHA40.test(binding.effective_base_sha)&&SHA40.test(binding.failed_head_sha)&&SHA64.test(binding.build_dispatched_event_sha256)&&SHA64.test(binding.event_sha256)&&(!bindingSha||binding.event_sha256===bindingSha);
  if(!exact)throw new Error("owner effective base binding invalid");
}

function validRuntimeSupport(binding:OwnerPayloadBaseSyncBinding,support:OwnerPayloadRuntimeSupport):boolean {
  return support.grant_key===binding.grant_key&&support.front_id===binding.front_id&&support.authorization_id===binding.authorization_id&&support.build_attempt_id===binding.build_attempt_id&&support.effective_base_sha===binding.effective_base_sha&&support.effective_base_binding_sha256===binding.event_sha256&&SHA40.test(support.runtime_support_sha)&&SHA64.test(support.event_sha256);
}

export function ownerPayloadBaseSyncReceipt(frontId:string,binding:OwnerPayloadBaseSyncBinding,support?:OwnerPayloadRuntimeSupport):string {
  if(support&&!validRuntimeSupport(binding,support))throw new Error("owner runtime support invalid");
  return [ownerPayloadBaseSyncSubject(frontId),"",`OWNER_GRANT_KEY=${binding.grant_key}`,`OWNER_AUTHORIZATION_ID=${binding.authorization_id}`,`OWNER_BUILD_ATTEMPT_ID=${binding.build_attempt_id}`,`OWNER_FROZEN_BASE_SHA=${binding.frozen_base_sha}`,`OWNER_EFFECTIVE_BASE_SHA=${binding.effective_base_sha}`,`OWNER_FAILED_HEAD_SHA=${binding.failed_head_sha}`,`OWNER_EFFECTIVE_BASE_BINDING_SHA256=${binding.event_sha256}`,`OWNER_BUILD_DISPATCHED_EVENT_SHA256=${binding.build_dispatched_event_sha256}`,...(support?[`OWNER_RUNTIME_SUPPORT_SHA=${support.runtime_support_sha}`,`OWNER_RUNTIME_SUPPORT_EVENT_SHA256=${support.event_sha256}`]:[])].join("\n");
}

export function parseOwnerPayloadBaseSyncReceipt(message:string,frontId:string):OwnerPayloadBaseSyncReceiptProvenance {
  const lines=message.replace(/\r\n/g,"\n").trimEnd().split("\n"),value=(name:string)=>{const matches=lines.filter(line=>line.startsWith(`${name}=`)).map(line=>line.slice(name.length+1));return matches.length===1?matches[0]:undefined;};
  if(lines[0]!==ownerPayloadBaseSyncSubject(frontId))throw new Error("owner base synchronization receipt invalid");
  const frozen_base_sha=value("OWNER_FROZEN_BASE_SHA"),effective_base_sha=value("OWNER_EFFECTIVE_BASE_SHA"),binding_event_sha256=value("OWNER_EFFECTIVE_BASE_BINDING_SHA256"),runtime_support_sha=value("OWNER_RUNTIME_SUPPORT_SHA"),runtime_support_event_sha256=value("OWNER_RUNTIME_SUPPORT_EVENT_SHA256");
  const supportPresent=runtime_support_sha!==undefined||runtime_support_event_sha256!==undefined;
  if(!frozen_base_sha||!effective_base_sha||!binding_event_sha256||!SHA40.test(frozen_base_sha)||!SHA40.test(effective_base_sha)||!SHA64.test(binding_event_sha256)||supportPresent&&(!runtime_support_sha||!runtime_support_event_sha256||!SHA40.test(runtime_support_sha)||!SHA64.test(runtime_support_event_sha256)))throw new Error("owner base synchronization receipt invalid");
  return {frozen_base_sha,effective_base_sha,binding_event_sha256,...(supportPresent?{runtime_support_sha:runtime_support_sha!,runtime_support_event_sha256:runtime_support_event_sha256!}:{})};
}

/** Verifies the immutable sync receipt and both required parent ancestries. */
export function verifyOwnerPayloadBaseSyncCommit(message:string,binding:OwnerPayloadBaseSyncBinding,synchronizedHead:string,parents:readonly string[],support?:OwnerPayloadRuntimeSupport):boolean {
  if(support&&!validRuntimeSupport(binding,support))return false;
  const parent=support?.runtime_support_sha??binding.effective_base_sha;
  if(!SHA40.test(synchronizedHead)||parents.length!==2||parents[0]!==binding.failed_head_sha||parents[1]!==parent)return false;
  return message.replace(/\r\n/g,"\n").trimEnd()===ownerPayloadBaseSyncReceipt(binding.front_id,binding,support);
}
