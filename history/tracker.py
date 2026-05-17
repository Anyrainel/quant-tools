"""Decision tracking and outcome recording.

Append-only log of decisions and their eventual outcomes.
The raw material for reflection — not the reflection itself.

Usage:
    history/tracker.py record --rule R-008 --action increase --target GLD ...
    history/tracker.py evaluate --decision-id d-20260516220000 --target-return 5.2 ...
    history/tracker.py list --status open
    history/tracker.py show d-20260516220000
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import click

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "history"
DECISIONS = HISTORY / "decisions.jsonl"
OUTCOMES = HISTORY / "outcomes.jsonl"

# ── Data Models ──────────────────────────────────────────────────────────────


@dataclass
class Decision:
    """A decision/recommendation at a point in time.
    
    Captures what was recommended, why, and what was expected.
    Written when the decision is made (before outcome is known).
    """
    id: str
    date: str  # ISO date
    rule_id: str  # e.g. "R-008", "dalio/08/gold-real-assets"
    action: str  # "increase", "decrease", "hold", "exit", "enter"
    target: str  # ticker or asset class, e.g. "GLD", "gold", "us_equity"
    
    # Why
    basis_signals: list[str] = field(default_factory=list)
    # e.g. ["gold_yoy>40%", "debt_revenue>650%", "dxy<100"]
    basis_principles: list[str] = field(default_factory=list)
    # e.g. ["dalio/atoms/a-00042", "dalio/03/gold-as-tail-hedge"]
    
    # Expectations (what we think will happen)
    expected_regime_shift: Optional[str] = None
    # e.g. "inflation_regime: stable→acute"
    expected_timeframe_days: int = 30
    expected_confidence: str = "medium"  # low | medium | high
    
    # Portfolio impact
    portfolio_delta: Optional[dict] = None
    # e.g. {"GLD": {"before": 0.10, "after": 0.15}}
    
    # Meta
    confidence: str = "medium"
    source: str = "agent"  # agent | manual | cron
    tags: list[str] = field(default_factory=list)
    notes: Optional[str] = None  # freeform context at decision time
    
    # Status tracking
    status: str = "open"  # open | evaluated | closed | overridden
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "Decision":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Outcome:
    """The result of a decision, recorded after the fact.
    
    Captures what actually happened vs what was expected.
    Written when the decision is evaluated (after timeframe elapsed).
    """
    id: str  # same as Decision.id
    decision_date: str
    evaluation_date: str
    
    # What happened
    actual_regime: Optional[dict] = None
    # e.g. {"debt_cycle": "late", "stress": "stable", "inflation": "acute"}
    
    # Price action
    target_return_pct: Optional[float] = None
    benchmark_return_pct: Optional[float] = None
    # benchmark = representative ticker or asset class index
    
    # Did the expectation hold?
    regime_prediction_correct: Optional[bool] = None
    direction_correct: Optional[bool] = None  # action was right direction
    magnitude_correct: Optional[bool] = None  # magnitude roughly right
    
    # Principle validation
    principle_holds: Optional[bool] = None
    # Did the underlying principle prove valid?
    
    # Pain / reflection (raw material, not synthesized)
    surprise: Optional[str] = None
    # What happened that we didn't expect?
    lesson: Optional[str] = None
    # What should we learn from this?
    
    # Meta
    was_correct: Optional[bool] = None  # overall judgment
    override_reason: Optional[str] = None  # if manually overridden
    tags: list[str] = field(default_factory=list)
    notes: Optional[str] = None  # freeform context at evaluation time
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "Outcome":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ensure_history():
    HISTORY.mkdir(exist_ok=True)
    DECISIONS.touch()
    OUTCOMES.touch()


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append_jsonl(path: Path, record: dict):
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ── CLI ──────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """Decision tracking and outcome recording. Raw material for reflection."""
    _ensure_history()


@cli.command()
@click.option("--rule", required=True, help="Rule or principle ID that fired")
@click.option("--action", required=True, type=click.Choice(["increase", "decrease", "hold", "exit", "enter"]))
@click.option("--target", required=True, help="Ticker or asset class")
@click.option("--confidence", default="medium", type=click.Choice(["low", "medium", "high"]))
@click.option("--signals", help="Comma-separated signals that triggered")
@click.option("--principles", help="Comma-separated principle IDs")
@click.option("--expected-shift", help="Expected regime shift")
@click.option("--timeframe", default=30, help="Expected evaluation timeframe in days")
@click.option("--tag", multiple=True, help="Tags for categorization")
@click.option("--notes", help="Freeform notes about this decision")
def record(rule, action, target, confidence, signals, principles, expected_shift, timeframe, tag, notes):
    """Record a new decision/recommendation."""
    decision = Decision(
        id=f"d-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        date=date.today().isoformat(),
        rule_id=rule,
        action=action,
        target=target,
        basis_signals=signals.split(",") if signals else [],
        basis_principles=principles.split(",") if principles else [],
        expected_regime_shift=expected_shift,
        expected_timeframe_days=timeframe,
        expected_confidence=confidence,
        confidence=confidence,
        tags=list(tag),
        notes=notes,
    )
    _append_jsonl(DECISIONS, decision.to_dict())
    click.echo(f"Recorded {decision.id}: {rule} → {action} {target} ({confidence})")


@cli.command()
@click.option("--decision-id", required=True, help="Decision ID to evaluate")
@click.option("--target-return", type=float, help="Actual return % of target")
@click.option("--benchmark-return", type=float, help="Benchmark return %")
@click.option("--regime-correct/--regime-wrong", default=None, help="Was regime prediction correct?")
@click.option("--direction-correct/--direction-wrong", default=None, help="Was direction correct?")
@click.option("--principle-holds/--principle-fails", default=None, help="Did principle hold?")
@click.option("--surprise", help="What surprised us?")
@click.option("--lesson", help="What did we learn?")
@click.option("--correct/--incorrect", default=None, help="Overall judgment")
@click.option("--notes", help="Freeform notes about this outcome")
def evaluate(decision_id, target_return, benchmark_return, regime_correct, direction_correct,
             principle_holds, surprise, lesson, correct, notes):
    """Record the outcome of a decision."""
    # Find matching decision for date
    decisions = _load_jsonl(DECISIONS)
    matching = [d for d in decisions if d.get("id") == decision_id]
    decision_date = matching[0].get("date", "") if matching else ""
    
    outcome = Outcome(
        id=decision_id,
        decision_date=decision_date,
        evaluation_date=date.today().isoformat(),
        target_return_pct=target_return,
        benchmark_return_pct=benchmark_return,
        regime_prediction_correct=regime_correct,
        direction_correct=direction_correct,
        principle_holds=principle_holds,
        surprise=surprise,
        lesson=lesson,
        was_correct=correct,
        notes=notes,
    )
    _append_jsonl(OUTCOMES, outcome.to_dict())
    click.echo(f"Recorded outcome for {decision_id}")


@cli.command()
@click.option("--status", help="Filter by status: open | evaluated | closed | overridden")
@click.option("--rule", help="Filter by rule ID")
@click.option("--target", help="Filter by target")
@click.option("--limit", default=20, help="Max results")
def list(status, rule, target, limit):
    """List decisions, optionally filtered."""
    decisions = [Decision.from_dict(d) for d in _load_jsonl(DECISIONS)]
    
    if status:
        decisions = [d for d in decisions if d.status == status]
    if rule:
        decisions = [d for d in decisions if d.rule_id == rule]
    if target:
        decisions = [d for d in decisions if d.target == target]
    
    decisions = decisions[-limit:]
    
    if not decisions:
        click.echo("No decisions found.")
        return
    
    click.echo(f"\n{'ID':<20} {'Date':<12} {'Action':<10} {'Target':<12} {'Status':<12} {'Rule'}")
    click.echo("-" * 80)
    for d in decisions:
        click.echo(f"{d.id:<20} {d.date:<12} {d.action:<10} {d.target:<12} {d.status:<12} {d.rule_id}")


@cli.command()
@click.argument("decision_id")
def show(decision_id):
    """Show full details of a decision and its outcome."""
    decisions = {d["id"]: d for d in _load_jsonl(DECISIONS)}
    outcomes = {o["id"]: o for o in _load_jsonl(OUTCOMES)}
    
    if decision_id not in decisions:
        click.echo(f"Decision {decision_id} not found.")
        return
    
    d = decisions[decision_id]
    click.echo(f"\nDecision: {decision_id}")
    click.echo(f"  Date: {d['date']}")
    click.echo(f"  Rule: {d['rule_id']}")
    click.echo(f"  Action: {d['action']} {d['target']}")
    click.echo(f"  Confidence: {d['confidence']}")
    click.echo(f"  Expected shift: {d.get('expected_regime_shift', 'N/A')}")
    click.echo(f"  Timeframe: {d.get('expected_timeframe_days', 'N/A')} days")
    click.echo(f"  Basis signals: {', '.join(d.get('basis_signals', []))}")
    click.echo(f"  Basis principles: {', '.join(d.get('basis_principles', []))}")
    if d.get('notes'):
        click.echo(f"  Notes: {d['notes']}")
    
    if decision_id in outcomes:
        o = outcomes[decision_id]
        click.echo(f"\nOutcome (evaluated {o['evaluation_date']}):")
        click.echo(f"  Target return: {o.get('target_return_pct', 'N/A')}%")
        click.echo(f"  Benchmark return: {o.get('benchmark_return_pct', 'N/A')}%")
        click.echo(f"  Direction correct: {o.get('direction_correct', 'N/A')}")
        click.echo(f"  Principle holds: {o.get('principle_holds', 'N/A')}")
        click.echo(f"  Overall correct: {o.get('was_correct', 'N/A')}")
        if o.get('surprise'):
            click.echo(f"  Surprise: {o['surprise']}")
        if o.get('lesson'):
            click.echo(f"  Lesson: {o['lesson']}")
        if o.get('notes'):
            click.echo(f"  Notes: {o['notes']}")
    else:
        click.echo("\nOutcome: not yet evaluated")


if __name__ == "__main__":
    cli()
