"""Decision and outcome tracker.

Records every recommendation, its basis, and its eventual outcome.
The feedback loop for principle evolution.

Usage:
    tracker.py record --rule R-008 --action "increase gold" --confidence high
    tracker.py evaluate --days 30  # score recent decisions
    tracker.py flag  # list principles that need review
"""

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import click

from core.models import SignalReport

DATA = Path(__file__).resolve().parents[1] / "data"
DECISIONS = DATA / "decisions.jsonl"


def _load_decisions() -> list[dict]:
    if not DECISIONS.exists():
        return []
    return [json.loads(line) for line in DECISIONS.read_text().splitlines() if line.strip()]


@click.group()
def cli():
    """Track decisions and outcomes for principle evolution."""
    pass


@cli.command()
@click.option("--rule", required=True, help="Rule ID that fired")
@click.option("--action", required=True, help="Recommended action")
@click.option("--confidence", default="medium", help="low | medium | high")
@click.option("--basis", help="Signals or principles that triggered this")
@click.option("--portfolio-delta", help="JSON of intended portfolio changes")
def record(rule, action, confidence, basis, portfolio_delta):
    """Record a new decision/recommendation."""
    entry = {
        "id": f"d-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "date": date.today().isoformat(),
        "rule": rule,
        "action": action,
        "confidence": confidence,
        "basis": basis,
        "portfolio_delta": portfolio_delta,
        "status": "open",
        "outcome": None,
        "outcome_date": None,
        "was_correct": None,
    }
    with DECISIONS.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    click.echo(f"Recorded {entry['id']}: {rule} → {action}")


@cli.command()
@click.option("--days", default=30, help="Evaluate decisions from last N days")
def evaluate(days):
    """Score recent decisions against market outcomes."""
    # TODO: implement outcome scoring
    # - Load decisions from last N days
    # - Fetch price action for affected tickers
    # - Compare predicted vs actual regime evolution
    # - Update was_correct field
    click.echo(f"Evaluating decisions from last {days} days...")
    click.echo("TODO: implement outcome scoring")


@cli.command()
def flag():
    """List principles/rules that need human review."""
    # TODO: flag rules with poor track records
    # - Load all closed decisions
    # - Group by rule, compute accuracy
    # - Flag rules below threshold
    decisions = _load_decisions()
    click.echo(f"Loaded {len(decisions)} decisions")
    click.echo("TODO: implement flagging logic")


if __name__ == "__main__":
    cli()
