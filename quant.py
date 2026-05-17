#!/usr/bin/env python3
"""
Quant Tools — Central CLI Entry Point

Thin orchestration layer. All logic lives in the modules.

Usage:
    quant.py signals pull          # fetch indicators → scorecard.json
    quant.py signals score         # classify regime from scorecard.json
    quant.py signals run           # pull + score
    quant.py signals timeline      # build historical timeline

    quant.py portfolio sync        # sync from brokers → holdings.json
    quant.py portfolio show        # display current holdings
    quant.py portfolio rebalance   # check drift vs targets

    quant.py tests backtest        # run strategy backtest
    quant.py tests allweather      # all-weather portfolio sim

    quant.py report generate       # synthesize signals + portfolio → report
    quant.py report check          # evaluate which rules fire

    quant.py full                  # signals run + portfolio sync + report generate
"""

import subprocess
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent


def _run(module: str, *args: str) -> int:
    """Delegate to a module's CLI."""
    cmd = [sys.executable, "-m", module, *args]
    return subprocess.call(cmd, cwd=ROOT)


@click.group()
def cli():
    """Quant Tools — Programmatic inputs for the quant system."""
    pass


# ── Signals ──────────────────────────────────────────────────────────────────

@cli.group()
def signals():
    """Macro regime classification and data ingestion."""
    pass


@signals.command()
def pull():
    """Fetch indicators → data/scorecard.json."""
    return _run("signals.gauge", "pull")


@signals.command()
def score():
    """Classify regime from scorecard.json."""
    return _run("signals.gauge", "score")


@signals.command()
def run():
    """Pull + score in one shot."""
    return _run("signals.gauge", "run")


@signals.command()
def timeline():
    """Build historical macro timeline."""
    return _run("signals.timeline")


# ── Portfolio ────────────────────────────────────────────────────────────────

@cli.group()
def portfolio():
    """Portfolio sync, tracking, and rebalancing."""
    pass


@portfolio.command()
def sync():
    """Sync holdings from brokers → data/holdings.json."""
    return _run("portfolio.broker")


@portfolio.command()
def show():
    """Display current holdings."""
    return _run("portfolio.broker", "--show")


@portfolio.command()
def rebalance():
    """Check allocation drift vs targets."""
    return _run("portfolio.rebalance")


# ── Tests ────────────────────────────────────────────────────────────────────

@cli.group()
def tests():
    """Backtests and strategy validation."""
    pass


@tests.command()
def backtest():
    """Run strategy backtest."""
    return _run("tests.backtest")


@tests.command()
def allweather():
    """All-weather portfolio simulation."""
    return _run("tests.allweather")


# ── Report ────────────────────────────────────────────────────────────────────

@cli.group()
def report():
    """Synthesize and format data for agent consumption."""
    pass


@report.command()
def generate():
    """Synthesize signals + portfolio → structured report."""
    return _run("report.report")


@report.command()
def check():
    """Evaluate which rules fire."""
    return _run("signals.gauge", "check")


# ── Full Pipeline ─────────────────────────────────────────────────────────────

@cli.command()
def full():
    """Run complete pipeline: signals + portfolio + report."""
    click.echo("▶ Running full pipeline...")
    steps = [
        ("signals", "pull"),
        ("signals", "score"),
        ("portfolio", "sync"),
        ("report", "generate"),
    ]
    for group, cmd in steps:
        click.echo(f"\n── {group} {cmd} ──")
        rv = _run(f"{group}.{cmd}" if cmd != "sync" else "portfolio.broker",
                  *("run" if cmd == "pull" and group == "signals" else 
                    "score" if cmd == "score" else
                    "generate" if cmd == "generate" else []))
        if rv != 0:
            click.echo(f"Failed at {group} {cmd}", err=True)
            return rv
    click.echo("\n✓ Full pipeline complete")
    return 0


if __name__ == "__main__":
    cli()
