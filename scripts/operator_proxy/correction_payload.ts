import {createHash} from "node:crypto";
import type {CorrectionPayloadV1} from "./types.js";

const plain=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==="object"&&!Array.isArray(value)&&Object.getPrototypeOf(value)===Object.prototype;
const exactKeys=(value:Record<string,unknown>,keys:readonly string[])=>Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const canonicalString=(value:unknown)=>typeof value==="string"&&value.length>0&&value.trim()===value&&value.normalize("NFC")===value&&!/[\r\n\u0000]/.test(value);
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):plain(value)?Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])):value;

export function canonicalCorrectionPayloadBytes(payload:CorrectionPayloadV1):string {return `${JSON.stringify(canonical(payload))}\n`;}

export function parseCorrectionPayloadV1(value:unknown):{payload:CorrectionPayloadV1;canonical_json:string;sha256:string} {
  if(!plain(value)||!exactKeys(value,["schema_version","requirements","preserved_invariants","evidence_references"])&&!exactKeys(value,["schema_version","requirements","preserved_invariants"]))throw new Error("correction payload invalid");
  if(value.schema_version!==1||!Array.isArray(value.requirements)||value.requirements.length===0||!Array.isArray(value.preserved_invariants)||value.preserved_invariants.length===0)throw new Error("correction payload invalid");
  const requirements=value.requirements.map(requirement=>{
    if(!plain(requirement)||!exactKeys(requirement,["requirement_id","instruction"]))throw new Error("correction payload invalid");
    const requirement_id=requirement.requirement_id,instruction=requirement.instruction;
    if(typeof requirement_id!=="string"||!/^[a-z0-9][a-z0-9._-]{0,127}$/i.test(requirement_id)||typeof instruction!=="string"||!canonicalString(instruction)||instruction.length>4096)throw new Error("correction payload invalid");
    return {requirement_id,instruction};
  });
  if(new Set(requirements.map(requirement=>requirement.requirement_id)).size!==requirements.length)throw new Error("correction payload invalid");
  const preserved_invariants=value.preserved_invariants.map(invariant=>{
    if(typeof invariant!=="string"||!/^[A-Z][A-Z0-9_]{1,127}$/.test(invariant))throw new Error("correction payload invalid");
    return invariant;
  });
  if(new Set(preserved_invariants).size!==preserved_invariants.length)throw new Error("correction payload invalid");
  if(value.evidence_references!==undefined&&!Array.isArray(value.evidence_references))throw new Error("correction payload invalid");
  const evidence_references=value.evidence_references===undefined?undefined:value.evidence_references.map(reference=>{
    if(!plain(reference)||!exactKeys(reference,["kind","value"]))throw new Error("correction payload invalid");
    const kind=reference.kind,value=reference.value;
    if(!(["issue_comment","commit","ci_run"] as const).includes(kind as never)||typeof value!=="string"||!canonicalString(value)||value.length>512)throw new Error("correction payload invalid");
    return {kind:kind as "issue_comment"|"commit"|"ci_run",value};
  });
  const payload:CorrectionPayloadV1=evidence_references===undefined?{schema_version:1,requirements,preserved_invariants}:{schema_version:1,requirements,preserved_invariants,evidence_references};
  const canonical_json=canonicalCorrectionPayloadBytes(payload);
  return {payload,canonical_json,sha256:createHash("sha256").update(canonical_json,"utf8").digest("hex")};
}
