# 0DTE First-Rebound Variants Design

## Intent

Test whether the frozen first-rebound signal performs better when expressed with
same-day expiry long options and substantially more capital per trade.

## Frozen variants

- Period: 2025-01-01 through 2026-10-25.
- Universe and signal: identical to `FIRST_REBOUND_SPEC.md`.
- `ATM`: strike with minimum absolute distance to underlying spot.
- `OTM`: nearest strike strictly OTM (call above spot, put below spot).
- Expiry: contract expiry date must equal the signal date (0DTE).
- Entry: market order after a valid hourly signal and usable bid/ask quote.
- Allocation: at most 10% of currently available cash, also capped at 10% of
  total portfolio equity, measured using option ask and the 100 multiplier.
- No stop loss and no underlying invalidation exit.
- Take profit: option liquidation value at bid reaches 135% of actual entry
  premium.
- Mandatory exit: 15:55 ET on the entry date, regardless of PnL.
- Never exercise, hold overnight, average down, or reinforce.
- Maximum one position per underlying and ten positions in aggregate.

## Execution assumptions

- Interactive Brokers brokerage and fee model.
- Minute option quotes; constant option slippage of 0.01 price units.
- A signal is skipped if no 0DTE contract exists or a usable quote is not
  obtained within 30 minutes.
- Orders must report `FILLED` before position state is published or removed.
- All remaining holdings are liquidated before the final backtest boundary.

## Approaches considered

1. Modify the prior options project in place. Rejected because it would obscure
   the frozen 21-45 DTE evidence.
2. Create a separate QC project sharing only the pure signal helper. Selected
   because it isolates the experiment while preserving exact signal parity.
3. Add 0DTE as another mode to the old project. Rejected because 0DTE lifecycle
   rules differ materially from multi-day options.

## Outputs

- Separate completed cloud backtests for ATM and OTM.
- Raw QuantConnect payloads, deterministic summary, and Spanish report.
- A result is invalid if it ends with holdings, an error, or unmatched entries
  and closed positions.
