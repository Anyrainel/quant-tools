# Quant Tools

Programmatic inputs for the quant system. Fetches data, tracks portfolio, generates signals, and produces structured outputs for the guidance engine.

## Structure

```
quant-tools/
├── quant.py              # thin CLI entry point
├── signals/              # macro regime classification + data ingestion
│   ├── gauge.py          # 16-indicator regime classifier
│   ├── timeline.py       # historical macro data
│   ├── config.yaml       # indicator config
│   └── rules.yaml        # regime rules
├── portfolio/            # broker sync + position tracking
│   ├── broker.py         # RH + E*TRADE read-only sync
│   ├── rebalance.py      # drift detection + trade sizing
│   ├── portfolio.py      # portfolio data models
│   └── allocations.yaml  # target allocation config
├── tests/                # backtests + validation
│   ├── backtest.py
│   ├── backtest_full.py
│   ├── alpha.py
│   └── allweather.py
├── report/               # synthesize → agent-ready output
│   ├── report.py         # structured signal report
│   ├── debate.py         # regime debate / tension analysis
│   ├── journal.py        # decision journal
│   └── monitor.py        # ongoing monitoring
├── core/                 # shared infrastructure
│   ├── cache.py          # data caching layer
│   └── models.py         # shared data structures
├── data/                 # runtime outputs (gitignored)
│   ├── scorecard.json    # latest regime reading
│   └── holdings.json     # portfolio snapshot
├── history/              # archived scorecards (gitignored)
└── BLUEPRINT.md          # system architecture
```

## Usage

```bash
# Signals
python quant.py signals pull       # fetch indicators
python quant.py signals score      # classify regime
python quant.py signals run        # pull + score

# Portfolio
python quant.py portfolio sync     # sync from brokers
python quant.py portfolio show     # display holdings
python quant.py portfolio rebalance # check drift

# Tests
python quant.py tests backtest     # run backtest
python quant.py tests allweather   # all-weather sim

# Report
python quant.py report generate    # synthesize report
python quant.py report check       # check fired rules

# Full pipeline
python quant.py full               # signals + portfolio + report
```

## Data Flow

```
[FRED/YFinance/Brokers] → [signals/] → data/scorecard.json
                                    ↓
                          [portfolio/] → data/holdings.json
                                    ↓
                          [report/] → structured output
                                    ↓
                          [Guidance Engine] → memory/YYYY-MM-DD.md
```

## Paired Repo

- **quant-principles** — Wiki/knowledge base (Quartz site)
  https://github.com/Anyrainel/quant-principles

## Cron

Scheduled via OpenClaw native cron. The agent wakes, decides what to run, invokes quant.py commands, and processes outputs.
