# Objective Salience Design

## Intent

Make the autonomous trader keep the economic objective, current sleeve capital, remaining time, and idle-capital opportunity cost salient while it searches and decides. The change should encourage broader, more economically relevant investigation without prescribing symbols, strategies, instruments, risk levels, trade counts, or trades.

## Goals

- Remind Codex that each sleeve currently has effective capital supplied by the bundle, not the historical $500 constraint.
- Explicitly reject nominal share price as a proxy for opportunity quality or affordability.
- Encourage comparison across liquid large-cap stocks, ETFs, mid-caps with verified catalysts, and liquid options when economically appropriate.
- Require a `NO_TRADE` conclusion to explain the breadth actually examined and why the best available alternatives did not beat cash after costs, while preserving `no_identifiable_candidate` when the search genuinely finds none.
- Treat repeated narrow or unproductive investigation as a reason for Codex to change its own search method.
- Preserve model autonomy and all existing safety, broker, accounting, and execution boundaries.

## Non-goals

- No new screener, service, database, scheduler, tool, strategy, symbol list, or QuantConnect requirement.
- No mandatory instrument coverage, minimum candidate count, minimum trade count, exposure target, or forced risk-taking.
- No change to broker execution, risk limits, reconciliation, sleeve accounting, or order authority.

## Approach

Modify only the existing autonomous mandate text and its prompt-level regression tests. Add concise objective-salience language to the current `autonomous_attention_policy` and instruction: use effective sleeve capital, judge opportunities by expected terminal-equity contribution rather than nominal price, search broadly enough to support a `NO_TRADE` claim, and change methodology when repeated narrow searches have low expected information value. Keep all choices model-selected.

## Success and failure

Success is a visible change over the next two or three sessions: broader candidate and instrument consideration, explicit evidence-based rejection of the strongest alternatives, fewer repeated low-information loops, and improved economic outcomes without degraded decision quality. Failure is increased activity without better net economics, forced or fabricated candidates, or any loss of autonomous choice.

