# Quant Tools

Programmatic inputs for the quant system. Fetches data, tracks portfolio, generates signals, and produces structured outputs for the guidance engine.

## Components

- **gauge** — Macro regime classification (Dalio-style: debt cycle, stress, inflation)
- **broker** — Portfolio sync from Robinhood + E*TRADE (read-only)
- **rebalance** — Allocation drift detection + trade sizing
- **backtest** — Strategy simulation over historical regimes
- **timeline** — Historical macro data compilation
- **report** — Structured signal output for the guidance engine

## Usage

```bash
cd quant-tools
uv run gauge.py pull    # fetch indicators
uv run gauge.py score    # classify regime
uv run broker.py         # sync portfolio
uv run rebalance.py      # check drift
```

## Data Flow

```
[FRED/YFinance/Brokers] → [gauge/broker] → [scorecard.json + holdings.json]
                                    ↓
                          [rebalance + backtest]
                                    ↓
                          [report] → memory/YYYY-MM-DD.md
```

## Repo

Paired with `quant-principles` (the wiki/knowledge base).
