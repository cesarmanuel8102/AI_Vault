# CODEX IBKR AUTONOMOUS RESEARCH V1

## Objective

Run a 30-day IBKR paper-trading experiment that measures Codex's ability to
maximize terminal experimental equity from an initial isolated allocation of
USD 500.

The experiment evaluates Codex as an autonomous trader/researcher, not as an
approver of human-selected strategies.

## Autonomous mandate

Codex controls:

- what markets and symbols to investigate;
- which read-only research tools to request;
- which public news, macro, filings and catalysts to investigate using live
  native Codex web research (`--search`) when available;
- strategy family and thesis;
- timeframe and holding period;
- instrument and contract structure;
- position sizing;
- whether to remain in cash;
- entry, monitoring, reduction and close decisions.

No fixed symbol universe, strategy family, indicator set, timeframe, per-trade
risk percentage, portfolio-exposure percentage, daily loss limit, weekly
drawdown limit, total drawdown stop, or fixed maximum number of positions is
part of the autonomous route.

Legacy strategy catalogs and frozen candidate lists are not authoritative for
the autonomous route.

## Capital policy

Initial isolated experimental allocation: USD 500.

The full current experimental equity may be lost. A proposal with maximum loss
equal to 100% of current experimental equity is allowed.

The deterministic capital boundary is:

    maximum experiment liability <= current experimental equity

The experiment may not consume capital or collateral outside the isolated
experimental equity even if the broker account has additional buying power.

Unbounded-liability structures are not allowed because they can violate the
isolated-capital boundary.

## Capital-adaptive behavior

Every decision receives fresh experimental equity and broker/account state.

Codex is explicitly instructed to reassess the executable opportunity set as:

- equity changes;
- buying power changes;
- margin requirements change;
- IBKR permissions/feasibility change;
- positions change;
- time remaining changes;
- market conditions change.

A strategy that was infeasible at USD 500 may become feasible after capital
growth and should be reconsidered. A strategy that becomes infeasible after a
drawdown must be discarded or resized.

## Broker authority

The declared options permission level for the experiment is Level 4.

Declared permission is not sufficient by itself. IBKR remains authoritative
for actual contract availability, margin, commission and order feasibility.

The research toolbox provides primitive, Codex-selected access to:

- account state;
- positions;
- open orders;
- recent broker executions/fills for delayed-fill reconciliation;
- IBKR market scanners;
- contract resolution;
- quotes and option Greeks;
- historical bars;
- option-chain discovery;
- subscribed IBKR news;
- IBKR what-if order feasibility and margin.

Single and multi-leg BAG option structures are supported by the research and
what-if layer. The autonomous route uses deterministic payoff analysis instead
of a fixed strategy allowlist: finite-loss short puts, covered calls and
bounded same-expiry multi-leg structures may proceed when their calculated
maximum liability plus costs fits inside current isolated experiment equity;
uncovered short calls, short stock and other unbounded/unverified structures
remain blocked.

## Research loop

The default autonomous model is `gpt-5.6-sol` with reasoning effort `max`.
Both remain operator-configurable, but the experiment default is intentionally
the maximum-capability Codex configuration rather than the prior `gpt-5.5`
default.

Codex may run multiple research rounds before returning a final decision.

Research flow:

    state -> Codex -> research requests -> read-only tools -> Codex -> ...
          -> FINAL decision

Valid final decisions include:

- NO_TRADE
- PROPOSE_TRADE
- MONITOR_POSITION
- REDUCE_POSITION
- CLOSE_POSITION
- PAUSE_FOR_REVIEW

NO_TRADE is valid and is not penalized by the runtime.

## Dynamic experiment state

The autonomous route maintains an isolated append-only experiment ledger that
accounts for actual broker fills by contract id, side, quantity, price,
commission and contract multiplier.

This supports stocks, long options and multi-leg option positions without
borrowing unrelated account equity into the experiment.

Before every decision cycle the runtime:

- reconciles delayed IBKR executions by experiment orderRef;
- deduplicates fills by execution id hash;
- marks tracked open positions with current broker quotes;
- recomputes isolated cash, market value and equity;
- recomputes high-water mark and drawdown for measurement only;
- reconciles tracked position quantity against IBKR;
- filters open orders to experiment orderRef values only;
- injects fresh current equity, broker state and Level-4 context into Codex;
- injects experiment start/end timestamps and remaining time;
- keeps candidate_screen_results empty.

Drawdown is observed for measurement and learning. It is not a fixed stop.

## Operating cadence

The continuous service uses these default observation clocks:

- normal opportunity-discovery cycle: every 300 seconds;
- open-position review cycle: every 60 seconds;
- immediate position-state reassessment after a broker fill.

These are observation/reasoning cadences, not mandatory trade frequencies.
Codex may return NO_TRADE or MONITOR_POSITION on any cycle.

The service terminates when isolated experiment equity reaches zero or the
30-day clock expires. Reconciliation or kill-switch failure blocks new
decisions without substituting a strategy decision.

## Position management

REDUCE_POSITION and CLOSE_POSITION are first-class autonomous decisions.

Before a reduction/close reaches paper execution, IBKR state is re-read and
the runtime verifies that the action reduces rather than increases exposure,
does not exceed the current position size, and passes an IBKR what-if check.

## Non-strategic integrity controls

The following controls remain because they do not choose trades for Codex:

- local IBKR paper endpoint only;
- single DU paper-account identity;
- broker reconciliation gate;
- kill switch;
- market-data integrity gate;
- immutable input hash/cycle checks;
- append-only research/decision evidence;
- IBKR what-if revalidation immediately before execution;
- isolated experimental-capital boundary.

## Execution arming

The autonomous paper executor is intentionally not armed by code deployment.

Paper transmission requires:

    IBKR_AUTONOMOUS_PAPER_ARMED=true

This flag is an operational start/stop control. It is not a strategy or risk
constraint.

No live-money execution is enabled by this implementation.

## Evidence

The runtime persists:

- frozen trader input bundles;
- Codex invocation metadata;
- every research request/result;
- audited native-tool activity metadata;
- broker feasibility evidence;
- final decision/proposal or position action;
- canonical trader result hash;
- multiplier-aware isolated fill/mark ledger;
- post-execution isolated equity snapshot.

This permits later attribution of performance to research quality, sizing,
execution, luck and realized market outcomes.

## Current lifecycle status

Implementation does not start the 30-day experiment.

Existing auditor, market-data and lifecycle readiness gates remain authoritative
until explicitly satisfied and the paper executor is deliberately armed.


## Validation

Current autonomous implementation validation:

- autonomous/regression suite on Linux: 69 passed, 0 failed;
- autonomous/regression suite on Windows: 69 passed, 0 failed;
- autonomous module compilation: PASS on both CI paths;
- live Codex web search flag and GPT-5.6 Sol/max invocation contract: PASS;
- deterministic bounded Level-4 structure tests: PASS;
- no fixed SPY/QQQ/AAPL/IWM/MSFT universe in the autonomous route;
- no 5%/15%/20% or equivalent fixed strategy-risk limits in the autonomous route;
- frozen candidate field retained only as an empty compatibility field;
- paper executor remains unarmed by default.
