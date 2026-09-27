# AUTONOMY CONSTRAINT AUDIT — AUTONOMY_EPOCH_1 preparation

Date: 2026-09-25 (evening, market closed)
Base HEAD audited: `fe8c58752be89027db169c1014ec08d29b28dbda`
Method: static inspection of prompts, schemas, loop/runtime/service parameters.
No Codex invocation, no broker writes, no runtime mutation during the audit.

## Classification legend

- **A. HARD SAFETY / EXECUTION INTEGRITY** — must never be removed or model-editable.
- **B. PROVIDER / LIVENESS NECESSITY** — technically necessary; minimize strategic interference.
- **C. OBSERVABILITY / AUDITABILITY** — records evidence only; keep.
- **D. STRATEGIC / METHODOLOGICAL PRESCRIPTION** — remove or convert to optional capability.

## Inventory of current constraints on Codex behavior

| # | Constraint | Where | Class | Epoch-1 decision |
|---|---|---|---|---|
| 1 | Objective sentence "Maximize terminal experimental equity over the remaining 30-day paper-trading experiment." | `autonomous_research.py` `_prompt_payload` mandate.objective | A (objective is the experiment itself) | **Keep** — reworded to horizon-neutral ("remaining experiment horizon") |
| 2 | `capital_can_be_fully_lost: True` / `fixed_percent_risk_limits: False` / `only_external_capital_boundary` | mandate dict | A | Keep (capital boundary statement) |
| 3 | `predefined_symbol_universe/strategy_family/timeframe: False` | mandate dict | A (freedom declarations) | Keep |
| 4 | `broker_and_account_permissions_are_authoritative: True` | mandate dict | A | Keep |
| 5 | `no_trade_is_allowed` / `no_trade_remains_valid` | mandate dict | A (freedom) | Keep |
| 6 | `trading_frequency_is_not_success`, `inactivity_is_not_success`, `cash_preservation_is_not_success_by_itself`, `risk_taking_is_not_success_by_itself` | mandate dict | D (epistemic framing, not strategy) | Keep as compact epistemic fields (they encode the objective function, not a method) |
| 7 | `shallow_research_with_habitual_no_trade_is_not_acceptable`, `avoidable_opportunity_cost_is_failure` | mandate dict | D | **Relax wording** → folded into persistence-toward-objective text without "shallow" judgment language |
| 8 | `capital_and_remaining_time_are_scarce`, optionality fields | mandate dict | D (reasoning aid) | Keep as objective-function facts |
| 9 | Instruction: "Conduct an active search for superior opportunities every cycle" | instruction | D | **Remove "every cycle" cadence prescription** → persistence text without per-cycle duty |
| 10 | Instruction: "If your current discovery method repeatedly fails, change the search process: broaden or alter instruments, asset classes, strategies, horizons, market regions, sessions, research tools and discovery methods" | instruction | D | **Replace** with non-prescriptive adaptivity statement (diagnose/reconsider/replace methodology) |
| 11 | Instruction: "Before concluding NO_TRADE, run a counterfactual challenge: state the best feasible alternative found..." | instruction | **D — counterfactual ritual prescribed** | **REMOVE** (Parts 2/3). NO_TRADE stays valid; no forced narrative ritual. Regret/counterfactual observation is host-side telemetry (already exists in `decision_diagnostics.py`) — model is not forced to perform it |
| 12 | Instruction: "NO_TRADE is valid only when retaining capital and optionality has the higher expected contribution ... after adequate search" | instruction | D (conditional validity of NO_TRADE) | **Relax** → NO_TRADE is a valid local decision whenever preferable to available alternatives (unconditional validity as a local choice) |
| 13 | Instruction: stagnation → "reconsider the search process, never forced trading" | instruction | D | Keep spirit, reworded as methodology-adaptivity (not forced trading) — aligns with Part 8 |
| 14 | Instruction: "Never manufacture trades to satisfy activity expectations" | instruction | D (anti-forced-trading) | Keep |
| 15 | Instruction: optionality preservation paragraph | instruction | D | Keep as expected-value reasoning note (not a fixed risk limit) |
| 16 | Instruction: "You may also use native Codex web search ... for public news, macro, filings, catalysts and market context" | instruction | D (lists example domains — mild steer) | **Replace** with broad legal-resource statement (Part 5) |
| 17 | Instruction: "IBKR data and IBKR what-if remain authoritative for broker/account/contract feasibility" | instruction | A (feasibility authority) | Keep |
| 18 | Toolbox: 11 read-only tools with fixed purposes | `ibkr_research_tools.py` manifest | A (tools are capability, not prescription) | Keep all; **add** workspace/self-tooling/QuantConnect capabilities |
| 19 | Research loop: `max_rounds=24`, `max_requests_per_round=16` | `autonomous_research.py` | B (liveness) + D (research budget) | Keep as **service liveness bound**; **add** research-continuity capability: DEFER research objective to persisted workspace when limit reached (Part 9) — model CHOSES to use it |
| 20 | Provider timeout `timeout_seconds=180` (service default) | `autonomous_service.py` | B | Keep (liveness); continuity mechanism covers longer investigations |
| 21 | Scan cadence `scan_interval_seconds=300`, position `60` | `autonomous_service.py` | B (service scheduling) | Keep unchanged (Part 17: don't invent new cadence) |
| 22 | Output schema: proposal requires thesis/catalyst/entry/invalidation/exit/why_now/alternatives/evidence/disconfirming/confidence + probability/expected-value fields | `AutonomousTradeProposal` pydantic | **C (audit record) + D (catalyst/why_now are strategy hints)** | **Split**: keep audit-integrity fields (thesis, entry_condition, exit_plan, evidence, probabilities — used by ledger/audit) but **remove strategy-prescriptive semantics**: `catalyst` and `why_now` become optional (`catalyst` optional string, `why_now` optional). Schema fields that exist for execution/risk validation (maximum_loss, loss_is_bounded, quantity, order_type) stay required |
| 23 | Probability sanity validator (profit+loss ≤ 1) | proposal validator | C (audit consistency) | Keep |
| 24 | Turn mode RESEARCH/FINAL; decision enum (NO_TRADE/PROPOSE_TRADE/REDUCE/CLOSE/CANCEL/MODIFY/MONITOR/PAUSE) | `AutonomousTurn` | C (output contract) — decision vocabulary is the execution vocabulary, not strategy | Keep |
| 25 | `reason_codes` free-form list | turn schema | C | Keep (observability) |
| 26 | Host-side: research telemetry, interference observation, regret records, risk diagnostics | `research_telemetry.py`, `decision_diagnostics.py`, `interference_observability.py` | C | Keep untouched (host-side; no model burden) |
| 27 | Research history passed to prompt = prior turns of CURRENT cycle only (no cross-cycle memory in prompt) | `_prompt_payload` research_history | D (memory limitation) | **Add workspace context capability**: host passes a workspace summary/pointer block (contents model-controlled) — Part 7 |
| 28 | `candidate_screen_results` field (currently `[]` always) | bundle | C (vestigial) | Keep field (schema stability) |
| 29 | Sandbox `--sandbox read-only`, `--search`, ephemeral, ignore user config | provider command | A (host security) | Keep |
| 30 | Model attestation (actual_model check) + owner exception pin | provider | A | Keep |
| 31 | Market-data gate / policy / REGULAR+REALTIME requirements | `market_policy.py`, runtime gate | A | Keep |
| 32 | Capital boundary, identity, executor, kill switch, lock, single-writer | kernel modules | A | Keep — become `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json` |
| 33 | "search movers" / indicator prescriptions / universe lists | **NOT FOUND** — no such strings exist in the repo's autonomous path | — | Nothing to remove; confirmed by grep |
| 34 | Counterfactual instructions in mandate (challenge ritual) | instruction ¶ | D | Removed (see #11) |

## Findings summary

- **No hidden universe/indicator/strategy-family prescriptions exist** (#33) — the
  current mandate is already universe-free.
- The main strategic prescriptions to remove are: the per-cycle "active search"
  duty (#9), the counterfactual-challenge ritual (#11), the conditional validity
  of NO_TRADE (#12), the enumerated discovery-method list (#10), and the
  strategy-semantic schema requirements `catalyst`/`why_now` (#22).
- Everything classified A stays byte-identical in behavior.
- Parts 4-9 add capabilities (self-tooling, workspace, QuantConnect, continuity)
  without removing any A/B/C boundary.

## Provider-credit safety for tests

All provider tests inject fake `runner=` callables (`test_real_codex_provider.py`,
`test_autonomous_codex_provider.py`, `test_autonomous_service.py` fixtures).
`CODEX_CREDITS_CONSUMED_BY_THIS_WORK = 0` is enforced by never executing a
command whose argv[0] resolves to the real codex binary: tests capture argv and
assert on it. New epoch tests follow the same pattern.