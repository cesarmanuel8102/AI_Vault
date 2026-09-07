import {createHash} from "node:crypto";
import type {HistoricalAttemptRefV1,LifecycleRecord} from "./types.js";

const sha1=/^[0-9a-f]{40}$/;
const sha256=/^[0-9a-f]{64}$/;

function canonicalJson(value: Record<string,unknown>): string {
  return JSON.stringify(Object.fromEntries(Object.entries(value).sort(([left],[right])=>left.localeCompare(right))));
}

function canonicalSha256(value: Record<string,unknown>): string {
  return createHash("sha256").update(Buffer.from(canonicalJson(value),"utf8")).digest("hex");
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
