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
**Status: Process, not code.** The agent writes bull/bear/reflection entries via `tracker.py reflect --topic debate`.

- [ ] Document debate process in HANDBOOK: agent reads wiki, writes FOR/AGAINST/RESOLUTION reflections
- [ ] Future: if multi-agent needed, design independent agents with isolated context windows

### 3. Signal Quality / Staleness Tracking
`signals/gauge.py` pulls data but doesn't systematically track quality.

- [ ] Add staleness detection per indicator (timestamp vs expected update frequency)
- [ ] Add missing data flags (N/A handling, interpolation warnings)
- [ ] Add cross-indicator consistency checks (e.g., gold up + DXY up = flag conflict)
- [ ] Add data source health dashboard
- [ ] Track in TODO: some FRED series lag by weeks/months — need alternative real-time sources
- [ ] Track in TODO: geopolitical signals currently manual — need automated feeds

## Medium Priority

### 4. Portfolio Mix Analysis + Construction
`portfolio/rebalance.py` checks drift, but doesn't deeply analyze risk structure. `portfolio/allweather.py` computes neutral weights but isn't integrated.

- [ ] Merge allweather.py logic into rebalance.py or make rebalance call allweather
- [ ] Add risk-parity analysis (is portfolio balanced by risk contribution?)
- [ ] Add correlation matrix of current holdings
- [ ] Add concentration risk analysis (single name, single sector, single country)
- [ ] Add factor exposure analysis (value, growth, momentum, quality)
- [ ] Add tail risk analysis (skew, kurtosis, VaR, CVaR)
- [ ] Track in TODO: knowing we should increase/decrease an asset class is not enough — need action determination (which holdings, tax considerations, timing)

### 5. allocations.yaml — Relationship to Wiki
`allocations.yaml` is the human's **ephemeral baseline** — neutral weights + regime tilts. It is:
- Versioned in repo (as config)
- Adjustable by human (not immutable like wiki)
- The "implementation" of wiki principles

The wiki provides the "should" (principles for regimes). allocations.yaml provides the "baseline" (human's target). When they conflict:
- Wiki wins for regime-specific guidance
- allocations.yaml wins for long-term baseline
- Agent documents tension via `tracker.py reflect`

### 6. Alert / Notification Layer
`report/monitor.py` detects regime changes. Needs delivery mechanism.

- [ ] Design alert taxonomy: regime shift, data staleness, portfolio drift
- [ ] Add alert delivery (Discord, email, etc. — requires human preference)
- [ ] Add alert suppression (don't spam if same alert fires daily)
- [ ] Add alert escalation (urgent vs routine)

### 7. Report / Feedback Automation
`report/feedback.py` doesn't exist yet.

- [ ] Auto-compare wiki_readings vs outcomes after evaluation period
- [ ] Auto-suggest wiki updates when principles underperform
- [ ] Auto-generate monthly principle health report

### 8. Journal / Audit Logging
`report/journal.py` deleted. Function merged into `history/tracker.py reflect`.

- [ ] Log every agent action: tool run, wiki query, recommendation made
- [ ] Add audit trail for human approval/rejection of recommendations
- [ ] Add structured journal entries for periodic reviews

### 9. Advanced Data Sources
- [ ] Add employment / labor market: unemployment, jobless claims, wage growth (FRED: UNRATE, ICSA, CES0500000003)
- [ ] Add housing / real estate: home prices, mortgage rates (FRED: CSUSHPISA, MORTGAGE30US)
- [ ] Add consumer / business sentiment: PMI, consumer confidence (FRED: NAPM, UMCSENT)
- [ ] Add international / trade: trade balance, foreign Treasury holdings (FRED: BOPGSTB, TIC)
- [ ] Add market internals: advance-decline, new highs/lows (need alternative source — not FRED)
- [ ] Add real-time geopolitical risk feeds (GDELT, ICEWS, or similar)
- [ ] Add options market data (implied volatility, skew)
- [ ] Track in TODO: these require API keys, subscriptions, or scraping infrastructure

## Completed
- [x] Move allweather.py from tests/ to portfolio/ — portfolio construction concept, not a test
- [x] Simplify history/tracker.py — remove flagging, keep only record/evaluate/list/show/reflect/journal
- [x] Add reflection/ branch to wiki for principle evolution
- [x] Split into two repos: macro-principles (wiki) and macro-tools (programmatic)
- [x] Add thin CLI entry point (quant.py)
- [x] Add shared data models in core/models.py
- [x] Remove rules.yaml — principles live in wiki, agent maps signals to wiki directly
- [x] Delete report/debate.py — debate is process, agent uses tracker.py reflect
- [x] Delete report/journal.py — merged into history/tracker.py
- [x] Refactor report/monitor.py — use wiki_readings instead of rules_fired
- [x] Update HANDBOOK — remove fired rules references, add wiki_readings, clarify allocations.yaml relationship
- [x] Add journal.jsonl to history/ for freeform agent reflections
- [x] Add daily + weekly + monthly cron to HANDBOOK

## Open Questions
- How often should tracker.py evaluate run? (monthly? quarterly? event-driven?)
- Should debate be multi-agent or single-agent with forced argumentation?
- What's the right alert delivery mechanism for Vanilain?
- How do we handle tax considerations in action determination?
- What's the threshold for flagging a principle as "needs review"?