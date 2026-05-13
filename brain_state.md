# AI_VAULT Brain State — Living Document
# ========================================
# LAST UPDATED: 2026-04-08 18:15 UTC-5
# PURPOSE: Every new agent reads this FIRST. Contains decisions, results,
#          dead ends, and current status. Prevents re-discovery of known facts.
#
# RULE: Update this file at the END of every session with new findings.
# LOCATION: C:/AI_VAULT/brain_state.md

---

## CURRENT CHAMPION: v10.13b

Architecture: HMM 3-state regime detection + NVDA equity (65%) + SPY PCS + bear puts + contrarian calls.
Code: `C:/AI_VAULT/tmp_agent/state/qc_backups/v10_13b_champion_reconstructed.py` (1,385 lines)
Live: Running on IBKR paper (DUM891854) via `C:/Users/cesar/brain_v1013b_live.py`

### Verified Metrics (Full 2023-01-01 to 2026-04-07, backtest ID: 4bacc76ad9694ce6b4236d3649e043b9)

| Metric | Verified | Claimed (docstring) | Delta |
|--------|----------|---------------------|-------|
| Sharpe | 0.822 | 0.90 | -0.078 |
| CAGR | 24.96% | 26.5% | -1.54% |
| DD | 18.7% | 16.6% | +2.1% |
| Net Profit | 107.0% | 116% | -9% |
| WR | 64% | 69% | -5% |
| Sortino | 0.81 | 0.91 | -0.10 |
| Alpha | 0.118 | 0.124 | -0.006 |
| PSR | 57.5% | N/A | — |
| DD Recovery | 205d | N/A | — |
| P/L Ratio | 2.01 | N/A | — |
| Expectancy | 0.917 | N/A | — |
| Orders | 223 | N/A | — |
| Capacity | $21M | N/A | — |
| Beta | 0.093 | N/A | — |
| Fees | $206.08 | N/A | — |
| Turnover | 3.23% | N/A | — |

NOTE: Claimed metrics were from period ending 2026-03-23. Verified extends to 2026-04-07
(tariff-driven market drop in early April likely explains worse numbers).

### "Fat Violet Panda" Backtest — ANALYZED 2026-04-07 18:30
BT ID: c257a9b1067b18d391636749f3c05e02
Source: Original v10.13b code (Cesar's version, pre-agent reconstruction). BT_END=(2026,3,23).
VERDICT: **Same code, shorter period. Confirms original claimed metrics. No new information.**
Metrics: Sharpe 0.899, CAGR 26.5%, DD 16.6%, Net 113.5%, WR 69%, Sortino 0.91, PSR 64.18%
These match the docstring claims exactly — the delta vs verified was 100% from the April tariff crash.
Source saved: C:/AI_VAULT/tmp_agent/state/qc_backups/fat_violet_panda_main.py
Raw data: C:/AI_VAULT/tmp_agent/strategies/brain_v10/fat_violet_panda_raw.json

### IS/OOS Split — COMPLETED 2026-04-07 13:27

| Metric | IS (2023-2024) | OOS (2025-2026) | Full (verified) |
|--------|---------------|-----------------|-----------------|
| Sharpe | **1.453** | **-0.579** | 0.822 |
| CAGR | 40.03% | -8.63% | 24.96% |
| DD | 8.6% | 24.0% | 18.7% |
| WR | 89% | 45% | 64% |
| Sortino | 1.501 | -0.606 | 0.81 |
| Alpha | 0.166 | -0.122 | 0.118 |
| PSR | 87.4% | 6.15% | 57.5% |
| Orders | 117 | 46 | 223 |
| Net | +96.3% | -10.8% | +107.0% |

- IS backtest ID: 30665eccdecbbcfabbfee91832977ec7
- OOS backtest ID: 5ad24a65940196ed52f40fe0736b3f0b
- Results: `C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_13b_is_oos_results.json`

**VERDICT: OOS COLLAPSE. Sharpe -0.579 = NOT DEPLOYABLE.**
Root cause: 65% NVDA allocation overfitted to 2023-2024 AI boom.
The edge in PCS (theta decay) is likely real but drowned by NVDA equity losses in OOS.
Full Sharpe 0.822 is IS subsidizing OOS — misleading as standalone metric.

---

## v10.x FAMILY — VERIFIED BACKTESTS (Full period ~2023-2026)

| Version | Sharpe | CAGR | DD | WR | Net Profit | Sortino | DD Recovery | Orders | Capacity |
|---------|--------|------|-----|-----|------------|---------|-------------|--------|----------|
| v10.13b | 0.822 | 24.96% | 18.7% | 64% | 107.0% | 0.81 | 205d | 223 | $21M |
| v10.12 | 0.763 | 29.0% | 21.3% | 57% | 127.3% | 0.78 | 139d | ? | $83M |
| v10.7 | 0.710 | 19.6% | 9.0% | 75% | 78.3% | 1.104 | 266d | ? | $110M |
| v10.11 | 0.591 | 20.7% | 24.6% | 55% | 83.7% | 0.693 | 218d | ? | $45M |

KEY INSIGHT: v10.7 has DD 9.0% and Sortino 1.104 — best risk profile of all versions.
v10.13b has best Sharpe but worst DD Recovery. v10.12 has best raw returns.

---

## DEAD ENDS — DO NOT REVISIT

### PM Bounce Call (Yoel Options V2.0b) — REGIME-DEPENDENT, NO OOS EDGE

**EXTENSIVE TESTING COMPLETED 2026-04-07 (sessions 1+2)**

The V2.0b PM_BOUNCE_CALL strategy was comprehensively tested across multiple param sets
and structural fix variations. ALL variants show the same pattern: strong IS, negative OOS.

#### G15 Champion (PT=0.35, SL=-0.20, R=0.06) — BEST RAW PARAMS

| Metric | IS (2023-2024) | OOS (2025-2026) | Full (2023-2026) |
|--------|---------------|-----------------|-----------------|
| Sharpe | 1.503 | -0.177 | 0.790 |
| CAGR | 85.9% | -8.2% | 40.1% |
| DD | 48.8% | 22.2% | 48.8% |
| WR | 48% | 43% | 46% |
| PSR | 68.1% | 8.6% | 32.3% |
| Orders | 318 | 175 | 491 |

BT IDs: IS=a293813f, OOS=53be8c0a, Full=4891a8b1

#### G16 = G15 + 4 Structural Fixes (WORSE)

Fixes applied: (1) anti-same-day SL, (2) soft trailing profit lock, (3) QQQ ADX filter, (4) loss streak sizing
ALL FIXES APPLIED TOGETHER DEGRADED EVERY METRIC:

| Metric | G15 Full | G16 Full | Delta |
|--------|----------|----------|-------|
| Sharpe | 0.790 | 0.278 | -0.512 |
| OOS Sharpe | -0.177 | -0.413 | -0.236 |
| Net Profit | 200.8% | 49.7% | -151% |

BT IDs: IS=b33be98b, OOS=241431aa, Full=a86d314f

#### G17 = G15 + FIX 1 only (Anti-Same-Day SL) — REGIME AMPLIFIER

| Metric | G15 IS | G17 IS | G15 OOS | G17 OOS | G15 Full | G17 Full |
|--------|--------|--------|---------|---------|----------|----------|
| Sharpe | 1.503 | 2.489 | -0.177 | -0.725 | 0.790 | 0.985 |
| CAGR | 85.9% | 170.3% | -8.2% | -25.5% | 40.1% | 53.6% |
| DD | 48.8% | 36.8% | 22.2% | 40.5% | 48.8% | 45.0% |

BT IDs: IS=2669a871, OOS=47a358eb, Full=e201de1e

**KEY FINDING: FIX 1 is a REGIME AMPLIFIER, not a fix.** It triples IS gains (bull market overnight
recovery) but doubles OOS losses (choppy market overnight gap downs). IS->OOS degradation
WORSENS: delta Sharpe -3.214 (G17) vs -1.680 (G15).

#### Root Cause Analysis

PM_BOUNCE_CALL generates signals that only have edge in sustained bull trends:
- The "PM bounce" (price touching SMA20 from above in uptrend) requires trending markets
- In 2023-2024 (strong bull): signals work, momentum carries overnight
- In 2025-2026 (chop/range): same signals fire but no follow-through, leading to systematic losses
- ALL fix attempts (risk management changes) are orthogonal to the signal quality problem
- The strategy needs different signal types for non-bull regimes (puts, spreads, etc.) or
  must be turned OFF in non-bull periods

#### Prior V2.0b variants also tested
- V4-B: IS Sharpe 1.391, OOS -0.13
- V5a (anti-sameday): Full Sharpe 0.653 (vs V4-B 0.53) — but OOS still negative
- ~63 backtests total across the V2.0b family

- Files: `C:/AI_VAULT/tmp_agent/strategies/yoel_options/`
- G15/G16/G17 raw results: same directory, g15_*/g16_*/g17_* prefix
- Master results: `C:/AI_VAULT/tmp_agent/strategies/yoel_options/master_all_backtests.json`
- VERDICT: **REGIME-DEPENDENT STRATEGY. No fix can solve the OOS problem without
  fundamentally changing signal generation. ABANDONED for deployment.**
- POSSIBLE RESURRECTION: Only if combined with regime-OFF filter that stays flat in non-bull
  periods, effectively becoming a "bull-only" strategy. But this would reduce trade frequency
  significantly and may not meet institutional targets.

### Trailing stops on NVDA equity (v10.14 — old)
- Attempted in v10.14, degraded performance
- File: `C:/AI_VAULT/tmp_agent/state/qc_backups/project_29490680_v10_14_backup_20260403_041023.py`
- VERDICT: Simple trailing stops hurt the equity leg. Need smarter exit (EMA-based, not percentage-based).

### v10.14 PCS Frequency Push (Cesar's manual iteration) — REGRESSION
- BT ID: 487a56fef60ec3027404927ffeda7dbe ("Calm Red Orange Kangaroo")
- 7 params changed simultaneously: REGIME_CONFIRM 5->3, SHORT_DELTA 0.10->0.12, TP 0.50->0.35,
  DTE_EXIT 21->14, MAX_RISK 0.12->0.16, dual entry hours [10,13], cooldown 3d->1d
- Results: Sharpe 0.783 (-0.116), PSR 49.8% (lost PASS gate), WR 62% (-7%), Sortino 0.763 (-0.15)
- Orders 309 (+97) but net profit ~equal ($21,165 vs $21,351) = churning
- DD Recovery 210d (no improvement vs 205d — was the stated goal)
- Source: C:/AI_VAULT/tmp_agent/state/qc_backups/crok_main.py
- VERDICT: REGRESSION. More trades, worse quality. Discard. Back to v10.13b as base.

---

## ROOT CAUSE DIAGNOSIS (v10.13b gaps)

All 7 metric gaps point to ONE structural problem: **low trade frequency with long holding periods**.

- 223 orders / 3 years = ~6 trades/month
- Turnover 3.23% = almost static portfolio
- DD Recovery 205d = if you fall, 7 months to recover
- Sortino 0.81 = losses last too long

The 64% WR with P/L 2.01 confirms the edge is REAL. The problem is expressing it in too few bets without active drawdown management.

### Improvement Vectors (ranked by expected impact)

1. **Exit dinamico en drawdown** — if position drops >X% from entry, partial/full close + re-entry on momentum recovery. Expected: DD Recovery 205d -> 60-90d, Sortino +0.2-0.4
2. **Senales complementarias** — add mean-reversion on shorter timeframe. Target: 400-600 orders. Better statistical significance.
3. **Volatility-targeting position sizing** — scale inversely with recent vol. Expected: Sharpe +0.1-0.2 without changing signals.
4. **Faster regime transitions** — current 5-day confirm + 5% gradual step is too slow. NVDA 65% doesn't reduce fast enough in BEAR.
5. **NVDA concentration risk** — 65% in one ticker is idiosyncratic risk. Consider adding 2-3 equity positions or reducing to 40-50%.

### CRITICAL: v10.7 as alternative base
v10.7 has DD 9.0%, Sortino 1.104, WR 75% — potentially better base than v10.13b for improvements.
MUST run IS/OOS split on v10.7 to check if same OOS collapse exists.

### CRITICAL: v10.13b OOS COLLAPSED
IS Sharpe 1.453 -> OOS Sharpe -0.579. NVDA 65% allocation is the root cause.
v10.13b Full Sharpe 0.822 is IS subsidizing OOS — NOT a real measure of forward performance.
The system is NOT deployable in current form. Need equity leg diversification.

---

## v19 ML EQUITY — TESTED AND ABANDONED (2026-04-08)

### v19 v2.0b — Baseline LightGBM (25 features, SPY daily)

Architecture: LightGBM single model, ~25 features (returns, vol, RSI, BB, MACD, ATR, VIX, credit, OFI, vol clock/skew/regime, calendar), triple-barrier labels (H=10, PT=1.25sigma, SL=1.0sigma, 15bps costs), threshold 0.55, position 0.50, retrain every 63 days. Pre-loads 1500 days of history to train before first trade.

Code: `C:/AI_VAULT/tmp_agent/strategies/v19_equity_test.py` (v3.0 — final version)

| Metric | IS (2022-2024H1) | OOS (2024H2-2026) | Full (2022-2026) |
|--------|------------------|-------------------|------------------|
| Sharpe | -0.644 | -2.442 | -0.532 |
| CAGR | 1.07% | 0.58% | 2.83% |
| DD | 6.1% | 2.2% | 6.1% |
| Orders | 48 | 24 | 92 |
| WR | 46% | 58% | 49% |
| P/L | 1.38 | 0.93 | 1.56 |
| Expectancy | 0.090 | 0.123 | 0.251 |
| PSR | 5.9% | 10.3% | 7.1% |
| Beta | 0.21 | 0.044 | 0.213 |
| Turnover | 2.53% | 1.74% | 2.79% |

BT IDs: IS=a3dce1dfd01e347698238ca6050b86be, OOS=780e3090698afcb982981f93a3e13c59, Full=8bc94fc761b3321ed31697a2731073b1

### v19 v2.0b — Deep Trade Diagnosis (45 trades from Full)

| Year | Trades | PnL | WR |
|------|--------|-----|----|
| 2022 | 20 | -$123 | 50% |
| 2023 | 4 | +$441 | 75% |
| 2024 | 5 | +$60 | 80% |
| 2025 | 13 | +$1,142 | 62% |
| 2026 | 3 | -$210 | 0% |

Key findings from trade analysis:
- Model has MILD edge: total PnL +$1,309 on $10K = 13.1% in 4.25 years
- Winners: Avg MFE $172, Avg MAE -$32 (good: lets winners run)
- Losers: Avg MFE $24, Avg MAE -$138 (bad: goes against immediately)
- Avg gap between trades: 33.8 calendar days (~11 trades/year)
- Only ~10% of time invested (45 trades x ~10 days / 1065 trading days)
- Sharpe negative because CAGR (2.83%) < risk-free rate (~4.5%) during period
- SPY B&H returned ~12% in same period — model matched with 0.21 beta

### v19 v3.0 — Aggressive Tuning (WORSE)

Changes: threshold 0.55->0.50, position 0.50->0.90, horizon 10->15, PT 1.25->1.5, SMA200 regime filter (long only above SMA200), exit threshold 0.48->0.45

| Metric | v2.0b Full | v3.0 Full | Delta |
|--------|------------|-----------|-------|
| Sharpe | -0.532 | -0.467 | +0.065 |
| Net | 12.6% | 7.1% | **-5.5%** |
| DD | 6.1% | 16.4% | **+10.3%** |
| P/L | 1.56 | 1.00 | **-0.56** |
| Expectancy | 0.251 | 0.080 | **-0.171** |
| Orders | 92 | 100 | +8 |

BT IDs: IS=c6bbc2e2d78cf488633fcc134afb7904, OOS=e65cbcbcd2d139c9fb5ad86e6c2debe0, Full=16f9657301478c2975608dfb2f63e027

### ROOT CAUSE: Why v19 ML equity has no commercial edge

1. **Threshold 0.50 = noise trades**: Lowering from 0.55 to 0.50 admitted low-quality signals, P/L dropped from 1.56 to 1.00
2. **Position sizing 0.90 amplifies losses**: DD tripled from 6.1% to 16.4%
3. **25 simplified features insufficient**: The v19.2b research pipeline uses ~60 features with VPIN (numba), Kyle's Lambda, Parkinson vol, asymmetric vol. This simplified version lost the signal.
4. **Single LightGBM vs 3-layer stacking**: v19.2b uses RF+ET+LGB+XGB->LR->LR. Single model = worse generalization.
5. **Fundamental limitation**: Daily SPY direction with these features may simply not be predictable enough for institutional-quality returns.

### VERDICT: v19 ML EQUITY ABANDONED

The simplified v19 implementation does NOT have edge. Two tuning attempts (v2.0b conservative, v3.0 aggressive) both show negative Sharpe everywhere. The full v19.2b pipeline with 60+ features and 3-layer stacking MIGHT work but would require:
- Implementing VPIN and Kyle's Lambda in pure Python loops (no numba in QC)
- Building 3-layer stacking ensemble (4 base models + 2 meta)
- This is 1000+ lines of additional code with high risk of same result

**DO NOT revisit v19 without a fundamentally new feature source (e.g., intraday data, alternative data, options flow).**

---

## v10.15 QQQ SUBSTITUTION (NVDA -> QQQ) — TESTED 2026-04-08

Code: `C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_15_qqq.py`  
Runner: `C:/AI_VAULT/tmp_agent/scripts/v10_15_runner.py`  
Results JSON: `C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_15_qqq_is_oos_full_results.json`

### Implemented Changes vs v10.13b

1. Equity leg ticker swapped from NVDA to QQQ (`BULL_EQUITY_WEIGHTS={"QQQ":1.0}`)
2. EMA20 sell-only gate migrated from NVDA symbols/vars to generic equity-leg vars (`eq_*`)
3. Added explicit backtest parameters `start_year` and `end_year`
4. Added mandatory `self.Liquidate()` in `OnEndOfAlgorithm`
5. Kept account model as `InteractiveBrokersBrokerageModel(AccountType.Margin)`

### QC Operational Incident (verified)

- First OOS/FULL attempt returned runtime error from unrelated code (`self.window.Add(data.Bars[self.symbol])` at `main.py:84`).
- Verified via `files/read` that QC project `main.py` had been overwritten by `MlExecutionAlgorithm` (2022-2024 script), not v10.15 code.
- Fix applied: upload `main.py` before EACH backtest + signature verification (`V10_15_QQQ_SIGNATURE_20260408`) before compile.
- Re-run after fix produced valid completed backtests.

### v10.15 Metrics (ALL 27 captured in JSON; key subset below)

| Metric | IS (2023-2024) | OOS (2025-2026) | Full (2023-2026) |
|--------|----------------|-----------------|------------------|
| Sharpe | 0.291 | -0.353 | 0.502 |
| CAGR | 10.743% | -2.241% | 16.165% |
| DD | 6.1% | 17.4% | 13.2% |
| Net Profit | 22.675% | -2.828% | 63.189% |
| Sortino | 0.293 | -0.427 | 0.523 |
| PSR | 44.887% | 8.618% | 37.558% |
| Win Rate | 58% | 53% | 55% |
| P/L Ratio | 6.44 | 0.86 | 4.04 |
| Orders | 123 | 40 | 224 |
| Alpha | -0.016 | -0.078 | 0.072 |
| Beta | 0.32 | 0.613 | -0.091 |
| Fees | $123.00 | $40.00 | $222.00 |

Backtest IDs:
- IS: `a1e281c05fd5d01d0f8a89820c251a15`
- OOS: `1ca560b73bb5b7719d1f88e22330a211`
- Full: `eb6adfc307efa3c5b10b6d5727eb13ae`

### Delta vs v10.13b (same splits)

| Metric | IS Delta | OOS Delta | Full Delta |
|--------|----------|-----------|------------|
| Sharpe | -1.162 | +0.226 | -0.320 |
| CAGR | -29.284 pp | +6.387 pp | -8.790 pp |
| Net Profit | -73.581 pp | +7.942 pp | -43.805 pp |
| Drawdown | -2.5 pp | -6.6 pp | -5.5 pp |
| PSR | -42.544 pp | +2.467 pp | -19.991 pp |
| Orders | +6 | -6 | +1 |

### Verdict

- OOS improved materially vs v10.13b (`Sharpe -0.579 -> -0.353`, `Net -10.77% -> -2.83%`, `DD 24.0% -> 17.4%`)
- But OOS still fails kill gates (Sharpe < 0, CAGR < 0, PSR 8.6%)
- IS edge collapsed heavily vs v10.13b (`Sharpe 1.453 -> 0.291`)
- **Conclusion: Option A (NVDA->QQQ single swap) reduces damage but does not recover deployable edge. v10.15 is NOT deployable.**

---

## INSTITUTIONAL TARGETS (from Analisis.txt)

| Category | Metric | Target | v10.13b Status |
|----------|--------|--------|---------------|
| Kill Gate | CAGR | >= 30-50% | 24.96% BELOW |
| Kill Gate | Sharpe | >= 1.0 (deploy) | 0.822 BELOW |
| Kill Gate | Sharpe | >= 0.6 (research) | 0.822 PASS |
| Kill Gate | PSR | >= 60-70% | 57.5% BELOW |
| Profitability | Net Profit | >= 120-200% (3y) | 107.0% BELOW |
| Profitability | Expectancy | >= 0.4-0.7 | 0.917 PASS |
| Profitability | P/L Ratio | >= 1.8-2.5 | 2.01 PASS |
| Risk | Drawdown | <= 20-25% | 18.7% PASS |
| Risk | Sortino | >= 1.2-1.8 | 0.81 BELOW |
| Risk | DD Recovery | <= 60-120d | 205d FAIL |
| Trades | Win Rate | 40-55% | 64% ABOVE |
| Trades | Total Orders | >= 800-1500 (3y) | 223 BELOW |
| Efficiency | Turnover | >= 10-30% | 3.23% BELOW |
| Efficiency | Capacity | >= $250K-1M | $21M PASS |

Scorecard: 6 PASS, 7 BELOW, 1 FAIL

---

## OPERATING RULES

- Capital: $10K personal. Prop firm abandoned.
- Margin account (AccountType.Margin)
- paper_only globally. live_trading_forbidden.
- Respond in Spanish. Don't say "voy a" — just do and narrate.
- Browser: Microsoft Edge.
- PowerShell: $ variables get eaten — use .ps1 scripts or Python. Forward slashes in paths.
- LSP errors on QC algorithm files are NORMAL.
- Max 5 free parameters (contract S13).
- Kelly PROHIBITED. Fixed Fractional + Vol Targeting + DD Throttling.
- IS: 2023-2024, OOS: 2025-2026.
- OnEndOfAlgorithm -> self.Liquidate() MANDATORY.
- QC API: sha256(TOKEN:timestamp) auth, timeout=30, retry with backoff.
- Unicode crashes Python stdout redirect on Windows (cp1252). ASCII only in print().
- python -u for unbuffered output in background processes.
- QC backtest progress: format float as f'{progress:.0%}'.
- rg (ripgrep) NOT available. Use Python scripts or grep tool.
- "Si una fase no cambia decisiones, es ruido."
- "YA ESTAS EN BUILD" — action, not planning.
- "cuando te digo algo espero que lo corrobores con la realidad" — verify actual errors from logs/docs.
- ALWAYS pass explicit start_year/end_year to backtests.
- Show ALL 27 QC metrics in results tables, not just top 5.

---

## QC ACCESS

- User ID: 384945
- Token: 4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3
- Org: 6d487993ca17881264c2ac55e41ae539
- Project ID: 29490680
- Live Deploy: L-f8a6181a1157273d680206e87a806435 (running, idle)

---

## KEY FILE LOCATIONS

### Strategy Code
- v10.13b champion: `C:/AI_VAULT/tmp_agent/state/qc_backups/v10_13b_champion_reconstructed.py`
- v10.13b live wrapper: `C:/Users/cesar/brain_v1013b_live.py`
- v10.13b live log: `C:/Users/cesar/brain_v1013b_live.log`
- v10.13b state: `C:/Users/cesar/brain_v1013b_state.json`
- v10.7 live: `C:/Users/cesar/brain_v107_live.py`
- PM Bounce (abandoned): `C:/AI_VAULT/tmp_agent/strategies/yoel_options/`

### Backtest Results
- v10.13b Full verified: `C:/AI_VAULT/tmp_agent/strategies/brain_v10/v10_13b_full_verified.json`
- v10.12: `C:/Users/cesar/v1012_bt_full.json`
- v10.11: `C:/Users/cesar/v1011_bt_full.json`
- v10.7: `C:/Users/cesar/v107_bt_full.json`
- PM Bounce master: `C:/AI_VAULT/tmp_agent/strategies/yoel_options/master_all_backtests.json`

### Runner Templates
- v5 ablation runner (good template): `C:/AI_VAULT/tmp_agent/scripts/v5_ablation_runner.py`
- v10.13b verification runner: `C:/AI_VAULT/tmp_agent/scripts/v10_13b_verification_runner.py`
- v10.13b IS/OOS runner: `C:/AI_VAULT/tmp_agent/scripts/v10_13b_is_oos_runner.py`

### Strategic Docs
- Analisis.txt: `C:/Users/cesar/Downloads/Analisis.txt`
- This file: `C:/AI_VAULT/brain_state.md`

---

## DECISIONS LOG

| Date | Decision | Rationale | Result |
|------|----------|-----------|--------|
| 2026-04-06 | Abandon PM Bounce Call | IS Sharpe 1.39 is 3-7x theoretical max, OOS -0.13, all fixes dead | Correct |
| 2026-04-07 | v10.13b is champion | Best Sharpe (0.822) of all v10.x, multi-strategy, regime-adaptive | Verified |
| 2026-04-07 | Claimed metrics inflated | Sharpe was 0.90 claimed, verified at 0.822 (extended period to Apr 7) | Noted |
| 2026-04-07 | IS/OOS split needed | Must verify edge holds OOS before any optimization work | DONE — OOS COLLAPSED |
| 2026-04-07 | v10.13b NOT deployable | OOS Sharpe -0.579, IS 1.453 — NVDA 65% overfitted to 2023-2024 AI boom | Critical finding |
| 2026-04-07 | NVDA concentration is root cause | 65% single-ticker in equity leg = structural overfitting to one regime | Must diversify |
| 2026-04-07 | Fat Violet Panda = original v10.13b | Same code, BT_END=Mar 23 vs Apr 7. Confirms claimed metrics. No new info. | Closed |
| 2026-04-07 | v10.14 CROK = regression | 7 params changed, Sharpe -0.116, PSR lost gate, churning. Discard. | Dead end |
| 2026-04-07 | Resurrect V2.0b for forensic analysis | G15 OOS better than v10.13b OOS, more trades. Premature kill. | Partially correct |
| 2026-04-07 | G15 forensic: same-day trades TOXIC OOS | 27 same-day OOS trades: WR 25.9%, PnL -$3,852 (459% of total loss) | Verified |
| 2026-04-07 | G15 forensic: QQQ main OOS loser | 34 OOS trades: WR 38.2%, PnL -$2,241 (267% of total loss) | Verified |
| 2026-04-07 | G16 (4 fixes) = WORSE than G15 | All metrics degraded. Fixes interact destructively. | Dead end |
| 2026-04-07 | G17 (FIX1 only) = regime amplifier | IS: Sharpe 1.5->2.5, OOS: -0.18->-0.73. Amplifies IS, destroys OOS. | Dead end |
| 2026-04-07 | PM_BOUNCE_CALL is regime-dependent | No risk mgmt fix can solve signal quality problem. Edge only in bull. | Critical finding |
| 2026-04-08 | v19 ML equity v2.0b: no edge | 25 features + single LightGBM on SPY daily. Sharpe negative IS/OOS/Full. | Dead end |
| 2026-04-08 | v19 v2.0b has mild trade-level edge | WR 53%, P/L 1.34, +$1309 Full. But trades 11x/year with 10% exposure -> cash drag | Informative |
| 2026-04-08 | v19 v3.0 aggressive tuning = WORSE | Lower threshold dilutes quality (P/L 1.56->1.00), higher position amplifies DD (6%->16%) | Dead end |
| 2026-04-08 | v19 ML ABANDONED | Simplified feature set insufficient. Full pipeline too complex for uncertain payoff. | Decision |
| 2026-04-08 | v10.15 (NVDA->QQQ) executed and verified | OOS improved but stayed negative; IS edge collapsed; not deployable. | Decision |
| 2026-04-08 | QC cloud main.py overwrite risk confirmed | `files/read` showed unrelated `MlExecutionAlgorithm`; added upload+signature verify per run. | Operational control |

---

## NEXT SESSION PRIORITIES

### ALL THREE STRATEGY FAMILIES TESTED — ALL FAILED OOS

| Family | IS Best Sharpe | OOS Best Sharpe | Root Cause |
|--------|---------------|-----------------|------------|
| v10.x (equity+options) | 1.453 | -0.353 | Equity concentration reduced but total edge still insufficient OOS |
| PM_BOUNCE_CALL | 1.503 | -0.177 | Regime-dependent (bull-only) |
| v19 ML Equity | -0.644 | -2.442 | No edge (weak signal, cash drag) |

### CRITICAL: Need to decide new direction

1. **Option A: v10.x with diversified equity leg**
   - Status: PARTIALLY TESTED (QQQ single swap done as v10.15, failed OOS kill gates)
   - Next if continuing A: multi-asset equity basket (>=3 tickers) + regime-aware sizing
   - Keep PCS/bear puts/contrarian calls structure (the options edge may be real)
   - Risk: diversifying reduces idiosyncratic blowups but can also remove concentrated upside

2. **Option B: Pure options income (PCS/Iron Condors)**
   - Abandon equity leg entirely, focus on theta decay strategies
   - Systematic put credit spreads on SPY with regime-based sizing
   - Pro: theta decay is real edge, less regime-dependent
   - Con: complex, needs intraday fills, max ~15-20% CAGR

3. **Option C: Multi-asset momentum/trend-following**
   - Simple trend-following on 5-10 futures/ETFs (SPY, TLT, GLD, UUP, etc.)
   - Classical CTA approach: SMA crossover + position sizing
   - Pro: well-established edge, regime-adaptive by design
   - Con: lower Sharpe (~0.5-0.8 historically), needs many assets for diversification

4. **Option D: Cesar's ML research pipeline (v17/v26) as trading algo**
   - v26 marked "MEJOR" by Cesar, v17 has Optuna HPO
   - BUT: same fundamental problem as v19 — daily SPY ML may not have enough edge
   - Only try if features are fundamentally different from v19

5. **RECOMMENDED NEXT: Option B or C**
   - Option A single-swap test already done (v10.15) and failed OOS deployability
   - Highest information gain now comes from changing strategy family, not micro-tuning v10.15

### v19 ML files for reference
- v19 algorithm: `C:/AI_VAULT/tmp_agent/strategies/v19_equity_test.py`
- v19 runner: `C:/AI_VAULT/tmp_agent/scripts/v19_runner.py`
- v19 diagnosis scripts: `C:/AI_VAULT/tmp_agent/scripts/v19_diagnose*.py`
- v19 results: `C:/AI_VAULT/tmp_agent/strategies/v19v3_is_oos_full_results.json`
- v19.2b research pipeline: `C:/Users/cesar/OneDrive/Escritorio/Research/Modelos BT QC/# ML RESEARCH PIPELINE v19.2b.txt`

### G16/G17/V19 Backtest IDs (for reference)

| Name | BT ID | Sharpe |
|------|-------|--------|
| G16 IS | b33be98b9b632791aae37f3bd789c3cf | 0.810 |
| G16 OOS | 241431aa393e8b5f25bd42255612c1d7 | -0.413 |
| G16 Full | a86d314ff11ff8849e094025e8ca7e7b | 0.278 |
| G17 IS | 2669a8718b486c3cb771978227c46c37 | 2.489 |
| G17 OOS | 47a358eb33615d63c1eddbe7a6cf1b53 | -0.725 |
| G17 Full | e201de1e056c8c5ca2c4867e1aca08c6 | 0.985 |
| V19v2 IS | a3dce1dfd01e347698238ca6050b86be | -0.644 |
| V19v2 OOS | 780e3090698afcb982981f93a3e13c59 | -2.442 |
| V19v2 Full | 8bc94fc761b3321ed31697a2731073b1 | -0.532 |
| V19v3 IS | c6bbc2e2d78cf488633fcc134afb7904 | -0.443 |
| V19v3 OOS | e65cbcbcd2d139c9fb5ad86e6c2debe0 | -1.046 |
| V19v3 Full | 16f9657301478c2975608dfb2f63e027 | -0.467 |
