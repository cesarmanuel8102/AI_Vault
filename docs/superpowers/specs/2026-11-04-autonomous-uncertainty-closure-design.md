# Autonomous Uncertainty Closure Design

## Intent

Preserve Codex's full trading autonomy while preventing repeated inconclusive analysis from becoming a stable terminal behavior. The host must not choose instruments, strategies, indicators, probabilities, cadence, or risk.

## Selected approach

Add a process-responsibility clause to the existing autonomous mandate. When the same material evidence gap remains unresolved and no material information has changed, Codex must autonomously choose whether to resolve the gap with a method or tool of its choice, replace the method, or redirect attention to another opportunity. Continuing the same investigation is valid only when Codex identifies material new information or positive expected information value.

Alternatives rejected:

- Host-selected statistical thresholds: too strategy-prescriptive and reduces autonomy.
- Host-enforced candidate rotation: may discard a genuinely improving opportunity and reduces autonomy.
- Runtime blocking of repeated NO_TRADE decisions: confuses process quality with a requirement to trade.

## Constraints

- NO_TRADE remains valid.
- No minimum activity or trade count.
- No prescribed asset, strategy, evidence type, tool, cadence, or risk.
- Existing PAPER, capital, execution, reconciliation, and safety boundaries remain unchanged.
- The change is prompt-contract only and must be covered by an autonomy-charter regression test.

## Success evidence

The contract test proves both the closure obligation and the absence of prescriptive language. After deployment, fresh accepted cycles should either produce material new evidence, explicitly change methodology/opportunity, or execute a justified proposal; repeated unsupported conclusions without new information should disappear.
