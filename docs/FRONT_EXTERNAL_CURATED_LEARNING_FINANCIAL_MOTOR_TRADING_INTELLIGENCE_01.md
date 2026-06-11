# FRONT-EXTERNAL-CURATED-LEARNING-FINANCIAL-MOTOR-TRADING-INTELLIGENCE-01

**Timestamp**: 2026-06-11T05:33Z  
**Status**: COMPLETE  
**Branch**: codex/own-capital-sustainable-return  
**Functional Commit**: pending  

## Objective

Create a canonical curated source plan for Brain to learn Financial Motor / Trading Intelligence safely, without ingesting into memory or FAISS, without executing trades, and without connecting to brokers.

## Why Financial Motor / Trading Intelligence is a Vertical Front

The five prior horizontal fronts established Brain's foundational capabilities:
1. **Agentic Systems** — how agents reason, plan, and act
2. **Evaluation & Benchmarking** — how to measure correctness and quality
3. **Memory / RAG / Knowledge Architecture** — how to store and retrieve knowledge
4. **Security / Governance / Sandboxing** — how to constrain actions safely
5. **Autonomous Coding & Patch Generation** — how to modify code safely

This sixth front applies those horizontal capabilities to a **vertical domain**: financial markets. The goal is not to build a trading engine, but to create a **curated knowledge foundation** that Brain can safely reference when (and only when) explicitly authorized to reason about financial topics.

## Financial Safety Boundary

- **No real trading** in this front
- **No broker/API connections** in this front
- **No executable strategies** in this front
- **No personalized financial advice** in this front
- **No live market data ingestion** in this front
- **No backtest execution** in this front
- All sources are **metadata-only** for books and copyrighted papers
- All broker/API docs are **governance-reference-only**

## Taxonomy (32 Categories)

| Tag | Name | Description |
|-----|------|-------------|
| market_microstructure | Market Microstructure | Order books, liquidity, spreads, execution dynamics |
| asset_classes_and_instruments | Asset Classes and Instruments | Stocks, bonds, commodities, currencies, derivatives |
| equities_etfs | Equities / ETFs | Equity and exchange-traded fund characteristics |
| options_risk | Options Risk | Option Greeks, expiration risk, asymmetric payoffs |
| futures_leverage_risk | Futures / Leverage Risk | Margin, leverage, margin calls, futures contract risk |
| portfolio_construction | Portfolio Construction | Asset allocation, diversification, rebalancing |
| factor_investing | Factor Investing | Value, momentum, size, quality factors and risks |
| statistical_arbitrage_risk | Statistical Arbitrage Risk | Pairs trading, convergence risk, regime breakdown |
| mean_reversion_risk | Mean Reversion Risk | Ornstein-Uhlenbeck assumptions and tail events |
| momentum_risk | Momentum Risk | Momentum crashes, factor crowding, reversal risk |
| volatility_regimes | Volatility Regimes | VIX, GARCH, regime-switching volatility |
| market_regime_detection | Market Regime Detection | Identifying trending vs mean-reverting vs crisis regimes |
| backtesting_validity | Backtesting Validity | In-sample vs out-of-sample, simulation fidelity |
| walk_forward_validation | Walk-Forward Validation | Rolling window validation, embargo, purged k-fold |
| overfitting_data_snooping | Overfitting / Data Snooping | Multiple comparison, p-hacking, Sharpe ratio inflation |
| survivorship_bias | Survivorship Bias | Missing delisted assets, index reconstitution effects |
| look_ahead_bias | Look-Ahead Bias | Using future information in historical simulation |
| transaction_costs | Transaction Costs | Commissions, fees, market impact modeling |
| slippage | Slippage | Execution price deviation from signal price |
| liquidity_risk | Liquidity Risk | Inability to execute at quoted prices |
| position_sizing | Position Sizing | Kelly, fractional Kelly, risk-parity, volatility targeting |
| risk_management | Risk Management | VaR, CVaR, stress testing, tail risk |
| drawdown_control | Drawdown Control | Maximum drawdown limits, circuit breakers |
| stop_loss_risk_exits | Stop-Loss / Risk Exits | Exit rules, trailing stops, time stops |
| capital_allocation | Capital Allocation | Cross-strategy capital allocation, reserves |
| benchmark_comparison | Benchmark Comparison | Alpha, beta, tracking error, information ratio |
| paper_trading_governance | Paper Trading Governance | Rules for simulated-only trading with no real capital |
| broker_api_governance | Broker/API Governance | API access controls, credential isolation, rate limits |
| financial_data_quality | Financial Data Quality | Splits, dividends, corporate actions, survivorship, lookahead |
| financial_action_approval_gates | Financial Action Approval Gates | Human-in-the-loop for any financial decision |
| compliance_regulatory_awareness | Compliance / Regulatory Awareness | SEC, FINRA, CFTC, MiFID rules and investor protections |
| non_personalized_financial_education_boundary | Non-Personalized Financial Education Boundary | Strict separation between education and personalized advice |

## Source Acceptance Criteria

**Must have:**
- Attribution (authors or organization)
- Title
- Public URL or documentation URL
- License or legal status known
- Expected learning value description
- Specific brain capability target
- Safety score estimate >= 78
- No critical risk flags
- Not a guaranteed-return claim
- Not a signal-selling service
- Not a paid alpha newsletter
- Not a Telegram/Discord group
- Not unverifiable PnL claims

**Preferred:**
- Active maintenance or recent publication
- Open license (MIT, Apache, public domain)
- Cross-checkable with at least 2 other sources
- Code examples or test suite visible
- Peer-reviewed or widely cited
- Risk methodology explicitly described
- Bias controls explicitly described
- Data quality methodology described
- Broker/API governance controls described

## Source Rejection Criteria

**Automatic reject:**
- No attribution
- Private/protected content inaccessible without payment
- Illegal or copyright-violating
- Promises guaranteed returns
- Signal-selling or paid alpha claims
- Unverifiable PnL screenshots or claims
- Strategy with no risk methodology
- Backtest with no bias controls
- Encourages leverage without risk controls
- Requires broker credentials or API access in this front
- Requires executing external code in this front
- Personalized financial advice to individuals
- Contradicted by newer official source with no rebuttal
- Abandoned with known security vulnerabilities

Auto-reject score threshold: 55

## Safety Scoring Rubric (25 Dimensions, Max 125)

- attribution_quality (0-5)
- primary_source_quality (0-5)
- technical_depth (0-5)
- financial_method_clarity (0-5)
- risk_method_clarity (0-5)
- backtest_method_clarity (0-5)
- data_quality_clarity (0-5)
- reproducibility (0-5)
- license_clarity (0-5)
- maintenance_status (0-5)
- test_or_example_presence (0-5)
- copyright_safety (0-5)
- relevance_to_brain (0-5)
- risk_of_hype_or_marketing (0-5)
- risk_of_unverifiable_return_claims (0-5)
- risk_of_overfitting (0-5)
- risk_of_data_snooping (0-5)
- risk_of_survivorship_bias (0-5)
- risk_of_lookahead_bias (0-5)
- risk_of_broker_or_execution_risk (0-5)
- risk_of_regulatory_or_compliance_issue (0-5)
- risk_of_personalized_financial_advice (0-5)
- risk_of_unsafe_autonomy (0-5)
- risk_of_vendor_lock_in (0-5)
- risk_of_obsolescence (0-5)

Decision rules:
- **Accept** if score >= 78 and no critical risks
- **Hold** if score 55-77 or metadata incomplete
- **Reject** if score < 55 or critical risk exists

## Contrast Scoring Rubric

Each source is contrasted against at least two other sources of different types:

**Contrast types:**
- Paper vs implementation
- Academic vs regulatory
- Theory vs backtesting framework
- Risk source vs execution source
- Factor paper vs factor library
- Broker docs vs governance controls
- Market microstructure vs data quality
- Portfolio construction vs drawdown control

**Required fields per contrast:**
- confirms
- contradicts
- complements
- unresolved_questions
- confidence_level (low/medium/high)

## Source Summary

**Total sources**: 28  
**Accepted**: 27  
**Hold**: 0  
**Rejected**: 1 (Unknown Trading Blog — guaranteed returns, no attribution)  
**Source groups**: academic_paper, book_metadata, regulatory, repo, docs, framework, internal_reference, standard

### Academic / Book / Paper Sources (Metadata Only)

| Source | Authors | Year | Type | Safety |
|--------|---------|------|------|--------|
| Advances in Financial Machine Learning | Lopez de Prado | 2018 | book_metadata | 82 |
| Evidence-Based Technical Analysis | Aronson | 2006 | book_metadata | 80 |
| Market Microstructure Theory | O'Hara | 1995 | academic_paper | 85 |
| Trading and Exchanges | Harris | 2002 | book_metadata | 83 |
| Algorithmic Trading and DMA | Johnson | 2010 | book_metadata | 81 |
| Fama-French Factor Papers | Fama / French | 1992 | academic_paper | 88 |
| Momentum (Jegadeesh / Titman) | Jegadeesh / Titman | 1993 | academic_paper | 86 |
| Probability of Backtest Overfitting | Bailey et al. | 2016 | academic_paper | 90 |
| Deflated Sharpe Ratio | Lopez de Prado / Bailey | 2014 | academic_paper | 88 |

### Regulatory / Government Sources

| Source | Organization | Type | Safety |
|--------|-------------|------|--------|
| SEC Investor.gov | SEC | regulatory_education | 92 |
| FINRA Investor Alerts | FINRA | regulatory_education | 90 |
| OCC Options Disclosure | Options Clearing Corp | regulatory_disclosure | 91 |
| CFTC Futures Risk | CFTC | regulatory_education | 89 |
| Interactive Brokers API Docs | Interactive Brokers | broker_api_docs | 72 |
| Alpaca API Docs | Alpaca Markets | broker_api_docs | 74 |

### GitHub / Framework / Repo Sources

| Source | Org | Type | Safety |
|--------|-----|------|--------|
| backtrader | backtrader community | backtesting_framework | 70 |
| Zipline Reloaded | Stefan Jansen | backtesting_framework | 76 |
| QuantConnect Lean | QuantConnect | backtesting_framework | 75 |
| vectorbt | vectorbt community | backtesting_framework | 78 |
| PyPortfolioOpt | Robert Martin | portfolio_framework | 80 |
| empyrical | Quantopian / QuantRocket | risk_metrics_library | 76 |
| pyfolio | Quantopian | risk_analytics_library | 70 |
| pandas-market-calendars | community | data_quality_tool | 78 |
| yfinance | Ran Aroussi | data_quality_tool | 68 |
| mlfinlab | Hudson and Thames | ml_finance_framework | 75 |
| statsmodels | statsmodels community | statistical_library | 82 |
| arch | Kevin Sheppard | volatility_modeling | 80 |

### Internal / Standard References

| Source | Type | Safety |
|--------|------|--------|
| Brain Governance Front | internal_reference | 95 |
| Brain Evaluation Front | internal_reference | 95 |
| Brain Memory Front | internal_reference | 95 |
| NIST AI RMF | governance_standard | 88 |

## Brain Financial Capability Map (24 Capabilities)

1. distinguish_education_recommendation
2. reject_guaranteed_returns
3. evaluate_market_data_quality
4. identify_backtest_bias
5. evaluate_transaction_costs
6. evaluate_liquidity_risk
7. evaluate_position_sizing
8. evaluate_drawdown_control
9. evaluate_benchmark_relative
10. evaluate_overfitting
11. evaluate_walk_forward
12. evaluate_market_regime
13. evaluate_factor_exposure
14. evaluate_options_leverage
15. evaluate_broker_governance
16. design_paper_trading
17. design_financial_approval
18. prevent_real_orders
19. produce_risk_scorecards
20. prepare_sandbox
21. decide_hypothesis
22. integrate_security
23. integrate_evaluation
24. integrate_memory

## Cross-Source Contrast Matrix (10 Pairs)

1. **Advances in ML Finance vs Probability of Backtest Overfitting** — Book vs paper. Both agree overfitting is the primary danger. Book provides implementation; paper provides mathematical rigor.
2. **Market Microstructure Theory vs Trading and Exchanges** — Theory vs practitioner. Both agree market impact and liquidity are central. Theory provides formal models; practitioner provides trading floor perspective.
3. **backtrader vs Zipline Reloaded** — Framework vs framework. Both provide event-driven backtesting. backtrader is simpler; Zipline has pipeline API.
4. **Fama-French vs Jegadeesh-Titman** — Factor paper vs factor paper. Both provide empirical evidence. Fama-French emphasize value/size; Jegadeesh-Titman emphasize momentum (which Fama was initially skeptical of).
5. **SEC Investor.gov vs FINRA Alerts** — Regulatory education vs warnings. Both stress non-personalized education and risk disclosure. SEC provides broad education; FINRA provides specific product warnings.
6. **IB API Docs vs Alpaca API Docs** — Broker API vs broker API. Both provide paper trading modes and rate limiting. IB has more asset classes; Alpaca has simpler API.
7. **empyrical vs PyPortfolioOpt** — Risk metrics vs portfolio construction. Both assume risk must be quantified before optimization. empyrical measures; PyPortfolioOpt uses measures to construct portfolios.
8. **yfinance vs pandas-market-calendars** — Data source vs data quality tool. yfinance has known data quality issues; pandas-market-calendars helps prevent some biases but not all.
9. **vectorbt vs Probability of Backtest Overfitting** — Framework vs academic paper. vectorbt explicitly warns about overfitting, consistent with Bailey et al.
10. **Brain Governance Front vs NIST AI RMF** — Internal governance vs external standard. Both require approval gates and risk assessment before action.

## Overfitting Risks

All backtesting frameworks in this plan are marked with overfitting_risk >= medium because:
- Any backtesting tool can be misused to data-snoop
- Brain must learn to detect overfitting before trusting any backtest
- Academic sources (Bailey, Lopez de Prado) provide the mathematical controls

## Backtest Bias Risks

The taxonomy explicitly includes:
- overfitting_data_snooping
- survivorship_bias
- look_ahead_bias
- backtesting_validity

Every backtesting framework source is cross-checked with at least one bias-control academic source.

## Trading Execution Risks

- No source in this plan enables real trading
- Broker API docs (IB, Alpaca) are governance-reference-only
- All broker sources have trading_execution_risk = medium (they describe how trading works, but this front does not connect)
- Brain capability `prevent_real_orders` is a hard block

## Personalized Advice Risks

- All regulatory sources explicitly state they are non-personalized
- Brain capability `distinguish_education_recommendation` is trained to separate education from advice
- Forbidden fields include `personalized_recommendation`
- Unknown Trading Blog was rejected for personalized advice risk

## Broker / API Governance Risks

- IB and Alpaca docs are included for governance patterns only
- No credentials, no connection, no execution in this front
- `broker_api_governance` and `financial_action_approval_gates` taxonomy categories ensure future governance

## Data Quality Risks

- yfinance is accepted with data_quality_risk = high as a cautionary example
- pandas-market-calendars is accepted as a quality control tool
- All academic sources discuss data quality methodology

## Copyright Constraints

- All books are metadata-only (title, authors, year, URL, learning value)
- No book content is copied
- Academic papers with open access (arXiv, SSRN) are metadata-only
- Copyright risk is marked medium for books, low for open-access papers and open-source repos

## Dry-Run-Only Confirmation

- ingestion_status: dry_run_only
- memory_mutated: False
- faiss_mutated: False
- trading_enabled: False
- broker_connected: False

## Memory / FAISS Immutability Proof

| Metric | Before | After | Status |
|--------|--------|-------|--------|
| semantic_memory.jsonl lines | 1710 | 1710 | unchanged |
| semantic_memory.jsonl SHA | 655d323... | 655d323... | unchanged |
| FAISS index SHA | b7b755c... | b7b755c... | unchanged |
| FAISS ids SHA | 0043623... | 0043623... | unchanged |
| FAISS ids count | 1611 | 1611 | unchanged |

## Tests Result

- py_compile: PASS
- smoke tests: 63 passed / 0 failed

## Limitations

- No live market data fetched
- No real backtests executed
- No broker APIs connected
- No strategies executed
- No semantic memory ingestion
- No FAISS promotion
- Financial sources are metadata summaries only
- Book content not copied
- Full paper content not downloaded
- Next front requires explicit operator approval before any ingestion or execution

## Next Recommended Front

**FRONT-EXTERNAL-CURATED-LEARNING-CONTROLLED-INGESTION-AUTHORIZATION-01**

This front will remain LOCKED until explicitly approved by the operator. It would cover:
- Controlled ingestion of curated sources into semantic memory
- Operator review queue for financial sources
- Approval gates before any financial knowledge promotion
- FAISS promotion dry-run for financial embeddings
- No real trading still

---

*End of canonical document for FRONT-EXTERNAL-CURATED-LEARNING-FINANCIAL-MOTOR-TRADING-INTELLIGENCE-01*
