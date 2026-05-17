#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
portfolio.py — Target portfolio combiner.

Combines neutral (from allweather) + tilts (from alpha) → target weights.
No account awareness. Pure math.

Usage:
    portfolio.py --json          # reads allweather + alpha outputs, combines
    portfolio.py --text          # table: neutral → tilt → target
    portfolio.py --neutral FILE  # override neutral JSON (default: allweather --json)
    portfolio.py --tilts FILE    # override tilts JSON (default: alpha --json)
"""

import json
import subprocess
import sys
from pathlib import Path

import click

MACRO_DIR = Path(__file__).parent
PYTHON = sys.executable


def run_json(script: str, extra_args: list | None = None) -> dict:
    """Run a sibling script with --json and parse its output."""
    cmd = [PYTHON, str(MACRO_DIR / script), "--json"]
    if extra_args:
        cmd += extra_args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise click.ClickException(f"{script} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def load_json_file(path: str) -> dict:
    return json.loads(Path(path).read_text())


def combine(neutral: dict, tilts: dict) -> dict:
    """Combine neutral weights + scaled tilts → target weights (clamped, normalized)."""
    all_classes = set(list(neutral.keys()) + list(tilts.keys()))
    raw_target: dict[str, float] = {}
    for ac in all_classes:
        n = float(neutral.get(ac, 0))
        t = float(tilts.get(ac, 0))
        raw_target[ac] = max(0.0, n + t)

    total = sum(raw_target.values())
    if total <= 0:
        return {ac: 0.0 for ac in all_classes}

    return {ac: round(v / total * 100, 1) for ac, v in raw_target.items()}


def build_output(neutral_data: dict, alpha_data: dict) -> dict:
    neutral = neutral_data.get("neutral", {})
    scaled_tilts = alpha_data.get("scaled_tilts", {})
    regime = alpha_data.get("regime", {})
    conviction = alpha_data.get("conviction", 1.0)
    rationale = alpha_data.get("rationale", {})

    target = combine(neutral, scaled_tilts)

    # Build per-asset summary for LLM consumption
    breakdown: dict[str, dict] = {}
    for ac in sorted(set(list(neutral.keys()) + list(target.keys()))):
        n = neutral.get(ac, 0.0)
        t = scaled_tilts.get(ac, 0.0)
        tgt = target.get(ac, 0.0)
        rat = rationale.get(ac, "no tilt")
        breakdown[ac] = {
            "neutral": n,
            "tilt": t,
            "target": tgt,
            "rationale": rat,
        }

    return {
        "target": target,
        "neutral": neutral,
        "tilts": scaled_tilts,
        "regime": regime,
        "conviction": conviction,
        "breakdown": breakdown,
    }


def print_text(output: dict) -> None:
    regime = output["regime"]
    conviction = output["conviction"]
    cs = regime.get("cycle_stage", "?")
    sd = regime.get("stress_direction", "?")
    ir = regime.get("inflation_regime", "?")

    print(f"\n=== TARGET PORTFOLIO: ({cs}, {sd}, {ir}) | conviction={conviction:.1f} ===\n")
    print(f"{'Asset Class':<22} {'Neutral':>8} {'Tilt':>7} {'Target':>8}")
    print("─" * 50)

    breakdown = output["breakdown"]
    rows = sorted(breakdown.items(), key=lambda x: -x[1]["target"])
    for ac, d in rows:
        label = ac.replace("_", " ").title()
        n = d["neutral"]
        t = d["tilt"]
        tgt = d["target"]
        t_str = f"{t:+.1f}" if t != 0 else "   —"
        print(f"{label:<22} {n:>7.1f}% {t_str:>7} {tgt:>7.1f}%")

    print("─" * 50)
    total = sum(d["target"] for d in breakdown.values())
    print(f"{'Total':<22} {sum(d['neutral'] for d in breakdown.values()):>7.1f}%        {total:>7.1f}%")
    print()


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON to stdout")
@click.option("--text", "as_text", is_flag=True, default=False, help="Human-readable table")
@click.option("--neutral", "neutral_file", default=None, help="Path to allweather JSON output")
@click.option("--tilts", "tilts_file", default=None, help="Path to alpha JSON output")
def main(as_json, as_text, neutral_file, tilts_file):
    """Combine neutral + tilts into target portfolio weights."""
    if neutral_file:
        neutral_data = load_json_file(neutral_file)
    else:
        neutral_data = run_json("allweather.py")

    if tilts_file:
        alpha_data = load_json_file(tilts_file)
    else:
        alpha_data = run_json("alpha.py")

    output = build_output(neutral_data, alpha_data)

    if as_json:
        click.echo(json.dumps(output, indent=2))
    else:
        print_text(output)


if __name__ == "__main__":
    main()
