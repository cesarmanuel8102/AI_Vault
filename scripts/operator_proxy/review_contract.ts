import type {ReviewerOutput} from "./types.js";
import {redactSensitiveData} from "./redaction.js";

export function normalizeReviewerOutput(value:unknown,expectedHead:string):ReviewerOutput {
  if(!value||typeof value!=="object")throw new Error("reviewer output invalid");
  const candidate=redactSensitiveData(value as ReviewerOutput);
  if(!["PASS","CHANGES_REQUESTED","BLOCKED"].includes(candidate.verdict)||candidate.head_sha!==expectedHead||typeof candidate.summary!=="string"||!Array.isArray(candidate.findings))throw new Error("reviewer output invalid");
  if(!candidate.findings.every(f=>f&&["P0","P1","P2"].includes(f.severity)&&typeof f.title==="string"&&typeof f.evidence==="string"&&typeof f.required_correction==="string"))throw new Error("reviewer findings invalid");
  if(candidate.verdict==="PASS"&&candidate.findings.length===0)return candidate;
  if(candidate.verdict==="CHANGES_REQUESTED"&&candidate.findings.length>0&&candidate.findings.every(f=>f.severity==="P1"||f.severity==="P2"))return candidate;
  return {...candidate,verdict:"BLOCKED"};
}

export function reviewIsConsistent(review:ReviewerOutput):boolean {
  return review.verdict==="PASS"?review.findings.length===0:review.verdict==="CHANGES_REQUESTED"?review.findings.length>0&&review.findings.every(f=>f.severity==="P1"||f.severity==="P2"):review.verdict==="BLOCKED";
}
