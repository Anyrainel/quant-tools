#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""rebalance.py — Trade list generator.

Given target weights + actual holdings → concrete trade list.
This is the ONLY file that knows about a specific account.

Usage:
    rebalance.py --target FILE --holdings FILE --json
    rebalance.py --target FILE --folio
    rebalance.py --text
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import click
import yaml

MACRO_DIR = Path(__file__).resolve().parents[1] / "portfolio"
DEFAULT_SCORECARD = Path(__file__).resolve().parents[2] / "data" / "scorecard.json"
ALLOCATIONS_YAML = MACRO_DIR / "allocations.yaml"
FOLIO_PY = Path(__file__).resolve().parents[2] / "folio" / "folio.py"
FOLIO_PYTHON = Path(__file__).resolve().parents[2] / "folio" / ".venv" / "bin" / "python3"
BROKER_PY = MACRO_DIR / "broker.py"
HOLDINGS_JSON = Path(__file__).resolve().parents[2] / "data" / "holdings.json"
PYTHON = sys.executable


def load_allocations() -> dict:
    return yaml.safe_load(ALLOCATIONS_YAML.read_text())


def build_ticker_to_class(cfg: dict) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for ac, info in cfg.get("asset_classes", {}).items():
        for t in info.get("tickers", []):
            mapping[t.upper()] = ac
    return mapping


def load_holdings_json(path: str) -> tuple[dict, float, float]:
    """Load holdings JSON: supports both list (broker.py) and dict formats."""
    data = json.loads(Path(path).read_text())
    raw_holdings = data.get("holdings", {})
    raw_cash = data.get("cash", 0.0)
    cash = float(raw_cash.get("total", raw_cash) if isinstance(raw_cash, dict) else raw_cash)
    # Support both list format (from broker.py) and dict format
    if isinstance(raw_holdings, list):
        holdings = {}
        for h in raw_holdings:
            ticker = h.get("ticker", "").upper()
            holdings[ticker] = {
                "value": float(h.get("value", 0)),
                "gain_pct": float(h.get("gain_pct", 0)),
                "asset_class": h.get("asset_class", "other"),
            }
    else:
        holdings = raw_holdings
    raw_total = data.get("total", data.get("total_value", 0))
    total = float(raw_total if raw_total else sum(h["value"] for h in holdings.values()) + cash)
    return holdings, total - cash, cash


def load_holdings_folio(cfg: dict) -> tuple[dict, float, float]:
    """Run folio.py show, parse text output → holdings dict."""
    python_bin = str(FOLIO_PYTHON) if FOLIO_PYTHON.exists() else PYTHON
    if not FOLIO_PY.exists():
        raise click.ClickException(f"folio.py not found at {FOLIO_PY}")

    result = subprocess.run(
        [python_bin, str(FOLIO_PY), "show"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise click.ClickException(f"folio.py failed: {result.stderr.strip()}")

    ticker_to_class = build_ticker_to_class(cfg)
    holdings: dict[str, dict] = {}
    total_invested = 0.0
    cash = 0.0

    for line in result.stdout.splitlines():
        cash_match = re.match(r"^\s*Cash:\s+\$([0-9,]+\.?\d*)", line)
        if cash_match:
            cash = float(cash_match.group(1).replace(",", ""))
            continue

        parts = line.split()
        if len(parts) < 9:
            continue
        ticker = parts[0].upper()
        if not re.match(r"^[A-Z]{1,6}$", ticker):
            continue
        try:
            value = float(parts[-3].replace("$", "").replace(",", ""))
            gain_pct = float(parts[-1].rstrip("%").replace("+", ""))
        except ValueError:
            continue

        ac = ticker_to_class.get(ticker, "cash")
        holdings[ticker] = {"value": value, "gain_pct": gain_pct, "asset_class": ac}
        total_invested += value

    return holdings, total_invested, cash


def compute_current_allocation(holdings: dict, cash: float, total: float) -> dict[str, float]:
    alloc: dict[str, float] = {}
    for info in holdings.values():
        ac = info["asset_class"]
        alloc[ac] = alloc.get(ac, 0.0) + info["value"]
    if cash > 0:
        alloc["cash"] = alloc.get("cash", 0.0) + cash
    return {ac: round(v / total * 100, 1) for ac, v in alloc.items()}


def pick_sell_ticker(asset_class: str, holdings: dict, cfg: dict) -> tuple[str, float | None]:
    tickers_in_class = [t for t, info in holdings.items() if info["asset_class"] == asset_class]
    if not tickers_in_class:
        return "", None
    prefer_loss = cfg.get("rebalance", {}).get("prefer_tax_loss", True)
    if prefer_loss:
        losers = [(t, holdings[t]["gain_pct"]) for t in tickers_in_class if holdings[t].get("gain_pct", 0) < 0]
        if losers:
            losers.sort(key=lambda x: x[1])
            t = losers[0][0]
            return t, holdings[t]["gain_pct"]
    t = max(tickers_in_class, key=lambda x: holdings[x]["value"])
    return t, holdings[t].get("gain_pct")


def pick_buy_ticker(asset_class: str, cfg: dict) -> str:
    tickers = cfg.get("asset_classes", {}).get(asset_class, {}).get("tickers", [])
    return tickers[0] if tickers else ""


def compute_trades(
    current: dict[str, float],
    target: dict[str, float],
    total: float,
    holdings: dict,
    cfg: dict,
) -> list[dict]:
    rb = cfg.get("rebalance", {})
    band = float(rb.get("band_threshold", 2.0))
    max_trade_pct = float(rb.get("max_single_trade_pct", 15.0))

    all_classes = set(list(target.keys()) + list(current.keys()))
    trades = []

    for ac in sorted(all_classes):
        cur_pct = current.get(ac, 0.0)
        tgt_pct = target.get(ac, 0.0)
        drift = cur_pct - tgt_pct  # positive = overweight

        if abs(drift) < band:
            trades.append(
                {
                    "asset_class": ac,
                    "action": "HOLD",
                    "amount": 0.0,
                    "ticker": "",
                    "gain_pct": None,
                    "reason": f"drift {drift:+.1f}% within ±{band}% band",
                    "target_pct": tgt_pct,
                    "current_pct": cur_pct,
                    "drift": round(drift, 2),
                }
            )
        elif drift > 0:
            raw_amount = abs(drift) / 100 * total
            amount = min(raw_amount, max_trade_pct / 100 * total)
            ticker, gain_pct = pick_sell_ticker(ac, holdings, cfg)
            gain_str = f" {gain_pct:+.1f}%" if gain_pct is not None else ""
            reason = f"target {tgt_pct:.1f}% vs current {cur_pct:.1f}%, prefer loser {ticker}{gain_str}"
            trades.append(
                {
                    "asset_class": ac,
                    "action": "SELL",
                    "amount": round(amount, 0),
                    "ticker": ticker,
                    "gain_pct": gain_pct,
                    "reason": reason,
                    "target_pct": tgt_pct,
                    "current_pct": cur_pct,
                    "drift": round(drift, 2),
                }
            )
        else:
            raw_amount = abs(drift) / 100 * total
            amount = min(raw_amount, max_trade_pct / 100 * total)
            ticker = pick_buy_ticker(ac, cfg)
            reason = f"target {tgt_pct:.1f}% vs current {cur_pct:.1f}%"
            trades.append(
                {
                    "asset_class": ac,
                    "action": "BUY",
                    "amount": round(amount, 0),
                    "ticker": ticker,
                    "gain_pct": None,
                    "reason": reason,
                    "target_pct": tgt_pct,
                    "current_pct": cur_pct,
                    "drift": round(drift, 2),
                }
            )

    return trades


def build_output(trades: list[dict], regime: dict | None, conviction: float | None) -> dict:
    active_trades = [t for t in trades if t["action"] != "HOLD"]
    total_sells = sum(t["amount"] for t in active_trades if t["action"] == "SELL")
    total_buys = sum(t["amount"] for t in active_trades if t["action"] == "BUY")

    out_trades = [
        {
            "asset_class": t["asset_class"],
            "action": t["action"],
            "amount": int(t["amount"]),
            "ticker": t["ticker"],
            "reason": t["reason"],
            "target_pct": t["target_pct"],
            "current_pct": t["current_pct"],
            "drift": t["drift"],
        }
        for t in active_trades
    ]

    result: dict = {
        "trades": out_trades,
        "holds": [t["asset_class"] for t in trades if t["action"] == "HOLD"],
        "summary": {
            "total_sells": int(total_sells),
            "total_buys": int(total_buys),
            "net": int(total_sells - total_buys),
            "trade_count": len(active_trades),
        },
    }
    if regime:
        result["regime"] = regime
    if conviction is not None:
        result["conviction"] = conviction
    return result


def print_text(output: dict) -> None:
    regime = output.get("regime", {})
    conviction = output.get("conviction")
    cs = regime.get("cycle_stage", "?")
    sd = regime.get("stress_direction", "?")
    ir = regime.get("inflation_regime", "?")

    header = f"Regime: ({cs}, {sd}, {ir})"
    if conviction is not None:
        header += f" | Conviction: {conviction:.1f}"
    print(f"\n=== REBALANCE PLAN ===\n{header}\n")

    trades = output.get("trades", [])
    holds = output.get("holds", [])

    if trades:
        print(f"{'Asset Class':<22} {'Action':<6} {'Amount':>10}  {'Ticker':<8}  Reason")
        print("─" * 80)
        for t in sorted(trades, key=lambda x: -abs(x["drift"])):
            label = t["asset_class"].replace("_", " ").title()
            amount_str = f"${t['amount']:,.0f}"
            print(f"{label:<22} {t['action']:<6} {amount_str:>10}  {t['ticker']:<8}  {t['reason']}")
    else:
        print("  No trades required — all within band.")

    if holds:
        holds_str = ", ".join(h.replace("_", " ").title() for h in holds)
        print(f"\n  HOLD: {holds_str}")

    s = output["summary"]
    print(f"\n  Sells: ${s['total_sells']:,.0f} | Buys: ${s['total_buys']:,.0f} | Net: ${s['net']:+,.0f}")
    print()


@click.command()
@click.option("--target", "target_file", default=None, help="Path to portfolio.py JSON output")
@click.option("--holdings", "holdings_file", default=None, help="Path to holdings JSON file")
@click.option("--folio", is_flag=True, default=False, help="Load holdings from folio.py")
@click.option("--broker", is_flag=True, default=False, help="Pull live holdings from brokers via broker.py")
@click.option("--scorecard", default=str(DEFAULT_SCORECARD), show_default=True, help="Path to scorecard.json")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON to stdout")
@click.option("--text", "as_text", is_flag=True, default=False, help="Human-readable plan")
def main(target_file, holdings_file, folio, broker, scorecard, as_json, as_text):
    """Generate trade list from target weights vs current holdings."""
    cfg = load_allocations()

    # Load target portfolio
    if target_file:
        portfolio_data = json.loads(Path(target_file).read_text())
    else:
        # Run portfolio.py to get target
        result = subprocess.run(
            [PYTHON, str(MACRO_DIR / "portfolio.py"), "--json"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise click.ClickException(f"portfolio.py failed: {result.stderr.strip()}")
        portfolio_data = json.loads(result.stdout)

    target = portfolio_data.get("target", {})
    regime = portfolio_data.get("regime")
    conviction = portfolio_data.get("conviction")

    # Load holdings
    if broker:
        # Pull live data from brokers, save to data/holdings.json, then load
        result = subprocess.run(
            [PYTHON, str(BROKER_PY), "all", "--save"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise click.ClickException(f"broker.py failed: {result.stderr.strip()}")
        holdings, total_invested, cash = load_holdings_json(str(HOLDINGS_JSON))
    elif folio:
        holdings, total_invested, cash = load_holdings_folio(cfg)
    elif holdings_file:
        holdings, total_invested, cash = load_holdings_json(holdings_file)
    else:
        raise click.ClickException("Provide --holdings FILE, --folio, or --broker flag.")

    total = total_invested + cash
    current = compute_current_allocation(holdings, cash, total)
    trades = compute_trades(current, target, total, holdings, cfg)
    output = build_output(trades, regime, conviction)

    if as_json:
        click.echo(json.dumps(output, indent=2))
    else:
        print_text(output)


if __name__ == "__main__":
    main()
