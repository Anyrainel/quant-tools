#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
journal.py — Decision journal.

Create, review, and list trading decision entries.
Entries are stored as YAML in data/decisions/ and mirrored as Markdown in
content/dalio/decisions/.

Usage:
    journal.py create --ticker GLD --action buy --size 30000 --thesis "..." --timeframe 90d
    journal.py review D-001 --outcome "..." --process-score 4
    journal.py list [--json]
"""

import json
from datetime import date, timedelta
from pathlib import Path

import click
import yaml

PROJECT = Path(__file__).resolve().parents[2]
DATA = PROJECT / "data"
SCORECARD_JSON = DATA / "scorecard.json"
DECISIONS_DIR = DATA / "decisions"
DECISIONS_VAULT = PROJECT / "content" / "dalio" / "decisions"


# ── Helpers ───────────────────────────────────────────────────────────────────


def load_scorecard() -> dict:
    if SCORECARD_JSON.exists():
        return json.loads(SCORECARD_JSON.read_text())
    return {}


def next_decision_id() -> str:
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(DECISIONS_DIR.glob("D-*.yaml"))
    if not existing:
        return "D-001"
    last = existing[-1].stem
    n = int(last.split("-")[1]) + 1
    return f"D-{n:03d}"


def load_decision(decision_id: str) -> dict:
    path = DECISIONS_DIR / f"{decision_id}.yaml"
    if not path.exists():
        raise click.ClickException(f"Decision {decision_id} not found at {path}")
    return yaml.safe_load(path.read_text())


def save_decision(d: dict) -> Path:
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = DECISIONS_DIR / f"{d['id']}.yaml"
    path.write_text(yaml.dump(d, default_flow_style=False, allow_unicode=True))
    return path


def write_decision_md(d: dict) -> Path:
    DECISIONS_VAULT.mkdir(parents=True, exist_ok=True)
    md_path = DECISIONS_VAULT / f"{d['id']}.md"
    status = "open" if d.get("outcome") is None else "closed"
    r = d.get("regime_at_decision", {})
    rules_str = ", ".join(d.get("rules_firing", []))

    lines = [
        "---",
        f"id: {d['id']}",
        f"date: {d['date']}",
        f"ticker: {d['ticker']}",
        f"action: {d['action']}",
        f"status: {status}",
        f"timeframe: {d['timeframe']}",
        "---",
        "",
        f"# {d['id']}: {d['action'].upper()} {d['ticker']}",
        "",
        (
            f"**Date:** {d['date']} | **Size:** {d.get('size', 'N/A')}"
            f" | **TF:** {d['timeframe']} | **SL:** {d.get('stoploss') or 'None'}"
        ),
        "",
        "## Thesis",
        "",
        d.get("thesis", ""),
        "",
        "## Regime at Decision",
        "",
        (
            f"- Cycle/Stress/Inflation: ({r.get('cycle_stage', '?')}, "
            f"{r.get('stress_direction', '?')}, {r.get('inflation_regime', '?')})"
        ),
    ]
    if rules_str:
        lines.append(f"- Rules firing: {rules_str}")
    if d.get("analog"):
        lines.append(f"\n**Historical Analog:** {d['analog']}")
    if d.get("outcome"):
        lines += [
            "",
            "## Outcome",
            "",
            d["outcome"],
            "",
            f"**Process Score:** {d.get('process_score', '?')}/5",
        ]
        if d.get("notes"):
            lines += ["", "## Lessons", "", d["notes"]]
    lines.append("")
    md_path.write_text("\n".join(lines))
    return md_path


def parse_timeframe_days(tf: str) -> int:
    tf = tf.strip().lower()
    if tf.endswith("y"):
        return int(tf[:-1]) * 365
    if tf.endswith("m"):
        return int(tf[:-1]) * 30
    if tf.endswith("d"):
        return int(tf[:-1])
    return 90


# ── CLI ───────────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """Decision journal — create, review, and list trade decisions."""
    pass


@cli.command()
@click.option("--ticker", prompt="Ticker", help="Asset ticker (e.g. GLD, BTC)")
@click.option(
    "--action",
    prompt="Action",
    type=click.Choice(["buy", "sell", "hold", "trim", "add"]),
    help="Trade action",
)
@click.option("--size", prompt="Size (e.g. $12,000 or 100 shares)", help="Dollar amount or share count")
@click.option("--thesis", prompt="Thesis (1-2 sentences)", help="Reason for the trade")
@click.option("--timeframe", prompt="Timeframe (e.g. 30d, 90d, 1y)", default="90d", help="Evaluation window")
@click.option("--stoploss", default=None, help="Stop loss price or condition")
@click.option("--analog", default=None, help="Historical analog (e.g. '2008 deleveraging')")
def create(ticker, action, size, thesis, timeframe, stoploss, analog):
    """Create a new decision journal entry."""
    sc = load_scorecard()
    regime = sc.get("regime", {})
    fired_rules = sc.get("rules_fired", [])
    rules_ids = [r["id"] for r in fired_rules] if fired_rules else []

    decision_id = next_decision_id()
    today = str(date.today())

    d = {
        "id": decision_id,
        "date": today,
        "ticker": ticker.upper(),
        "action": action,
        "size": size,
        "thesis": thesis,
        "timeframe": timeframe,
        "stoploss": stoploss,
        "analog": analog,
        "regime_at_decision": {
            "cycle_stage": regime.get("cycle_stage"),
            "stress_direction": regime.get("stress_direction"),
            "inflation_regime": regime.get("inflation_regime"),
        },
        "rules_firing": rules_ids,
        "outcome": None,
        "outcome_date": None,
        "process_score": None,
        "notes": None,
    }

    yaml_path = save_decision(d)
    md_path = write_decision_md(d)
    print(f"\n✅ Decision {decision_id} saved.")
    print(f"   YAML: {yaml_path}")
    print(f"   Vault: {md_path}")
    print(
        f"   Regime: ({regime.get('cycle_stage')}, {regime.get('stress_direction')}, {regime.get('inflation_regime')})"
    )
    if rules_ids:
        print(f"   Rules firing: {', '.join(rules_ids)}")


@cli.command()
@click.argument("decision_id")
@click.option("--outcome", prompt="Outcome (what happened?)", help="Result of the trade/decision")
@click.option(
    "--process-score",
    prompt="Process score (1-5)",
    type=click.IntRange(1, 5),
    help="Quality of reasoning (1=poor, 5=excellent)",
)
@click.option("--notes", prompt="Lessons learned", default="", help="Lessons learned")
def review(decision_id, outcome, process_score, notes):
    """Review and close a decision journal entry."""
    decision_id = decision_id.upper()
    d = load_decision(decision_id)
    d["outcome"] = outcome
    d["outcome_date"] = str(date.today())
    d["process_score"] = process_score
    d["notes"] = notes if notes else None

    save_decision(d)
    write_decision_md(d)
    print(f"\n✅ {decision_id} reviewed and closed.")
    print(f"   Outcome: {outcome}")
    print(f"   Process score: {process_score}/5")


@cli.command("list")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON")
def list_decisions(as_json):
    """List all decisions with open/closed/overdue status."""
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(DECISIONS_DIR.glob("D-*.yaml"))

    if not files:
        print("No decisions recorded yet. Use 'journal.py create' to create one.")
        return

    today = date.today()
    records = []

    for f in files:
        d = yaml.safe_load(f.read_text())
        decision_date = date.fromisoformat(str(d["date"])[:10])
        tf_days = parse_timeframe_days(str(d.get("timeframe", "90d")))
        due = decision_date + timedelta(days=tf_days)

        if d.get("outcome") is not None:
            status = "closed"
        elif today > due:
            status = "overdue"
        else:
            days_left = (due - today).days
            status = f"open ({days_left}d)"

        records.append(
            {
                "id": d["id"],
                "date": str(d["date"]),
                "ticker": d["ticker"],
                "action": d["action"],
                "timeframe": str(d.get("timeframe", "?")),
                "status": status,
                "thesis": (d.get("thesis") or "")[:60],
                "regime": d.get("regime_at_decision", {}),
            }
        )

    if as_json:
        print(json.dumps(records, indent=2))
        return

    print(f"\n{'ID':<8} {'Date':<12} {'Ticker':<8} {'Action':<6} {'TF':<6} {'Status':<15} {'Thesis'}")
    print("-" * 85)
    for rec in records:
        print(
            f"{rec['id']:<8} {rec['date']:<12} {rec['ticker']:<8}"
            f" {rec['action']:<6} {rec['timeframe']:<6} {rec['status']:<15} {rec['thesis']}"
        )
    print()


if __name__ == "__main__":
    cli()
