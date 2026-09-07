import {createHash} from "node:crypto";
import type {FunctionalEvidenceAssertionV1,FunctionalEvidenceInputV1,HistoricalAttemptRefV1,LifecycleRecord,RebaselineHardLimitsInputV1,RebaselineHardLimitsV1} from "./types.js";

const sha1=/^[0-9a-f]{40}$/;
const sha256=/^[0-9a-f]{64}$/;

function canonicalJson(value: Record<string,unknown>): string {
  return JSON.stringify(Object.fromEntries(Object.entries(value).sort(([left],[right])=>left.localeCompare(right))));
}

function canonicalSha256(value: Record<string,unknown>): string {
  return createHash("sha256").update(Buffer.from(canonicalJson(value),"utf8")).digest("hex");
}

function normalizeHardLimits(value: RebaselineHardLimitsInputV1): RebaselineHardLimitsV1 {
  if (value.human_final_authority!==true || value.auto_merge!==false || value.canonical_local_sync!==false || value.live_trading!==false || value.real_money!==false) throw new Error("functional evidence hard limits invalid");
  return {human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading:false,real_money:false};
}

export function projectHistoricalAttempt(record: LifecycleRecord): HistoricalAttemptRefV1 {
  const repair=record.owner_payload_repair,issue=record.issue,pr=record.pr,failedHead=record.head_sha;
  if (
    record.state==="TERMINAL_COMPLETED" || record.repair_cycles!==2 || !repair ||
    typeof issue!=="number" || !Number.isInteger(issue) || issue<=0 || typeof pr!=="number" || !Number.isInteger(pr) || pr<=0 ||
    !sha1.test(record.base_sha) || !sha1.test(failedHead??"") ||
    !sha256.test(repair.grant_key) || !sha256.test(repair.consumed_event_sha256) || !sha256.test(repair.build_attempt_id)
  ) throw new Error("historical Owner attempt invalid or not exhausted");
  if (issue===undefined || pr===undefined || failedHead===undefined) throw new Error("historical Owner attempt invalid or not exhausted");
  const core={
    schema_version:1 as const,
    front_id:record.front_id,
    roadmap_item_id:record.roadmap_item_id,
    lifecycle_state:record.state,
    issue,
    pr,
    base_sha:record.base_sha,
    failed_head_sha:failedHead,
    repair_cycles:2 as const,
    grant_key:repair.grant_key,
    consumed_event_sha256:repair.consumed_event_sha256,
    build_attempt_id:repair.build_attempt_id
  };
  return {...core,historical_sha256:canonicalSha256(core)};
}

export function verifyFunctionalEvidenceForRebaseline(input: FunctionalEvidenceInputV1): FunctionalEvidenceAssertionV1 {
  if (!/^[A-Z0-9][A-Z0-9._-]{2,127}$/.test(input.item_id) || !/^[A-Z0-9][A-Z0-9._-]{5,127}$/.test(input.task_id) || !sha1.test(input.canonical_ref) || !/^docs\/[A-Za-z0-9._/-]+$/.test(input.evidence_path) || input.evidence_path.includes("..")) throw new Error("functional evidence identity invalid");
  const hardLimits=normalizeHardLimits(input.hard_limits);
  if (!Array.isArray(input.required_markers) || input.required_markers.length===0 || new Set(input.required_markers).size!==input.required_markers.length || input.required_markers.some(marker=>typeof marker!=="string" || !marker.trim() || marker.includes("\n") || marker.includes("\r"))) throw new Error("functional evidence markers invalid");
  const evidence=Buffer.from(input.evidence_bytes),text=evidence.toString("utf8");
  if (!evidence.length) throw new Error("functional evidence empty");
  for (const marker of input.required_markers) if (!text.includes(marker)) throw new Error("functional evidence marker missing");
  const core={schema_version:1 as const,item_id:input.item_id,task_id:input.task_id,evidence_path:input.evidence_path,canonical_ref:input.canonical_ref,evidence_sha256:createHash("sha256").update(evidence).digest("hex"),required_markers:[...input.required_markers],hard_limits:hardLimits,status:"PASSED" as const};
  return {...core,assertion_sha256:canonicalSha256(core)};
}
