import test from "node:test";
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {appendFileSync,mkdtempSync,readFileSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {ControllerSupersessionLedger} from "../../../scripts/operator_proxy/controller_supersession_ledger.js";
import type {ControllerSupersessionReceiptInputV1} from "../../../scripts/operator_proxy/types.js";

const sha40=(char:string)=>char.repeat(40);
const sha64=(char:string)=>char.repeat(64);
const ledger=()=>new ControllerSupersessionLedger(mkdtempSync(join(tmpdir(),"controller-supersession-ledger-")));
const canonicalize=(value:unknown):unknown=>Array.isArray(value)?value.map(canonicalize):value&&typeof value==="object"?Object.fromEntries(Object.entries(value as Record<string,unknown>).sort(([left],[right])=>left.localeCompare(right)).map(([key,child])=>[key,canonicalize(child)])):value;
const eventHash=(event:Record<string,unknown>)=>{const {event_sha256,...body}=event;return createHash("sha256").update(`${JSON.stringify(canonicalize(body))}\n`,"utf8").digest("hex");};
const receipt=(overrides:Record<string,unknown>={}):ControllerSupersessionReceiptInputV1=>({
  schema_version:1 as const,
  controller:"CODEX_GOVERNED_CONTROLLER" as const,
  supersession_key:sha64("a"),
  sequence:0,
  previous_event_sha256:null,
  repository:"cesarmanuel8102/AI_Vault",
  roadmap_item_id:"R9.9",
  canonical_base_sha:sha40("b"),
  manifest_sha256:sha64("c"),
  roadmap_sha256:sha64("d"),
  historical_attempt_sha256:sha64("e"),
  historical_base_sha:sha40("0"),
  front_id:"BRAIN-101-SYNTHETIC-FRONT-01",
  failed_head_sha:sha40("f"),
  grant_key:sha64("1"),
  consumed_event_sha256:sha64("2"),
  build_attempt_id:sha64("3"),
  functional_evidence_ref:sha40("4"),
  functional_evidence_path:"docs/roadmap/evidence/SYNTHETIC.md",
  functional_evidence_sha256:sha64("5"),
  functional_evidence_assertion_sha256:sha64("6"),
  hard_limits:{human_final_authority:true,auto_merge:false,canonical_local_sync:false,live_trading:false,real_money:false},
  persistent_agent_loop_enabled:false,
  created_utc:"2026-09-07T00:00:00.000Z",
  ...overrides
} as ControllerSupersessionReceiptInputV1);

test("appends one chained receipt and replays exact bytes idempotently",()=>{
  const store=ledger(),first=store.append(receipt());
  assert.equal(store.append(receipt()).event_sha256,first.event_sha256);
  const second=store.append(receipt({supersession_key:sha64("7"),sequence:1,previous_event_sha256:first.event_sha256,roadmap_item_id:"R9.10",front_id:"BRAIN-101-SYNTHETIC-FRONT-02"}));
  assert.equal(second.previous_event_sha256,first.event_sha256);
  assert.equal(store.validate().length,2);
  assert.match(readFileSync(join(store.root,"controller-supersessions.jsonl"),"utf8"),/CODEX_GOVERNED_CONTROLLER/);
});

test("rejects a conflicting duplicate key, duplicate sequence, and bad predecessor",()=>{
  const store=ledger();store.append(receipt());
  assert.throws(()=>store.append(receipt({canonical_base_sha:sha40("9")})),/supersession receipt/i);
  const path=join(store.root,"controller-supersessions.jsonl");
  const corrupt={...receipt({supersession_key:sha64("7"),functional_evidence_assertion_sha256:sha64("8")}),event_sha256:""};
  corrupt.event_sha256=eventHash(corrupt);
  appendFileSync(path,`${JSON.stringify(corrupt)}\n`);
  assert.throws(()=>store.validate(),/supersession receipt/i);
});

test("rejects a receipt without an exact historical base anchor",()=>{
  const store=ledger();
  assert.throws(()=>store.append(receipt({historical_base_sha:""})),/supersession receipt/i);
  assert.throws(()=>store.append(receipt({historical_base_sha:undefined})),/supersession receipt/i);
});

test("fails closed for a hash-valid record with a corrupted predecessor",()=>{
  const store=ledger();const first=store.append(receipt());
  const path=join(store.root,"controller-supersessions.jsonl");
  const stored=JSON.parse(readFileSync(path,"utf8")) as Record<string,unknown>;
  const corrupt={...stored,previous_event_sha256:first.event_sha256,event_sha256:""};
  corrupt.event_sha256=eventHash(corrupt);
  writeFileSync(path,`${JSON.stringify(corrupt)}\n`);
  assert.throws(()=>store.validate(),/supersession receipt/i);
});
