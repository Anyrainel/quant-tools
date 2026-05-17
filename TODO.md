# Quant Tools — TODOs

## Dalio-Complete Gaps

### Decision Tracking + Learning (outcomes/)
- [ ] Implement `tracker.py evaluate` — score decisions against market outcomes
- [ ] Implement `tracker.py flag` — flag principles with poor track records
- [ ] Wire tracker into `quant.py full` pipeline
- [ ] Add `outcomes/` to BLUEPRINT.md architecture

### Debate (report/debate.py)
- [ ] Add believability-weighted scoring per "voice"
- [ ] Track historical accuracy of each perspective
- [ ] Generate structured debate output for agent consumption

### Backtests (tests/)
- [ ] `tests/scenarios.py` — scenario engine (2008 replay, Weimar inflation, etc.)
- [ ] Stress test portfolio through synthetic crises
- [ ] Add correlation matrix + risk-weighted bet sizing

### Signals (signals/)
- [ ] Add `threshold_alerts` and `safety_metrics` sections to rules.yaml
- [ ] Implement one-shot alerts (crossing detection)
- [ ] Add portfolio-level safety guards (concentration, drawdown)

### Report (report/)
- [ ] `report/feedback.py` — compare fired rules vs outcomes, flag wiki updates
- [ ] Monthly principle review automation

## Open Questions
- How often should `tracker.py evaluate` run? (monthly? quarterly?)
- What's the threshold for flagging a principle as "needs review"?
- Should flagged principles auto-generate wiki update suggestions?
