# Quant System Handbook

**Version:** 2.0  
**Scope:** Practical agent reference. How to run the system, generate decisions, and maintain it.  
**Companion:** BLUEPRINT.md (architecture and vision)

---

## CLI Reference

Entry point: `quant.py` at repo root. All commands delegate to modules.

### Signals

```bash
python quant.py signals pull       # fetch 16 indicators → data/scorecard.json
python quant.py signals score      # classify regime from scorecard.json
python quant.py signals run        # pull + score in one shot
python quant.py signals timeline   # build historical macro timeline
```

Run `signals run` when:
- Generating new guidance
- Data is stale (>24h since last pull)
- Human asks for current regime assessment

### Portfolio

```bash
python quant.py portfolio sync     # sync RH + E*TRADE → data/holdings.json
python quant.py portfolio show     # display current holdings table
python quant.py portfolio rebalance # check allocation drift vs targets
```

Run `portfolio sync` when:
- Generating new guidance
- Human asks for current positions
- After any manual trades (to keep data current)

### Tests

```bash
python quant.py tests backtest     # run strategy backtest
python quant.py tests allweather   # all-weather portfolio simulation
```

Run tests when:
- Evaluating a new strategy idea
- Human asks for historical performance
- Before changing `allocations.yaml` targets

### Report

```bash
python quant.py report generate    # synthesize signals + portfolio → report
python quant.py report check       # evaluate which rules fire
```

Run `report generate` when:
- Producing structured input for guidance generation
- Human asks for a summary

### Full Pipeline

```bash
python quant.py full               # signals run + portfolio sync + report generate
```

Run `full` when:
- Starting a guidance session
- Data is stale across the board

### History / Decision Tracking

```bash
python -m history.tracker record --rule R-008 --action increase --target GLD --confidence high --signals "gold_yoy>40" --principles "dalio/atoms/a-00042"
python -m history.tracker evaluate --decision-id d-20260516220000 --target-return 5.2 --direction-correct --principle-holds
python -m history.tracker flag      # list principles needing review
python -m history.tracker stats     # decision and outcome statistics
```

Run `record` when:
- A recommendation is made
- Any action is taken (even "hold" with reasoning)

Run `evaluate` when:
- The decision's timeframe has elapsed (default 30 days)
- Sufficient price action has occurred to judge

Run `flag` when:
- Generating periodic reviews
- Human asks which principles are underperforming

---

## Decision Workflow

### Standard Flow

1. **Check staleness**
   - Read `data/scorecard.json` timestamp
   - Read `data/holdings.json` timestamp
   - If either >24h old, run `quant.py full`

2. **Read signals**
   - Load `data/scorecard.json`
   - Note regime tuple (debt_cycle, stress, inflation)
   - Note `wiki_readings` from gauge output — these are the wiki chapters to read

3. **Query wiki**
   - Read the chapters listed in `wiki_readings`
   - For each chapter: read index.md for gestalt, then relevant mid files
   - Note relevant atoms by ID
   - The mapping is in `gauge.py check_rules()` — regime axes map to chapters automatically

4. **Read portfolio**
   - Load `data/holdings.json`
   - Load `portfolio/allocations.yaml` for neutral weights + regime tilts
   - Compute target allocation: neutral + tilts for current regime
   - Compare to actual holdings
   - Note drift, concentration, drawdown

5. **Generate recommendations**
   - Cross-reference wiki principles with computed target allocation
   - The wiki provides the "should" (principles for this regime)
   - allocations.yaml provides the "baseline" (human's neutral + tilts)
   - When they conflict: wiki wins for regime-specific guidance, allocations.yaml wins for long-term baseline
   - Document any tension in `history/tracker.py reflect`
   - Produce specific actions (increase/decrease/hold/exit/enter) with targets
   - Assign confidence (low/medium/high)
   - Document reasoning: which signals, which principles, which expectations

6. **Record decision**
   - Run `history.tracker record` with rule, action, target, basis
   - Include expected regime shift and timeframe
   - This is MANDATORY — no recommendation without a record

7. **Present to human**
   - Structured summary: regime, portfolio state, recommendations, confidence
   - Wait for approval before any action

### Periodic Review Flow (Monthly)

1. Run `history.tracker stats` — overall accuracy
2. Run `history.tracker flag` — principles needing review
3. Read `content/reflection/principle-scores.md` — current scores
4. Read `content/reflection/lessons.md` — existing lessons
5. Document new lessons from recent evaluated decisions
6. Update `content/reflection/reviews.md` with monthly entry
7. If principles flagged, propose wiki updates to human

---

## Cron Setup

Use OpenClaw native cron, not Python schedulers. The agent wakes, decides what to run, invokes tools, processes outputs.

### Recommended Jobs

**Daily (6:00 AM PT, market open)**
- Purpose: Fresh data for the day
- Action: Run `quant.py signals run`, save to `data/scorecard.json`
- Delivery: None (silent update, data ready when human asks)
- Note: If regime changed from yesterday, note it in memory

**Weekly (Sunday 6:00 PM PT)**
- Purpose: Full weekly assessment
- Action: Run `quant.py full`, then `quant.py report generate`
- Delivery: Summarize regime + wiki_readings to Discord
- Condition: Only deliver if regime changed or wiki_readings changed since last week

**Monthly (1st of month, 9:00 AM PT)**
- Purpose: Decision review and principle health check
- Action: 
  1. Run `history.tracker list --status overdue` — find unevaluated decisions
  2. Run `history.tracker list --status evaluated` — review recent outcomes
  3. Agent reads outcomes, writes reflections via `tracker.py reflect`
  4. Summarize patterns for human review
- Delivery: Reflection summary + any principles needing attention to Discord

### Cron Payload Example

```json
{
  "kind": "agentTurn",
  "message": "Run daily signal update: quant.py signals run. Save to data/scorecard.json. If regime changed from yesterday, note it in memory."
}
```

See OpenClaw cron docs for exact syntax. Set `sessionTarget: current` to bind to this session.

---

## Data Locations

| File | Path | Purpose | Update Frequency |
|------|------|---------|-----------------|
| scorecard.json | `data/scorecard.json` | Latest regime reading + wiki_readings | Daily (signals run) |
| holdings.json | `data/holdings.json` | Portfolio snapshot | After trades (portfolio sync) |
| decisions.jsonl | `history/decisions.jsonl` | Decision log | Per recommendation |
| outcomes.jsonl | `history/outcomes.jsonl` | Outcome log | Per evaluation |
| journal.jsonl | `history/journal.jsonl` | Agent reflections | As needed |
| allocations.yaml | `portfolio/allocations.yaml` | Target allocation (neutral + tilts) | Manual (human sets) |
| config.yaml | `signals/config.yaml` | Indicator config | Rare (schema change) |

---

## Common Tasks

### "What's the current regime?"
1. Check `data/scorecard.json` staleness
2. If stale, `quant.py signals run`
3. Read scorecard, summarize regime tuple + key indicators
4. Read `wiki_readings` to know which wiki chapters are relevant

### "Should I rebalance?"
1. `quant.py full` (fresh data)
2. `quant.py portfolio rebalance` (drift check)
3. Read wiki chapters from `wiki_readings`
4. Compute target from `allocations.yaml`: neutral + regime tilts
5. Compare current allocation to target
6. Cross-reference with wiki principles
7. When wiki and allocations.yaml conflict: document tension via `tracker.py reflect`
8. Generate specific trade list with sizing
9. `history.tracker record` the recommendation
10. Present to human for approval

### "How accurate are our principles?"
1. `history.tracker list --status evaluated`
2. Read outcomes, compare to expectations
3. Write reflections via `tracker.py reflect`
4. Summarize patterns for human review

### "I want to debate a decision"
1. Read relevant wiki chapters (from `wiki_readings`)
2. Write bull case: `tracker.py reflect --topic debate --content "FOR: ..."`
3. Write bear case: `tracker.py reflect --topic debate --content "AGAINST: ..."`
4. Review both, write synthesis: `tracker.py reflect --topic debate --content "RESOLUTION: ..."`
5. The reflection log is the debate record

### "Add a new signal source"
1. Add fetcher to `signals/` (new .py file or extend gauge.py)
2. Add indicator to `signals/config.yaml`
3. Update `gauge.py check_rules()` to map new indicator to relevant wiki chapters
4. Update BLUEPRINT capabilities section
5. Test with `quant.py signals pull`

### "Add a new wiki branch"
1. Create `content/<branch>/` with index.md
2. Create `sources/<branch>/WIKI.md` with schema
3. Run atomization pipeline per WIKI.md
4. Update `content/index.md` to link branch
5. Update BLUEPRINT system structure section

---

## Troubleshooting

**scorecard.json missing or empty**
- Run `quant.py signals run`
- Check `data/.env` has FRED API key

**holdings.json missing or stale**
- Run `quant.py portfolio sync`
- Check keyring has broker credentials

**broker.py fails with auth error**
- Verify credentials in OS keyring
- Check if 2FA code is current
- Re-run setup per broker.py docstring

**regime classification seems wrong**
- Read `data/scorecard.json` raw indicators
- Check indicator staleness (some FRED series lag)
- Cross-check with alternative sources
- Document discrepancy in `memory/YYYY-MM-DD.md`

**principle flagged but seems correct**
- Read the decisions that invoked it
- Check if context changed (regime shift made principle less relevant)
- Consider splitting principle by regime rather than deprecating
- Document reasoning in `content/reflection/lessons.md`
