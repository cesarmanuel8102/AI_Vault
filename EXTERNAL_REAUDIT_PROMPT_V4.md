# EXTERNAL RE-AUDIT PROMPT V4 — CODEX IBKR AUTONOMOUS PAPER TRADER

You are an external, independent, adversarial technical auditor.

Repository:
`cesarmanuel8102/AI_Vault`

Canonical branch:
`codex/ibkr-paper-auditor-gate-v2`

Do NOT trust any SHA written in documentation. Resolve the actual branch HEAD
yourself after a fresh clone and record it in your report.

The current development team expects the branch to include the V3 remediation
merge lineage, but that expectation is NOT evidence.

## Mission

Re-audit the complete Codex + Interactive Brokers autonomous PAPER experiment
from scratch and determine whether it is technically safe and internally
consistent enough to proceed to operational preflight for a 30-day experiment
with isolated starting equity of USD 500.

Do not validate the team's narrative. Try to falsify it.

Do not modify the canonical branch.
Do not merge anything.
Do not arm trading.
Do not submit, modify, or cancel any broker order.
Do not enable live-money execution.

If you create adversarial tests, use a temporary audit branch/worktree or
external scratch directory and report them separately.

## Evidence hierarchy

Treat the following as intent/context only, never proof:

- `CODEX_HANDOFF_AUTONOMOUS_IBKR_V1.md`
- `CODEX_IBKR_AUTONOMOUS_RESEARCH_V1.md`
- `EXTERNAL_AUDIT_REMEDIATION_V1.md`
- `EXTERNAL_REAUDIT_V2_REMEDIATION.md`
- `EXTERNAL_AUDIT_V3_REMEDIATION.md`
- `EXTERNAL_AUDIT_REMEDIATION_CLOSURE_V4.md`
- commit messages
- PR descriptions
- historical CI summaries

Authority is:
1. executable code;
2. independently reproduced tests;
3. runtime call graph;
4. current Git tree/history;
5. actual host/broker evidence where available.

## Core experiment contract

The intended experiment is:

- PAPER only;
- initial isolated experimental equity: USD 500;
- duration: 30 calendar days;
- objective: maximize expected terminal isolated experimental equity;
- full loss of isolated experimental equity is an allowed experimental result;
- no external broker/account capital may backstop the experiment;
- no unbounded liability may enter the experiment;
- Codex controls research, opportunity discovery, strategy, instrument,
  timeframe, sizing, entry, monitoring, reduction, exit, and NO_TRADE;
- actual broker feasibility is authoritative;
- all order transmission remains explicitly gated.

The deterministic capital boundary should remain conceptually:

`maximum experiment liability <= current isolated experiment equity`

## Autonomous mandate

Verify that the autonomous route remains free from:

- fixed human-selected trading universe;
- frozen candidate allowlist;
- mandatory strategy catalog;
- mandatory indicators/timeframes;
- legacy 5% per-trade risk cap;
- legacy 15% open-risk cap;
- legacy 20% drawdown cap;
- legacy 40% position cap;
- fixed max-position count;
- mandatory stop loss;
- mandatory diversification.

Search specifically for:

- `candidate_screen_results`
- `SYMBOL_NOT_IN_FROZEN_CANDIDATES`
- `allowed_symbols`
- `symbols_universe`
- `strategy_catalog`
- `RiskPolicy.month1`
- `RiskEngine.month1`

Distinguish dead/legacy code from code reachable by the autonomous runtime.

## Research loop

Verify the real runtime supports:

fresh state
→ Codex
→ one or more model-selected research/tool requests
→ tool results
→ further Codex reasoning
→ final decision

Confirm that Codex, not the host, selects what to research.

Expected primitive broker/research capabilities include:

- account/session context;
- positions;
- open orders;
- executions;
- market scanners;
- contract resolution;
- quotes;
- historical bars;
- option chains / Greeks;
- news;
- broker feasibility / what-if.

Confirm live public research is truly enabled in the Codex CLI argv, not merely
described in a prompt.

## Model attestation — adversarial priority

The intended model is:

- requested model: `gpt-5.6-sol`
- reasoning effort: `max`
- web search: enabled

Do NOT merely search for these strings.

Audit the complete model-attestation path.

Attempt to bypass it with at least:

1. missing `actual_model`;
2. empty stdout;
3. None/non-string output;
4. malformed JSONL;
5. duplicate JSON keys;
6. `actual_model=null`;
7. empty model string;
8. numeric/non-string model field;
9. mismatch to another model;
10. only a `model` field but no authoritative `actual_model`;
11. nested or renamed fields;
12. multiple lines with conflicting model identifiers;
13. an alternate Codex provider;
14. operator CLI override to a lower model/reasoning effort.

Verify that every invalid or ambiguous case fails closed before the experiment
can act.

## Persisted experiment clock

Re-test the original clock defect adversarially.

Verify:

- first start is persisted;
- subsequent restart loads the original start/end;
- a changed `--start-utc` cannot reset the horizon;
- duration is immutable;
- initial allocation is immutable;
- a future start is represented as NOT STARTED rather than elapsed;
- expiration cannot be reset by restart;
- runtime horizon calculation uses broker/server-derived time rather than
  trusting only the local wall clock;
- corruption of the persisted clock blocks.

Attempt clock tampering and restart scenarios.

## Isolated experiment ledger

Audit the isolated ledger independently.

Verify accounting for:

- stock;
- long options;
- short option legs;
- multi-leg spreads;
- multiplier 100;
- partial fills;
- closing fills;
- commissions;
- late commissions;
- marks;
- weighted average cost;
- synthetic execution IDs;
- later reconciliation from synthetic ID to real execId;
- delayed/repeated broker executions.

Verify:

- equity is reconstructed from isolated fills/marks/cash/fees;
- global NLV is not used in experiment equity;
- global broker cash/buying power/margin values are not exposed to Codex;
- ledger is hash chained and chain corruption fails closed;
- duplicate/missing execId handling cannot double-count exposure.

Try to corrupt:
- one row payload;
- predecessor hash;
- event hash;
- synthetic execution identity;
- commission adjustment identity.

## Order registry and fill attribution

Re-test fill isolation.

Expected experiment order refs are variants of:

- `codex-ibkr-paper-30d-a-...`
- `codex-ibkr-paper-30d-p-...`

Verify:

- order identity is persisted BEFORE transmission;
- client order ID is registered;
- broker permId is appended after submission without mutating old rows;
- immediate fills inherit issued order identity when callbacks omit metadata;
- delayed fills must match the same registry row;
- a correct permId must NOT mask a wrong orderId;
- a correct orderId must NOT mask a wrong permId;
- unrelated/manual broker fills cannot enter the isolated ledger;
- another tool cannot spoof only the orderRef prefix and get imported.

Construct adversarial combinations of orderRef/orderId/permId/clientId.

## Broker feasibility / what-if

This is a critical capital-isolation boundary.

Verify new-trade and position-action paths both fail closed when:

- `whatIfOrder` returns None;
- `whatIfOrder` throws;
- init margin evidence is missing;
- maintenance margin evidence is missing;
- commission evidence is missing;
- broker warning contains:
  - insufficient
  - incompatible
  - missing
  - rejected
  - not allowed
  - cannot
- margin exceeds isolated equity.

Explicit scenario:

- isolated equity = $500;
- global paper account buying power >> $500;
- what-if required margin = $600.

The action must BLOCK.

Verify broker-global before/after margin and equity-with-loan values can be used
internally if needed but are NOT exposed to Codex.

## Same-connection execution / TOCTOU

Trace the actual code between:

what-if → final controls → position snapshot → placeOrder

Verify what-if and send use the same IBKR connection.

For position actions, independently test:

- size shrinks after what-if;
- size grows after what-if;
- long position flips to short;
- short position flips to long;
- contract changes;
- operator revokes authorization after registry write but before send;
- kill switch triggers after validation but before send.

Confirm a late sign inversion cannot turn a reducing SELL into a new naked short
or a reducing BUY into a new long.

Identify and quantify any irreducible final check-to-network-send interval.

## Level 4 / derivative boundedness

Re-derive the payoff math independently.

Test at least:

- long stock;
- long call;
- long put;
- debit vertical;
- credit vertical;
- cash-secured/finite-loss short put;
- covered call;
- uncovered short call;
- short stock;
- call ratio spread;
- put ratio spread;
- multi-expiry structure;
- BAG combo;
- multi-leg BUY market order without deterministic price bound.

Confirm:

- bounded structures can pass if broker-feasible and within isolated equity;
- unbounded structures block;
- model-authored `capital_required` is never used as authority or loss-floor
  fallback;
- max loss + commission cannot exceed isolated equity.

## Per-trade market data

The preflight SPY/QQQ/IEF policy is NOT enough.

Verify immediately before any proposed contract is sent:

- actual broker market-data type is LIVE/REALTIME, not merely requested LIVE;
- bid/ask are present and valid;
- quote timestamp is fresh against broker/server time;
- delayed/frozen market data blocks;
- missing data blocks;
- stale data blocks.

For BAG orders:
- verify a fresh direct combo quote OR
- verify fresh LIVE evidence for every leg.

Try to bypass with:
- requested LIVE but actual delayed;
- NaN bid;
- NaN ask;
- stale timestamp;
- combo quote missing with one stale leg;
- combo quote missing with one delayed leg.

## Runtime MARKET_DATA_POLICY gate

Verify the frozen policy is not only a preflight artifact.

On every autonomous cycle and immediately before transmission:

- load and verify policy artifact;
- validate schema/version coherence;
- obtain fresh broker evidence;
- evaluate `MarketDataGate`;
- BLOCK on invalid/missing/stale policy or quotes.

Verify evidence-window protocol:

- SPY, QQQ, IEF;
- SPY primary exchange ARCA;
- QQQ primary exchange NASDAQ;
- IEF primary exchange NASDAQ;
- REGULAR session;
- realtime;
- 5-second cadence;
- 330-second windows;
- 3 windows;
- >=30-minute start separation;
- >=65-minute evidence span;
- >=540 accepted observations;
- >=180 accepted observations per symbol.

Verify evidence span is based on broker quote timestamps, not merely local
receipt clock progression.

Test a frozen/repeated broker quote while local time advances.

## Kill switch and owner authorization

Verify production write/read paths exist.

Test:

- default fail-closed state;
- operator clear;
- operator trigger;
- Codex PAUSE_FOR_REVIEW;
- owner authorization bound to the persisted clock;
- authorization revoked;
- stale authorization from another clock;
- revocation after order-registry write but before broker send.

Immediately before `placeOrder`, fresh control state must be checked again.

Deployment or environment variable alone must NOT be enough to trade.

## Arming boundary

Audit all order-writing call sites.

Confirm:

- paper execution default unarmed;
- `IBKR_AUTONOMOUS_PAPER_ARMED=true` alone is insufficient;
- persisted clock must be valid;
- owner authorization must be valid;
- kill switch must be CLEAR;
- market-data gate must pass;
- Auditor gate must pass;
- reconciliation must pass;
- persistent order registry must exist;
- PAPER account identity must match expected bound account;
- live account / U-prefixed account cannot be used;
- port is PAPER port 4002;
- no hidden live-money execution route exists.

Search the entire repository for:
- `placeOrder`
- submit/cancel/modify order surfaces
- alternate broker adapters
- direct raw socket/API order paths.

## Continuous service behavior

Verify:

- no-position discovery cadence ~300 seconds;
- open-position review cadence ~60 seconds;
- immediate post-fill reevaluation exists;
- post-fill reevaluation is observation/reasoning only, not a second execution;
- position timer resets after post-fill refresh;
- NO_TRADE remains valid;
- recoverable broker/runtime errors do not kill the service;
- fatal DB/ledger corruption does not enter an infinite retry loop;
- PAUSE_FOR_REVIEW creates a real pause/kill/alert side effect;
- equity <= 0 terminates;
- experiment expiry terminates;
- terminal state event contains final marked state and open positions.

Evaluate the deliberate policy of not blindly liquidating after the 30-day
horizon; determine whether the marked terminal state is methodologically sound
for the experiment.

## Auditor V2 — host isolation

Re-audit the Windows isolation design.

Verify:

- expected SID binding;
- auditor not Administrators;
- explicit deny logon/user rights;
- forbidden privileges absent from restricted token;
- protected paths cannot be read/mutated;
- opaque path chain fails closed;
- reparse/symlink attacks fail closed;
- report directory write is allowed but delete/overwrite is denied;
- auditor account is enabled only during bounded probe lifecycle;
- password is rotated after probe;
- prior `seclogon` state is restored.

### Broker socket isolation

This was a former CRITICAL.

The exact endpoint map must be present and DENIED:

- `127.0.0.1:4001`
- `127.0.0.1:4002`
- `[::1]:4001`
- `[::1]:4002`

Missing endpoint, extra endpoint, CONNECTED, OTHER, or NOT_PROVEN must BLOCK.

If you have access to the actual Windows host, independently run the restricted
token probe rather than trusting unit tests.

If you do not have host access, classify host-level enforcement as NOT
OPERATIONALLY VERIFIED, not PASS.

## Auditor trust anchor

Re-test the former circular trust-anchor defect.

Verify the installed runtime is checked against an immutable Git-derived pinned
trust source/anchor.

Try:

- tampered runtime file;
- tampered deployment manifest;
- tampered target manifest;
- regenerated hashes after tampering;
- line-ending normalization differences;
- wrong Git source commit;
- wrong trust-anchor hash.

The finalizer must not accept a hash derived solely from the same mutable
installed manifest it is supposed to validate.

## Receipt freshness

Verify Auditor receipt freshness and integrity are checked:

- at service startup/arming;
- every autonomous cycle;
- immediately before broker transmission.

Stale >24h or hash/runtime mismatch must block.

## Fault injection

Do not trust `FaultInjectionHarness` labels.

Verify that any reported PASS is tied to real executable regression tests.

Add your own fault tests for at least:

- Gateway down;
- contract resolution failure;
- market data delayed;
- market data frozen;
- stale quote;
- recon mismatch;
- duplicate fill;
- missing execId;
- late commission;
- corrupted ledger;
- corrupted clock;
- corrupted market policy;
- stale Auditor receipt;
- malformed Codex output;
- model substitution;
- Codex timeout;
- what-if None;
- margin missing;
- broker rejection;
- partial fill;
- kill-switch race;
- owner-revocation race;
- position inversion race.

## CI / tests

Do not rely on historical counts.

Run the current complete:
`tests/ibkr_paper_30d/`

Report:
- collected;
- passed;
- failed;
- skipped;
- setup errors;
- collection errors;
- OS;
- Python;
- pytest;
- exact SHA.

On Linux, Windows-only tests must skip explicitly, not fail noisily.

Inspect workflows and verify the full directory is run in both Linux and Windows
CI, not a hand-selected subset.

Look for circular tests that simply reproduce implementation assumptions.

## Git history

Inspect the full remediation lineage from the original audited SHA forward.

At minimum inspect:
- original audited SHA `c4a0abdd081724e6073d0a4c394feb9749e4c985`;
- first remediation merge lineage;
- second re-audit remediation;
- V3 remediation merge lineage;
- current canonical HEAD.

Do not assume a merge commit preserved all protections; inspect the current
tree.

## Required answers

Explicitly answer:

A. Is autonomous opportunity discovery genuinely unrestricted by human symbol
or strategy allowlists?

B. Can any legacy 5/15/20/40-style policy affect the autonomous runtime?

C. Can any path consume broker capital beyond isolated experiment equity?

D. Can any path create unbounded liability?

E. Does what-if fail closed on every missing/error evidence path?

F. Is what-if on the same connection as execution?

G. Can a late position sign/size change invert exposure?

H. Is experimental equity independent from global NLV?

I. Can global broker balances leak to Codex through any tool/evidence surface?

J. Can duplicate, missing-ID, delayed, or late-commission fills corrupt equity?

K. Is the 30-day clock restart-proof and tamper-evident?

L. Is runtime market-data enforcement real on every cycle and pre-send?

M. Is the actual proposed contract verified LIVE/fresh before send?

N. Is Auditor V2 checked every cycle and pre-send?

O. Is the restricted auditor unable to reach all four broker loopback
endpoints?

P. Is the trust anchor truly external to the mutable installed runtime?

Q. Can owner revocation / kill switch activation race past the final send gate?

R. Is model substitution/missing actual_model fail-closed for every provider?

S. Can deployment alone or an environment variable alone send orders?

T. Is there any hidden live-money path?

U. Are all current CRITICAL findings closed?

V. Are all current HIGH findings closed?

W. What residual MEDIUM/LOW risks remain?

X. What exact operational prerequisites still require evidence on the real
Windows/IBKR PAPER host?

Y. Is the system READY FOR OPERATIONAL PREFLIGHT?

Z. Is it READY FOR DAY 1 of the 30-day PAPER experiment? If not, enumerate the
exact remaining blockers.

## Required report

Write:

`EXTERNAL_REAUDIT_CODEX_IBKR_AUTONOMOUS_V4.md`

Required structure:

1. Executive Summary
2. Audited repository / branch / exact SHA
3. Audit environment
4. Methodology
5. Current runtime call graph
6. Git-remediation lineage
7. Findings:
   - CRITICAL
   - HIGH
   - MEDIUM
   - LOW
   - INFORMATIONAL
8. Original V1 finding-by-finding closure matrix
9. V2 finding-by-finding closure matrix
10. V3 finding-by-finding closure matrix
11. New findings discovered in V4
12. Autonomous research assessment
13. Capital isolation assessment
14. Ledger/accounting assessment
15. Broker/what-if/execution assessment
16. Level-4 derivative boundedness assessment
17. Market-data assessment
18. Clock/control/arming assessment
19. Auditor/Windows isolation assessment
20. Test/CI assessment
21. Residual risks
22. Operational evidence still required
23. Explicit answers A-Z
24. Final conclusion

For every finding include:
- ID;
- severity;
- exact file/function/line;
- why it matters;
- concrete failure scenario;
- reproduction;
- evidence;
- recommended remediation.

## Verdict discipline

Do NOT write “looks good.”

Use these states:

- READY_FOR_OPERATIONAL_PREFLIGHT
- NOT_READY_FOR_OPERATIONAL_PREFLIGHT

and separately:

- READY_FOR_DAY_1
- NOT_READY_FOR_DAY_1

A code-only PASS is not sufficient to declare READY_FOR_DAY_1 if required
Windows host, IBKR PAPER Gateway, real market-data, or restricted-token evidence
has not been reproduced.

The objective is to falsify the current implementation if possible.
