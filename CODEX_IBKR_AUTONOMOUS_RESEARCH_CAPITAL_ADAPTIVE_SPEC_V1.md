# CODEX IBKR Autonomous Research + Capital-Adaptive Trader Spec V1

## Experiment objective

The 30-day IBKR PAPER experiment starts from an experimental allocation of
USD 500 and measures the ability of Codex to autonomously maximize terminal
experimental equity.

The experimental capital is fully loss-tolerant.  Total loss is an admissible
experimental outcome, not a target.

## Economic constraints

Codex's strategy space is constrained only by:

1. the instruments and structures actually supported by the IBKR paper broker;
2. the account's actual permissions, configured Options Permission Level 4,
   market-data entitlements and margin rules;
3. current experimental equity and broker buying power;
4. worst-case experimental liability must not exceed current experimental
   equity.

There is no fixed:

- risk percentage per trade;
- total exposure percentage;
- daily loss limit;
- weekly drawdown limit;
- total drawdown stop;
- maximum concurrent-position count;
- diversification requirement;
- strategy family;
- symbol allowlist;
- asset-class allowlist beyond broker/account permissions;
- timeframe allowlist;
- mandatory stop-loss percentage;
- mandatory trade frequency.

Aggressive concentration is allowed when Codex's probabilistic analysis
supports it.  NO_TRADE remains valid when no available action improves
expected terminal wealth.

## Autonomous research

Codex decides what information it needs.

The runtime supplies an auditable toolbox rather than a prefiltered answer.
Codex can iteratively choose:

- account state / buying power;
- contract search;
- IBKR market scanners;
- contract details;
- quotes;
- option Greeks / implied volatility when available;
- historical bars with Codex-selected horizon and timeframe;
- option expirations / strikes / exchanges;
- broker news when entitled;
- live read-only web search for current external evidence;
- capital feasibility;
- exact IBKR what-if margin / commission preview;
- optional external research when a read-only external provider is configured.

Candidate screens from legacy Brain V9, QuantConnect or other scanners may be
provided as evidence, but are advisory only.  They never define the permitted
symbol or strategy universe.

## Capital adaptation

Current experimental equity is rebound into the research toolbox at the start
of every decision cycle. The exact experiment start timestamp is also bound to
the decision bundle; Codex receives day index and remaining seconds/days until
the fixed 30-day terminal horizon.

A change in equity immediately triggers a new research cycle so Codex can
discover instruments or structures that became newly accessible, or stop using
structures that are no longer financially feasible.

Conceptually:

    Strategy_t = f(
        ExperimentalEquity_t,
        BuyingPower_t,
        BrokerCapabilities_t,
        Market_t,
        Evidence_t,
        TimeRemaining_t
    )

No code maps fixed equity bands to predetermined strategies.

## Broker feasibility

Before any final PROPOSE_TRADE decision, Codex must obtain:

1. capital_feasibility evidence using current experimental equity and broker
   buying power;
2. an exact IBKR what-if preview for the intended order/structure.

The what-if path is PAPER-only and forces transmit=false.  It is used to obtain
margin and commission impact, not to submit an order.

A proposal lacking these two pieces of evidence is not execution-ready.

Every proposed economic leg must also resolve to an IBKR contract ID and have a
fresh real-time IBKR quote for that exact contract before execution readiness.
Delayed, stale, unresolved, or mismatched contract data fails closed.

The runtime independently proves that the payoff structure has no unbounded-loss
direction. A model-provided maximum-loss number cannot override this proof.
Short equity, naked short calls, and unhedged directional derivatives therefore
cannot pass merely because Codex reports a small estimated loss.

## Scheduling

The scheduler controls thinking cadence, not trade frequency:

- normal opportunity discovery: every 300 seconds;
- open-position review: every 60 seconds;
- equity change: immediate;
- broker order/position event: immediate.

Codex can make zero, one or multiple trading decisions as justified by
opportunity and broker state.

## Preserved deterministic boundaries

The following infrastructure remains outside Codex and does not choose the
strategy:

- IBKR PAPER identity proof;
- broker reconciliation;
- market-data freshness/integrity gates;
- experimental subledger;
- immutable decision/research evidence;
- execution lock;
- auditor isolation;
- kill switch;
- worst-case liability <= experimental equity;
- explicit paper-order authorization.

These controls prevent infrastructure errors from escaping the experiment;
they do not impose a trading style.

## Order authority

Autonomous research and decision generation do not themselves grant order
authority.

Paper-order submission remains a separate gated side effect.  The experiment
must not be started and no paper order must be transmitted until the existing
broker identity, reconciliation, market-data, auditor and execution gates are
satisfied and paper-write authority is explicitly enabled.

Live / real-money trading is outside this specification.
