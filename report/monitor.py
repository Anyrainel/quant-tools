#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
monitor.py — Regime change detector.

Runs gauge pull+score, diffs against previous scorecard, generates alerts.
Designed for cron. Writes alert JSON to data/alerts/YYYY-MM-DD.json.

Usage:
    monitor.py           # run, compare, output alert JSON
    monitor.py --text    # one-line summary for cron capture
    monitor.py --json    # full alert JSON to stdout
"""

import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import click

PROJECT = Path(__file__).resolve().parents[2]
DATA = PROJECT / "data"
SCORECARD_JSON = DATA / "scorecard.json"
HISTORY_DIR = DATA / "history"
ALERTS_DIR = DATA / "alerts"
PYTHON = sys.executable
MACRO_DIR = Path(__file__).parent


def run_gauge(cmd: str) -> int:
    result = subprocess.run(
        [PYTHON, str(MACRO_DIR / "gauge.py"), cmd],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo(f"gauge.py {cmd} failed: {result.stderr.strip()}", err=True)
    return result.returncode


def load_scorecard() -> dict:
    if SCORECARD_JSON.exists():
        return json.loads(SCORECARD_JSON.read_text())
    return {}


def diff_scorecards(new_sc: dict, prev_sc: dict) -> dict:
    new_regime = new_sc.get("regime", {})
    old_regime = prev_sc.get("regime", {})

    new_list = [new_regime.get(k) for k in ("cycle_stage", "stress_direction", "inflation_regime")]
    old_list = [old_regime.get(k) for k in ("cycle_stage", "stress_direction", "inflation_regime")]
    regime_changed = old_list != new_list

    # Wiki readings changed
    new_readings = set(new_sc.get("wiki_readings", []))
    old_readings = set(prev_sc.get("wiki_readings", []))
    new_wiki = sorted(new_readings - old_readings)
    cleared_wiki = sorted(old_readings - new_readings)

    # Indicator threshold crossings (>10% relative change)
    crossings = []
    new_raw = new_sc.get("raw", {})
    old_raw = prev_sc.get("raw", {})
    for key, ind in new_raw.items():
        val = ind.get("value")
        prev_val = (old_raw.get(key) or {}).get("value")
        if val is not None and prev_val is not None and prev_val != 0:
            pct = abs((val - prev_val) / prev_val) * 100
            if pct > 10:
                crossings.append(
                    {
                        "indicator": key,
                        "old": prev_val,
                        "new": val,
                        "pct_change": round(pct, 1),
                    }
                )

    return {
        "regime_changed": regime_changed,
        "old_regime": old_list,
        "new_regime": new_list,
        "new_wiki_readings": new_wiki,
        "wiki_readings_cleared": cleared_wiki,
        "threshold_crossings": crossings,
    }


def determine_alert_level(diff: dict) -> str:
    if diff["regime_changed"]:
        return "urgent"
    if diff.get("new_wiki_readings") or diff.get("wiki_readings_cleared"):
        return "warning"
    if diff["threshold_crossings"]:
        return "info"
    return "none"


def one_line_summary(today_str: str, alert: dict) -> str:
    level = alert["alert_level"]
    new_regime = alert["new_regime"]
    regime_str = ",".join(str(r) for r in new_regime)
    if level == "none":
        return f"[{today_str}] MONITOR OK — regime=({regime_str}) no changes"
    if level == "info":
        indicators = ", ".join(t["indicator"] for t in alert["threshold_crossings"][:3])
        return f"[{today_str}] MONITOR INFO — {len(alert['threshold_crossings'])} indicator(s) moved >10%: {indicators}"
    if level == "warning":
        new_readings = alert.get("new_wiki_readings", [])
        return f"[{today_str}] MONITOR WARNING — new wiki readings: {new_readings}"
    return f"[{today_str}] MONITOR URGENT — regime changed {alert['old_regime']} → {alert['new_regime']}"


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Full alert JSON to stdout")
@click.option("--text", "as_text", is_flag=True, default=False, help="One-line summary to stdout")
def main(as_json, as_text):
    """Pull fresh data, compare to history, emit alert."""
    click.echo("[monitor] Pulling indicators...", err=True)
    if run_gauge("run") != 0:
        sys.exit(1)

    today_str = str(date.today())
    new_sc = load_scorecard()

    # Save history snapshot
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_file = HISTORY_DIR / f"{today_str}.json"
    shutil.copy(SCORECARD_JSON, history_file)

    # Load previous history
    prev_sc: dict = {}
    for hf in sorted(HISTORY_DIR.glob("*.json"), reverse=True):
        if hf.stem < today_str:
            prev_sc = json.loads(hf.read_text())
            break

    diff = (
        diff_scorecards(new_sc, prev_sc)
        if prev_sc
        else {
            "regime_changed": False,
            "old_regime": [],
            "new_regime": [
                new_sc.get("regime", {}).get(k) for k in ("cycle_stage", "stress_direction", "inflation_regime")
            ],
            "new_rules_fired": [],
            "rules_cleared": [],
            "threshold_crossings": [],
        }
    )

    alert_level = determine_alert_level(diff)
    alert = {
        "date": today_str,
        "alert_level": alert_level,
        **diff,
    }

    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    alert_file = ALERTS_DIR / f"{today_str}.json"
    alert_file.write_text(json.dumps(alert, indent=2))

    if as_json:
        click.echo(json.dumps(alert, indent=2))
    else:
        click.echo(one_line_summary(today_str, alert))


if __name__ == "__main__":
    main()
