#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
alpha.py — Regime tilt engine.

Given a regime tuple + conviction, outputs the tilt vector
(what to overweight/underweight vs neutral), in percentage points.

No account awareness. No neutral portfolio awareness. Pure signal.

Usage:
    alpha.py --json                                          # reads scorecard.json
    alpha.py --regime late,deteriorating,rising --conviction 0.6
    alpha.py --text                                          # human-readable
"""

import json
from pathlib import Path

import click
import yaml

DEFAULT_SCORECARD = Path(__file__).resolve().parents[2] / "data" / "scorecard.json"
DEFAULT_CONFIG = Path(__file__).parent / "allocations.yaml"

# Map inflation_regime values to tilt section keys
INFLATION_KEY_MAP = {
    "stable": "stable",
    "acute": "acute",
    "rising": "rising",
    "disinflation": "disinflation",
}


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def load_scorecard(path: Path) -> dict:
    return json.loads(path.read_text())


def compute_conviction(disagreements: dict) -> float:
    n = sum(1 for v in disagreements.values() if v)
    return max(0.4, round(1.0 - n * 0.2, 2))


def compute_tilts(regime: dict, conviction: float, cfg: dict) -> dict:
    """
    Compute raw and scaled tilt vectors with per-asset rationale.

    Returns dict with raw_tilts, scaled_tilts, rationale.
    """
    tilts_cfg = cfg.get("tilts", {})
    asset_classes = list(cfg.get("neutral", {}).keys())

    cycle_stage = regime.get("cycle_stage", "mid")
    stress_direction = regime.get("stress_direction", "stable")
    inflation_regime = regime.get("inflation_regime", "stable")

    # Fetch tilt vectors for each regime dimension
    cycle_vec = tilts_cfg.get("cycle_stage", {}).get(cycle_stage, {}) or {}
    stress_vec = tilts_cfg.get("stress_direction", {}).get(stress_direction, {}) or {}
    inflation_vec = tilts_cfg.get("inflation_regime", {}).get(inflation_regime, {}) or {}

    # Build raw tilt (sum of 3 vectors) and rationale
    raw_tilts: dict[str, float] = {ac: 0.0 for ac in asset_classes}
    rationale: dict[str, str] = {}

    for ac in asset_classes:
        c_val = float(cycle_vec.get(ac, 0))
        s_val = float(stress_vec.get(ac, 0))
        i_val = float(inflation_vec.get(ac, 0))
        total = c_val + s_val + i_val
        raw_tilts[ac] = total

        parts = []
        if c_val != 0:
            parts.append(f"{cycle_stage}({c_val:+g})")
        if s_val != 0:
            parts.append(f"{stress_direction}({s_val:+g})")
        if i_val != 0:
            parts.append(f"{inflation_regime}({i_val:+g})")

        if parts:
            expr = " + ".join(parts) + f" = {total:+g}"
            rationale[ac] = f"{expr}, × {conviction} = {total * conviction:+.2g}"
        else:
            rationale[ac] = "no tilt"

    # Scale by conviction
    scaled_tilts = {ac: round(v * conviction, 2) for ac, v in raw_tilts.items()}

    # Filter out zero-tilt assets from output (keep rationale for non-zero only)
    rationale = {ac: v for ac, v in rationale.items() if v != "no tilt"}
    raw_tilts = {ac: v for ac, v in raw_tilts.items() if v != 0}
    scaled_tilts = {ac: v for ac, v in scaled_tilts.items() if v != 0}

    return {
        "raw_tilts": raw_tilts,
        "scaled_tilts": scaled_tilts,
        "rationale": rationale,
    }


def build_output(regime: dict, conviction: float, cfg: dict) -> dict:
    tilt_data = compute_tilts(regime, conviction, cfg)
    return {
        "regime": regime,
        "conviction": conviction,
        "raw_tilts": tilt_data["raw_tilts"],
        "scaled_tilts": tilt_data["scaled_tilts"],
        "rationale": tilt_data["rationale"],
    }


def print_text(output: dict) -> None:
    regime = output["regime"]
    conviction = output["conviction"]
    scaled = output["scaled_tilts"]
    rationale = output["rationale"]

    cs = regime.get("cycle_stage", "?")
    sd = regime.get("stress_direction", "?")
    ir = regime.get("inflation_regime", "?")

    print(f"\n=== REGIME TILTS: ({cs}, {sd}, {ir}) | conviction={conviction:.1f} ===\n")
    print(f"{'Asset Class':<22} {'Raw':>6}  {'Scaled':>7}  Rationale")
    print("─" * 75)

    raw = output["raw_tilts"]
    all_acs = sorted(set(list(raw.keys()) + list(scaled.keys())), key=lambda x: -abs(scaled.get(x, 0)))

    for ac in all_acs:
        label = ac.replace("_", " ").title()
        raw_v = raw.get(ac, 0)
        sc_v = scaled.get(ac, 0)
        rat = rationale.get(ac, "—")
        print(f"{label:<22} {raw_v:>+5g}  {sc_v:>+7.2f}  {rat}")

    if not all_acs:
        print("  (no tilts — neutral regime)")
    print()


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Output JSON to stdout")
@click.option("--text", "as_text", is_flag=True, default=False, help="Human-readable output")
@click.option(
    "--regime",
    default=None,
    help="Override regime: cycle,stress,inflation (e.g. late,deteriorating,rising)",
)
@click.option("--conviction", default=None, type=float, help="Override conviction (0.0-1.0)")
@click.option("--scorecard", default=str(DEFAULT_SCORECARD), show_default=True, help="Path to scorecard.json")
@click.option(
    "--config", "config_path", default=str(DEFAULT_CONFIG), show_default=True, help="Path to allocations.yaml"
)
def main(as_json, as_text, regime, conviction, scorecard, config_path):
    """Compute regime tilt vector from scorecard or manual override."""
    cfg = load_config(Path(config_path))

    if regime:
        parts = [p.strip() for p in regime.split(",")]
        if len(parts) != 3:
            raise click.ClickException("--regime must be: cycle_stage,stress_direction,inflation_regime")
        regime_dict = {
            "cycle_stage": parts[0],
            "stress_direction": parts[1],
            "inflation_regime": parts[2],
        }
        conv = conviction if conviction is not None else 1.0
    else:
        sc = load_scorecard(Path(scorecard))
        regime_dict = sc.get("regime", {})
        if not regime_dict:
            raise click.ClickException("No regime in scorecard. Run 'gauge.py run' first.")
        if conviction is not None:
            conv = conviction
        else:
            disagreements = sc.get("disagreements", {})
            conv = compute_conviction(disagreements)

    output = build_output(regime_dict, conv, cfg)

    if as_json:
        click.echo(json.dumps(output, indent=2))
    else:
        print_text(output)


if __name__ == "__main__":
    main()
