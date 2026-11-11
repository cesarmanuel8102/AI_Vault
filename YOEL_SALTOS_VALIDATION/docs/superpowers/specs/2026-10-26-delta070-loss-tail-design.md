# Delta 0.70 0DTE Loss-Tail Countermeasure

## Observed cause

The delta 0.70, 0DTE, TP 10% variant wins often but has negative expectancy
because a small number of failed continuations lose a large fraction of the
premium. In the 2025 discovery sample, the causal precursor with the clearest
separation was present 15 minutes after entry:

- option return is at or below -40%; and
- directional underlying return is below zero.

This identifies a failed immediate continuation, rather than ordinary option
noise alone. It flagged four losing 2025 trades and no winners. Applied without
changes to the untouched 2026 sample, it flagged the catastrophic GLD loss and
no winners in checkpoint replay.

## Countermeasure

For delta 0.70, DTE 0, TP 10% only:

1. Reject an entry when estimated roundtrip friction exceeds the 10% target;
   a trade whose expected transaction hurdle is larger than its planned gross
   reward is not economically admissible.
2. Close the position after 15 minutes when both failed-continuation conditions
   above hold.

Preserve the frozen signal, universe, sizing, costs, 15:55 exit and absence of
any other stop or statistical filter.

## Validation

1. QuantConnect 2025 discovery backtest.
2. QuantConnect 2026 locked validation backtest with identical parameters.
3. Combined 2025 through 2026 confirmation.

The countermeasure succeeds only if 2026 net profit and profit factor improve,
winner retention remains high, and the combined result is materially better
than the control. A positive discovery result is not required and cannot
replace out-of-sample validation.
