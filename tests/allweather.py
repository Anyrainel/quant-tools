#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
allweather.py — Risk-balanced neutral portfolio weights.

Computes the All Weather neutral portfolio from allocations.yaml.
No regime awareness. No account awareness.

The All Weather logic:
- Each asset class has environment exposures (which of 4 quadrants it thrives in)
- The neutral portfolio equalizes risk contribution across all 4 environments
- We use Dalio's published approximate weights from allocations.yaml neutral section

Usage:
    allweather.py --json           # output neutral weights as JSON
    allweather.py --text           # human-readable table (default)
    allweather.py --universe FILE  # custom asset universe YAML
"""

import json
from pathlib import Path

import click
import yaml

DEFAULT_UNIVERSE = Path(__file__).parent / "allocations.yaml"

ENVIRONMENTS = ["rising_growth", "falling_growth", "rising_inflation", "falling_inflation"]


def load_universe(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def compute_environment_balance(asset_classes: dict, neutral: dict) -> dict[str, float]:
    """For each environment, sum the neutral weights of asset classes that thrive in it."""
    balance: dict[str, float] = {env: 0.0 for env in ENVIRONMENTS}
    for ac, info in asset_classes.items():
        weight = neutral.get(ac, 0.0)
        envs = info.get("environment", [])
        if isinstance(envs, str):
            envs = [envs]
        per_env = weight / len(envs) if envs else 0.0
        for env in envs:
            if env in balance:
                balance[env] += per_env
    return {k: round(v, 2) for k, v in balance.items()}


def build_output(cfg: dict) -> dict:
    asset_classes = cfg.get("asset_classes", {})
    neutral = cfg.get("neutral", {})

    env_balance = compute_environment_balance(asset_classes, neutral)

    # Include environment info in neutral output for LLM self-description
    neutral_annotated = {}
    for ac, weight in neutral.items():
        info = asset_classes.get(ac, {})
        envs = info.get("environment", [])
        if isinstance(envs, str):
            envs = [envs]
        neutral_annotated[ac] = {
            "weight": weight,
            "environment": envs,
            "representative_ticker": info.get("representative_ticker", ""),
        }

    return {
        "neutral": {ac: d["weight"] for ac, d in neutral_annotated.items()},
        "neutral_detail": neutral_annotated,
        "environment_balance": env_balance,
        "rationale": (
            "Neutral weights from allocations.yaml (Dalio All Weather, household-adjusted). "
            "Environment balance shows risk contribution per quadrant. "
            "Ideal balance: 25% each quadrant."
        ),
    }


def print_text(output: dict) -> None:
    neutral = output["neutral"]
    detail = output["neutral_detail"]
    env_balance = output["environment_balance"]

    print("\n=== ALL WEATHER NEUTRAL PORTFOLIO ===\n")
    print(f"{'Asset Class':<22} {'Weight':>7}  {'Environments'}")
    print("─" * 60)
    for ac, weight in sorted(neutral.items(), key=lambda x: -x[1]):
        label = ac.replace("_", " ").title()
        envs = ", ".join(detail[ac].get("environment", []))
        ticker = detail[ac].get("representative_ticker", "")
        ticker_str = f" ({ticker})" if ticker else ""
        print(f"{label:<22} {weight:>6.1f}%  {envs}{ticker_str}")
    print("─" * 60)
    total = sum(neutral.values())
    print(f"{'Total':<22} {total:>6.1f}%")

    print("\n=== ENVIRONMENT BALANCE ===\n")
    print(f"{'Environment':<25} {'Weight':>8}")
    print("─" * 35)
    for env, weight in env_balance.items():
        label = env.replace("_", " ").title()
        gap = weight - 25.0
        gap_str = f"  ({gap:+.1f}% vs ideal 25%)" if abs(gap) > 0.5 else "  ✓"
        print(f"{label:<25} {weight:>7.1f}%{gap_str}")
    print()


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON to stdout")
@click.option("--text", "as_text", is_flag=True, default=False, help="Human-readable table")
@click.option("--universe", default=str(DEFAULT_UNIVERSE), show_default=True, help="Path to universe YAML")
def main(as_json, as_text, universe):
    """Compute All Weather neutral portfolio weights."""
    cfg = load_universe(Path(universe))
    output = build_output(cfg)

    if as_json:
        click.echo(json.dumps(output, indent=2))
    else:
        print_text(output)


if __name__ == "__main__":
    main()
