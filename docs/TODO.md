# Quant Tools — TODOs

## High Priority

### 1. Backtests — Enrich and Harden
Current backtests (`tests/backtest.py`, `tests/backtest_full.py`) need to reach quant-system standards.

- [ ] Add regime-aware backtesting — run strategies conditioned on historical regime classifications
- [ ] Add transaction cost modeling (slippage, fees, market impact)
- [ ] Add drawdown analysis (max drawdown, recovery time, underwater curve)
- [ ] Add Sharpe, Sortino, Calmar ratios
- [ ] Add rolling window analysis (12mo, 36mo, 60mo)
- [ ] Add correlation matrix and diversification benefit measurement
- [ ] Add benchmark comparison (vs buy-and-hold, vs all-weather)
- [ ] Add Monte Carlo simulation for path dependency
- [ ] Add walk-forward optimization framework
- [ ] Track in TODO: some signals lack historical data for long backtests — need better data sources

### 2. Debate / Multi-Perspective Analysis
`report/debate.py` exists but is skeletal. This is a **process concept**, not a code concept.

- [ ] Design: multi-agent vs single-agent debate
  - Option A: Multiple agents, each with a different lens (macro, technical, fundamental, contrarian)
  - Option B: Single agent, forced to argue both sides before deciding
  - Risk: putting all perspectives in one context window may bias synthesis
- [ ] If multi-agent: define agent roles, process for independent analysis, then weighted aggregation
- [ ] If single-agent: structure as explicit "argue for / argue against / resolution" steps
- [ ] Weighting: by historical accuracy of each perspective (requires tracking)
- [ ] Output: structured debate summary with confidence per perspective
- [ ] Track in TODO: debate is currently only about categorical balance (asset classes). Future: stock selection, timing, etc. will need different debate structure.

### 3. Signal Quality / Staleness Tracking
`signals/gauge.py` pulls data but doesn't systematically track quality.

- [ ] Add staleness detection per indicator (timestamp vs expected update frequency)
- [ ] Add missing data flags (N/A handling, interpolation warnings)
- [ ] Add cross-indicator consistency checks (e.g., gold up + DXY up = flag conflict)
- [ ] Add data source health dashboard
- [ ] Track in TODO: some FRED series lag by weeks/months — need alternative real-time sources
- [ ] Track in TODO: geopolitical signals currently manual — need automated feeds

## Medium Priority

### 4. Portfolio Mix Analysis
`portfolio/rebalance.py` checks drift, but doesn't deeply analyze the portfolio's risk structure.

- [ ] Add risk-parity analysis (is the portfolio actually balanced by risk contribution?)
- [ ] Add correlation matrix of current holdings
- [ ] Add concentration risk analysis (single name, single sector, single country)
- [ ] Add factor exposure analysis (value, growth, momentum, quality)
- [ ] Add tail risk analysis (skew, kurtosis, VaR, CVaR)
- [ ] Track in TODO: knowing we should increase/decrease an asset class is not enough — need action determination (which holdings, tax considerations, timing)

### 5. Rules.yaml Enhancement
`signals/rules.yaml` has 14 rules. Needs versioning and testing infrastructure.

- [ ] Add rule versioning (git tracks history, but rules need semantic versioning)
- [ ] Add rule backtesting — test each rule's historical accuracy
- [ ] Add rule conflict detection (two rules firing opposite actions)
- [ ] Add rule coverage analysis (are there regime states with no firing rule?)
- [ ] Add threshold alerts section (one-shot when indicator crosses threshold)
- [ ] Add safety metrics section (portfolio-level guards)

### 6. Alert / Notification Layer
Not built yet. Agent runs tools but doesn't notify when something important changes.

- [ ] Design alert taxonomy: regime shift, rule fire, data staleness, portfolio drift, principle flag
- [ ] Add alert generation to `report/report.py`
- [ ] Add alert delivery (Discord, email, etc. — requires human preference)
- [ ] Add alert suppression (don't spam if same alert fires daily)
- [ ] Add alert escalation (urgent vs routine)

## Low Priority / Future

### 7. Report / Feedback Automation
`report/feedback.py` doesn't exist yet.

- [ ] Auto-compare fired rules vs outcomes after evaluation period
- [ ] Auto-suggest wiki updates when principles underperform
- [ ] Auto-generate monthly principle health report

### 8. Journal / Audit Logging
`report/journal.py` exists but isn't wired into workflow.

- [ ] Log every agent action: tool run, wiki query, recommendation made
- [ ] Add audit trail for human approval/rejection of recommendations
- [ ] Add structured journal entries for periodic reviews

### 9. Advanced Data Sources
- [ ] Add real-time geopolitical risk feeds (GDELT, ICEWS, or similar)
- [ ] Add market breadth indicators (advance-decline, new highs/lows)
- [ ] Add options flow / sentiment data
- [ ] Add earnings trend and guidance revision data
- [ ] Track in TODO: these require API keys, subscriptions, or scraping infrastructure

## Completed
- [x] Move allweather.py from tests/ to portfolio/ — portfolio construction concept, not a test
- [x] Simplify history/tracker.py — remove flagging, keep only record/evaluate/list/show
- [x] Add reflection/ branch to wiki for principle evolution
- [x] Split into two repos: quant-principles (wiki) and quant-tools (programmatic)
- [x] Add thin CLI entry point (quant.py)
- [x] Add shared data models in core/models.py

## Open Questions
- How often should tracker.py evaluate run? (monthly? quarterly? event-driven?)
- What's the threshold for flagging a principle as "needs review"? (accuracy < 50% over N invocations?)
- Should debate be multi-agent or single-agent with forced argumentation?
- What's the right alert delivery mechanism for Vanilain?
- How do we handle tax considerations in action determination?
