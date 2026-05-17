# Quant System Blueprint

**Version:** 2.0  
**Scope:** Agent-facing architecture document. Describes vision, system structure, capabilities, and operating principles.  
**Update trigger:** Any structural change to repos, components, data flows, or responsibilities.

---

## Vision

Build a dalio-complete decision system: a machine that ingests macro signals, applies principles from primary sources, generates portfolio guidance, tracks outcomes, and evolves its principles based on feedback.

The system is designed to scale across:
- **Sources:** Dalio (done), Howard Marks, Reinhart & Rogoff, Ilmanen, and others (future)
- **Signals:** Macro regime (done), geopolitical risk, market technicals, earnings trends (future)
- **Outputs:** Regime classification, allocation drift, scenario analysis, principle evolution (partial)

The system does not trade autonomously. It produces structured recommendations for human approval.

---

## System Structure

Two repos with distinct responsibilities.

### quant-principles (Wiki / Knowledge Base)

**Role:** Immutable principles, condition-indexed, source-grounded.

**Contents:**
- `content/dalio/` — 9 chapters, 270+ atoms, Dalio sources
- `content/reflection/` — Decision reviews, principle scores, lessons, periodic reviews
- `sources/<branch>/WIKI.md` — Schema and pipeline contract per branch
- Quartz static site → Cloudflare Pages

**Boundaries:**
- Contains no executable code
- Contains no portfolio data
- Contains no API keys or credentials
- Principles are source-grounded (verbatim quotes, citations)

**Future branches:** Add as siblings under `content/`. Each branch gets its own `sources/<branch>/WIKI.md` schema. Follow the dalio pattern: atomize → cluster → route → synthesize → lint.

### quant-tools (Programmatic Inputs)

**Role:** Fetch data, classify regimes, track portfolios, generate reports, record outcomes.

**Modules:**
- `signals/` — Macro regime gauge, timeline, config, rules
- `portfolio/` — Broker sync, drift detection, allocation config
- `tests/` — Backtests, strategy validation, scenario analysis (partial)
- `report/` — Synthesize signals + portfolio → structured agent input
- `history/` — Decision tracking, outcome recording, principle scoring
- `core/` — Shared models (RegimeReading, Holding, PortfolioSnapshot, SignalReport, Decision, Outcome, PrincipleScore), cache layer

**Data outputs (runtime, gitignored):**
- `data/scorecard.json` — latest regime reading
- `data/holdings.json` — portfolio snapshot
- `history/decisions.jsonl` — append-only decision log
- `history/outcomes.jsonl` — append-only outcome log

**Entry point:** `quant.py` — thin CLI that delegates to modules. See HANDBOOK.md for usage.

---

## Capabilities

### Current

**Knowledge:**
- Dalio branch: debt cycles, deleveraging, currency systems, sovereign stress, geopolitical cycles, asset positioning, investing principles
- Reflection branch: decision logging, principle scoring, lesson capture, review templates

**Tools:**
- `gauge.py` — 16-indicator regime classifier (debt cycle, stress, inflation)
- `broker.py` — Read-only sync from Robinhood + E*TRADE
- `rebalance.py` — Allocation drift vs targets
- `report.py` — Structured signal output
- `tracker.py` — Decision recording, outcome evaluation, principle flagging

**Automation:**
- None currently scheduled. Cron setup described in HANDBOOK.md.

### Gaps (dalio-complete)

- `tests/scenarios.py` — Stress test portfolio through synthetic crises (Weimar, 2008, etc.)
- `report/debate.py` — Believability-weighted multi-perspective analysis
- `report/feedback.py` — Auto-compare fired rules vs outcomes, suggest wiki updates
- Threshold alerts and safety metrics in `signals/rules.yaml`
- Automated principle evolution pipeline (flagged principles → wiki update suggestions)

---

## Operating Principles

### Do

- Update this BLUEPRINT immediately on any structural change
- Log all significant changes in `memory/YYYY-MM-DD.md`
- Run `quant.py full` before generating guidance if data is stale (>24h)
- Record every recommendation via `history/tracker.py record`
- Evaluate decisions when their timeframe elapses
- Flag principles below 50% accuracy for human review
- Cross-reference wiki atoms by ID, not by memory
- Keep private financial data in this workspace; never commit to public repos

### Do Not

- Trade, move money, or send anything external without explicit human approval
- Duplicate principle content between wiki branches
- Run broker sync without confirming read-only safeguards
- Let signal data go stale without noting it in the report
- Silently override rules when they conflict; document the tension
- Add new wiki branches without updating BLUEPRINT
- Let the CLI grow complex; if it does, the modules need better abstraction

### Decision Authority

- **Agent can:** Run tools, read data, generate recommendations, record decisions, flag principles
- **Human must:** Approve trades, approve wiki structural changes, approve principle deprecation
- **Either can:** Update `allocations.yaml` targets, run backtests, review reports

---

## Changelog

- `2026-05-16` — v2.0. Restructured as two-repo system. Added reflection branch, history tracking, thin CLI. Removed ASCII diagrams, made agent-facing.
- `2026-05-16` — v1.1. Split quant-principles and quant-tools repos.
- `2026-05-16` — v1.0. Initial blueprint.
