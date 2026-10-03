# IBKR PAPER — October 2 Pending Remediation Report

**Status:** READY_FOR_ADVERSARIAL_AUDIT
**Generated:** 2026-10-02T23:58:00Z
**Machine-readable companion:** `remediation_report.json`

---

## 1. Git identity

| Field | Value |
|---|---|
| Baseline branch | `codex/ibkr-paper-operational-approved` |
| Baseline SHA | `e5812193692f9599b9d0f9e8507869ba5d100840` |
| Remediation branch | `codex/ibkr-oct2-pending-remediation-v1` |
| Final code SHA | `58ca0691483940d55d4b25b993bc980680d520f4` |
| Evidence commit | `376744efb7febdda9a5674b246f632c0ce983c73` |
| Remote baseline SHA | `e5812193692f9599b9d0f9e8507869ba5d100840` ✅ equal |
| Force push used | **No** |
| Baseline history rewritten | **No** |

> **SHA bookkeeping:** "Final code SHA" is the last *functional* commit. The branch tip additionally
> carries evidence/doc commits. Verify the authoritative tip with
> `git ls-remote origin refs/heads/codex/ibkr-oct2-pending-remediation-v1`.
> Full suite and kernel verification were re-run at the tip: **1579 passed / 0 failed / 7 skipped**,
> kernel `verified=True` (71 files).

The baseline did **not** exist remotely before this work (`git ls-remote` returned no ref and
no object for `e581219`). It was preserved first, by a plain non-destructive push that created
a new ref, before any development began.

### Commits created

| SHA | Subject |
|---|---|
| `5754b150899f9e3b0030f010b668ea01c81c2e6c` | fix(ibkr): accept canonical nested combo leg contract identity |
| `58ca0691483940d55d4b25b993bc980680d520f4` | feat(ibkr): idle outside regular session instead of re-blocking |

### Files changed (7)

```
IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json
ibkr_paper_30d/autonomous_service.py
ibkr_paper_30d/ibkr_research_tools.py
ibkr_paper_30d/session_orchestration.py          (new)
tests/ibkr_paper_30d/test_autonomous_service.py
tests/ibkr_paper_30d/test_broker_feasibility_runtime.py
tests/ibkr_paper_30d/test_session_orchestration.py  (new)
```

No PowerShell file was modified.

---

## 2. Prior-branch forensics — the stated premise was refuted

The task stated that `602d975` and `1bffeb7` are *not* incorporated in `e581219`.
**Evidence contradicts this.** I did not cherry-pick either commit.

| Commit | Branch | Merge-base with e581219 | Finding |
|---|---|---|---|
| `602d975` | `codex/broker-combo-feasibility` | `d7a5f24` | Combo construction + all combo error codes **already present** in e581219 |
| `1bffeb7` | `codex/broker-feasibility-runtime` | `ba0b219` | What-if runtime primitives **already present** in e581219 |

- `git diff e581219:ibkr_research_tools.py 602d975:ibkr_research_tools.py` → **2 insertions, 25 deletions**, none touching combo logic. e581219 is a strict superset (it added later TIF handling).
- `git diff e581219:ibkr_research_tools.py 1bffeb7:ibkr_research_tools.py` → **3 insertions, 117 deletions**.
- `1bffeb7` is **not** an ancestor of `602d975`; they are independent branches.
- `git diff --stat e581219..602d975` → **125 files, 36,986 deletions**.

**Deliberately not incorporated:** nothing was taken from either branch. Both tips are rooted at
pre-Continuity-V3 merge-bases. Merging either would have deleted roughly 37k lines including
Continuity V3, successor epoch, provider lifecycle, and the October 2 provider/event-loop fixes.
Their useful content already exists in the baseline, so importing them would have been a regression.

---

## 3. Defect 1 — combo BROKER_FEASIBILITY

### Root cause

The combo leg validator (`_validate_flat_feasibility_args`) and the BAG builder
(`_feasibility_contract_from_args`) resolved leg contract identity **only from flat leg keys**
(`conId` / `con_id` / `contract_id`).

The repository's canonical contract identity — the shape `IBKRResearchToolbox._serialize_contract()`
emits *to the model* — is a **nested object**. When the model supplied authoritative,
broker-resolved contracts under `leg["contract"]`, the identity was invisible to validation and the
request was rejected at `stage=REQUEST_VALIDATION`, before any IBKR transmission.

This is a **contract-shape mismatch between the model-facing tool contract and the validator**,
not a missing feature.

### Forensic evidence (from `autonomous.sqlite3`)

30 matching failure rows. Representative invocation `autonomous-01a0ee85-fb8b-797d-87c9-1e1699e7893d`:

| Round | request_id | Legs supplied | Outcome |
|---|---|---|---|
| 2 | `whatif_iova_oct16_15_18_call_spread` | descriptors, no conId | correctly rejected |
| 3 | `retry_whatif_iova_oct16_15_18_with_contracts` | nested `conId` 913925915 / 926221865 | **incorrectly rejected** |
| 4 | `retry_whatif_iova_with_normalized_contracts` | nested `contract_id` | **incorrectly rejected** |

The model held valid, real, resolved IBKR conIds and was still blocked.

### Fix

Added `_combo_leg_contract_spec()` and `_combo_leg_contract_id()`, which resolve leg identity from
the canonical nested contract object **or** the flat leg. Both the validator and the BAG builder use
them. The repository's existing canonical representation is reused — **no parallel combo
representation was introduced**.

Additionally implemented required case **F**: combos whose legs share one contract identity are now
rejected with `BROKER_FEASIBILITY_COMBO_LEG_DUPLICATE` (previously unimplemented).

All pre-existing fail-closed codes are unchanged.

---

## 4. Defect 2 — post-market orchestration

### Root cause

The service loop had **no notion of a trading session**. Cycle scheduling was driven purely by
elapsed monotonic cadence and position presence, so a closed market produced an endless sequence of
full research cycles whose only possible outcome was a correct fail-closed market-data block.

**The market-data gate behaved correctly. No market-data validation was weakened.**

### Empirical evidence

State events after `2026-10-02T20:00Z` (16:00 ET regular close):

```
AUTONOMOUS_CYCLE_STARTED    : 48   last = 2026-10-02T23:55:39Z
AUTONOMOUS_CYCLE_COMPLETED  : 48   last = 2026-10-02T23:56:00Z
RECOVERY_GATE_FAILURE reason_codes: ["MARKET_DATA_GATE_BLOCK"]
Direct post-close probe      : INITIAL_REALTIME_QUOTE_TIMEOUT
```

Note for precision: alert-level deduplication already existed, so only 2 `RECOVERY_GATE_FAILURE`
alerts were emitted. The genuinely unbounded component was the **cycle loop and its state events**,
not the alert table.

### Fix

New module `ibkr_paper_30d/session_orchestration.py` — a pure, deterministic decision derived from
the repository's **existing** authoritative calendar abstraction
(`market_observation.classify_session` over IBKR `contractDetails.liquidHours` + `timeZoneId`).

| Condition | Action |
|---|---|
| `REGULAR` | `RUN_AUTONOMOUS_CYCLE` |
| non-regular + open position | `RUN_AUTONOMOUS_CYCLE` (continuity obligation survives) |
| non-regular + open order | `RUN_AUTONOMOUS_CYCLE` (continuity obligation survives) |
| non-regular + flat | `MARKET_CLOSED_IDLE` → sleep to next session |
| `UNKNOWN` calendar | `RUN_AUTONOMOUS_CYCLE` — idle requires positive proof |

Timezone, weekends, US market holidays, early closes and DST transitions are all derived from the
IBKR calendar. **No `if hour >= 16` logic was introduced.**

- `MARKET_CLOSED_IDLE` is appended **once per transition**, not per poll.
- The idle decision grants no authority and produces no receipt; a test asserts its payload contains
  none of `gate_status`, `receipt_sha256`, `order_authority`, `market_data_gate`, `authorized`, `passed`.
- `session_evidence_reader` defaults to `None`, so with no calendar evidence the service behaves
  **exactly as baseline** (pinned by `test_service_without_session_evidence_preserves_existing_behaviour`).

---

## 5. Testing

TDD was followed for both defects; every fix had a watched RED first.

| Stage | Result |
|---|---|
| Combo RED | 3 failed, 1 passed — nested contracts rejected with `BROKER_FEASIBILITY_COMBO_LEG_CONTRACT_REQUIRED` |
| Combo GREEN | 19 passed |
| Orchestration RED | collection error — module did not exist |
| Orchestration GREEN | 13 passed |
| Service RED | 5 failed, 1 passed — unexpected kwarg `session_evidence_reader` |
| Service GREEN | 41 passed |

### Full suite

```
python -m pytest tests/ibkr_paper_30d -q
1579 passed, 7 skipped, 0 failed   (1586 collected, 226s)
```

Baseline `e581219` measured independently in the read-only worktree
`C:/AI_VAULT_IBKR_OUTPUT_REPAIR`: **1563 collected**.
Delta **+23** (4 combo, 13 orchestration, 6 service). `1563 + 23 = 1586`. ✅

**Intermediate failure, disclosed in full:** a full-suite run taken *before* the kernel manifest was
regenerated produced **20 failures**, every one caused by `kernel_manifest` refusing an untracked
authority file (`ibkr_paper_30d/session_orchestration.py` enters the closure via
`autonomous_service.py`). That is the provenance control working as designed. It was resolved
**canonically** — by git-tracking the module and regenerating the manifest with the repository's own
mechanism. No gate was relaxed to make tests pass.

---

## 6. Integrity checks

| Check | Result |
|---|---|
| `verify_kernel_manifest` | `verified=True`, 71 files, sha `140091f7547061ffcbe6b2fe99c44fb2cd732f0c3eea146f2df4929cbb258570` |
| Runtime provenance | `PASS`, 81 approved files @ `58ca069` |
| PowerShell AST (3 canonical entrypoints) | 0 parse errors each |
| `git diff --check` | clean |
| `git status` (tracked) | clean |

---

## 7. PAPER validation

### Preconditions

| Field | Value |
|---|---|
| Host / port | `127.0.0.1` : **4002** |
| LIVE port 4001 | **CLOSED**, never referenced |
| Account | `DUM891854` (DU namespace ✅) |
| Identity hash | `cd82698d836ef78fd1a0c70b90ccebf690e43076ec2aa0aae4067c03faa4f5b0` |
| Positions / open orders / executions | **0 / 0 / 0** |
| Execution lock | `ACTIVE`, gen 29, `order_authority=false`, PID 48224 (baseline process; not touched) |

### Combo what-if — `BROKER_WHATIF_PASS`

Contracts resolved **dynamically from PAPER**. SPY is a contract-resolution fixture only — not a
trading universe, not a strategy.

| Field | Value |
|---|---|
| Legs | BUY conId `882135148` `SPY 261120C00770000` / SELL conId `927880746` `SPY 261120C00771000` |
| Leg shape | **canonical nested contract — the exact shape that failed on Oct 2** |
| `whatIf` / `transmit` | `true` / `true` |
| `LOCAL_VALIDATION_PASS` | **true** |
| `BROKER_WHATIF_PASS` | **true** |
| what-if calls transmitted to IBKR | **1** |
| `real_order_writes_attempted` | **0** |

Authoritative marker: IBKR returned a real regulatory `warningText` for the non-marketable limit,
which local validation cannot fabricate.

### Causal control against the baseline

The **identical payload and conIds** run against `e581219` in a separate worktree:

| Field | Baseline `e581219` | Remediation `58ca069` |
|---|---|---|
| `LOCAL_VALIDATION_PASS` | **false** | true |
| `BROKER_WHATIF_PASS` | **false** | **true** |
| what-if calls to IBKR | **0** | **1** |
| error | `BROKER_FEASIBILITY_COMBO_LEG_CONTRACT_REQUIRED` @ `REQUEST_VALIDATION` | none |
| real order writes | 0 | 0 |

This proves the fix is **causal**, and reproduces the October 2 defect against live IBKR.

### Harness guarantee

`ib.placeOrder` was replaced with a hard raise, making a real order write structurally impossible
during validation. `whatIfOrder` was wrapped only to count calls and assert `whatIf=True`; the real
IBKR call still executed, so the response is authoritative.

---

## 8. October 2 behaviour preserved

Full suite green plus unchanged source for every listed subsystem. These files were **not modified**:

`authoritative_broker_writer.py`, `continuity_watchdog.py`, `continuity_executor.py`,
`continuity_evaluator.py`, `continuity_models.py`, `continuity_store.py`, `continuity_schema.py`,
`continuity_binding.py`, `continuity_reporting.py`, `provider_lifecycle.py`,
`autonomous_research.py`, `execution_lock.py`, `day1_launch.py`, `broker_write_coordinator.py`.

Regressed green: per-thread event loops (writer + watchdog), Continuity V3 runtime, structured-output
schema compatibility, `ContinuityCondition.value` fix, StateActions schema, semantic self-repair loop
and bounded retries, provider durable diagnostics, execution-lock recovery, stale-provider recovery,
successor authority, immutable kernel verification, PAPER identity enforcement, order-authority
behaviour, watchdog health, broker reconciliation, Day1 launch.

**Provider self-repair is unchanged.**

---

## 9. Production state (not modified by this work)

| Field | Value |
|---|---|
| Scheduler task | `CodexIBKRMarketDataGate` |
| State | **Ready** (as found — *not* changed by me) |
| ApprovedHead | `e5812193692f9599b9d0f9e8507869ba5d100840` |
| Next run | **2026-10-05 09:35 local** |
| Last run / result | 2026-10-02 11:44:13 / `1` |
| SQLite hand-edited | No |
| Evidence deleted | No |
| PAPER armed by builder | No |
| Day 1 started by builder | No |
| New experiment started | No |

---

## 10. Unresolved risks

| ID | Sev | Risk |
|---|---|---|
| **R1** | HIGH | The canonical checkout is currently on `codex/ibkr-oct2-pending-remediation-v1` @ `58ca069` while the scheduler pins `ApprovedHead=e581219`. Monday's run would fail its approved-head check and **BLOCK** (fail-closed, not fail-open). This is an operational posture change caused by this work and needs an explicit Owner decision: promote + update ApprovedHead, or restore the baseline checkout. |
| **R2** | HIGH | The baseline service **PID 48224 is still running** and still executing post-close cycles (48 after 20:00Z, latest 23:56Z). The remediation is **not deployed**, so the cycle storm continues until the Owner acts. This work deliberately did not stop that process. |
| **R3** | MEDIUM | `BROKER_WHATIF_PASS` was obtained with the market closed, so IBKR returned DBL_MAX margin sentinels and zero commission. The IBKR round trip is proven; **combo margin/commission computation is not**. Re-validate during a live session before promotion. |
| **R4** | MEDIUM | `_what_if_evidence` reports success whenever IBKR returns any state object, including DBL_MAX "not computed" sentinels. **Pre-existing baseline behaviour**, untouched here, affects flat orders identically. Left unchanged deliberately (observational diagnostics stay observational). Flagged for auditor judgement. |
| **R5** | MEDIUM | `session_evidence_reader` is **unwired in production** — no launch path supplies `liquidHours`/`timeZoneId` yet. The orchestration fix is inert until that wiring is added and audited. Proven by tests only. |
| **R6** | LOW | PREMARKET is treated as non-trading. If premarket action is ever intended, the Owner must revisit; chosen because the market-data gate already requires `MarketSession.REGULAR`. |

---

## 11. Explicitly NOT proven

- Combo **margin/commission** computation by IBKR (market closed; DBL_MAX sentinels).
- End-to-end **production** behaviour of `MARKET_CLOSED_IDLE` — `session_evidence_reader` is not yet
  wired by any production launch path (R5). Proven by unit/service tests only.
- Live Monday session resumption in production (proven deterministically by tests, not live).
- Anything about the model's trading quality, strategy, or profitability. **No strategy, symbol,
  threshold, or universe was introduced.**
- That the still-running baseline process (PID 48224) is free of other latent defects; it was
  observed read-only and not interfered with.

---

## 12. Safety invariants upheld

PAPER-only port 4002 ✅ · LIVE 4001 never used ✅ · real order writes **0** ✅ ·
`whatIf=true` on every feasibility call ✅ · no gate bypassed ✅ · no fail-closed→fail-open ✅ ·
no SQLite hand-edit ✅ · no evidence deleted ✅ · no force push ✅ ·
no hard-coded symbols/strategy ✅ · no profitability threshold ✅ · no trading universe ✅
