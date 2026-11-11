# Yoel Sardinas transcript-derived research

This directory preserves the reproducible research performed on 2026-10-25 and
2026-10-26 from the user's course-video transcriptions. It is distinct from the
older `tmp_agent/strategies/yoel_options` PM-bounce study.

## Scope

- Post-shock continuation and reversal hypotheses.
- First moving-average rebound in equities, long options, and debit spreads.
- ATM/OTM 0DTE variants and TP sensitivity.
- Delta/DTE comparison: delta 0.50/0.70 and DTE 0/7/14.
- Loss-tail, timed-exit, trailing, and profit-ladder countermeasures.
- Capital deployment from $500 and the 2x50% allocation experiment.
- Capital-independent causal entry selector with frozen OOS validation.

## Start here

Read the reports chronologically:

1. `INFORME_PRELIMINAR_2026-10-25.md`
2. `INFORME_OPERABILIDAD_2026-10-25.md`
3. `INFORME_OPCIONES_2026-10-25.md`
4. `INFORME_PRIMER_REBOTE_2026-10-25.md`
5. `INFORME_0DTE_PRIMER_REBOTE_2026-10-25.md`
6. `INFORME_0DTE_TP5_OPTIMIZACION_2026-10-25.md`
7. `INFORME_0DTE_PRECURSORES_PERDIDA_2026-10-25.md`
8. `INFORME_DELTA_DTE_2026-10-26.md`
9. `INFORME_DELTA070_COLA_PERDIDAS_2026-10-26.md`
10. `INFORME_CAPITAL_500_APERTURA_2026-10-26.md`
11. `INFORME_SELECTOR_CAUSAL_2026-10-26.md`

## Current conclusion

The work found attractive intermediate samples, including high win rates and a
profitable $500 trajectory in 2025-2026. Those results did not remain profitable
across broader periods or frozen out-of-sample validation. The current research
verdict is **NO-GO for deployment**. The artifacts are retained for independent
review and for formulating genuinely new causal hypotheses, not for silently
retuning the same holdout period.

## Deliberate exclusions

The public research branch excludes downloaded LEAN/QuantConnect market data,
local IDE/cache files, generated `lean.json`, and the 227 MB observation CSV.
These are not needed to understand the rules or audit the recorded cloud
backtest outputs. Full course transcriptions are also not published here.
