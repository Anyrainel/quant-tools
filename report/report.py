#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
report.py — Generate vault scorecard page.

Reads scorecard.json, writes content/dalio/scorecard.md.

Usage:
    report.py          # regenerate the vault page
    report.py --json   # print scorecard summary JSON instead
"""

import json
from pathlib import Path

import click

PROJECT = Path(__file__).resolve().parents[2]
DATA = PROJECT / "data"
SCORECARD_JSON = DATA / "scorecard.json"
SCORECARD_MD = PROJECT / "content" / "dalio" / "scorecard.md"


def load_scorecard() -> dict:
    if SCORECARD_JSON.exists():
        return json.loads(SCORECARD_JSON.read_text())
    return {}


def status_emoji(ind: dict | None) -> str:
    if not ind or ind.get("value") is None:
        return "❌"
    if ind.get("stale"):
        return "⚠️"
    return "✅"


def fmt_val(ind: dict | None, unit: str = "") -> str:
    if not ind or ind.get("value") is None:
        return "N/A"
    v = ind["value"]
    s = " ⚠️ STALE" if ind.get("stale") else ""
    return f"{v}{unit}{s}".strip()


def table_row(raw: dict, name: str, key: str, unit: str = "") -> str:
    val_str = fmt_val(raw.get(key), unit)
    date_str = (raw.get(key) or {}).get("date", "N/A")
    emoji = status_emoji(raw.get(key))
    return f"| {name} | {val_str} | {date_str} | {emoji} |"


def generate_report(scorecard: dict) -> str:
    raw = scorecard.get("raw", {})
    regime = scorecard.get("regime", {})
    cs = regime.get("cycle_stage", "?")
    sd = regime.get("stress_direction", "?")
    ir = regime.get("inflation_regime", "?")
    tension = scorecard.get("tension")
    fired_rules = scorecard.get("rules_fired", [])
    pulled_at = scorecard.get("pulled_at", "unknown")[:10]

    desc = f"Current regime: {cs} cycle, {sd} stress, {ir} inflation. Last updated {pulled_at}."

    lines = [
        "---",
        'title: "Macro Regime Scorecard"',
        f'description: "{desc}"',
        f"last_updated: {pulled_at}",
        "---",
        "",
        "# Macro Regime Scorecard",
        "",
        f"**Current regime: ({cs}, {sd}, {ir})**  ",
        f"**Last updated: {pulled_at}**",
        "",
        f"## Q1: Debt Cycle Stage → {cs}",
        "",
        "| Indicator | Value | Date | Status |",
        "|---|---|---|---|",
        table_row(raw, "Debt/Revenue", "debt_revenue", "%"),
        table_row(raw, "r - g spread", "r_minus_g", "pp"),
        table_row(raw, "Primary Deficit/Revenue", "primary_deficit_revenue", "%"),
        table_row(raw, "Fed BS/GDP", "fed_bs_gdp", "%"),
        table_row(raw, "Credit-to-GDP Gap", "credit_gap", "pp"),
        "",
        f"## Q2: Near-Term Stress → {sd}",
        "",
        "| Indicator | Value | Date | Status |",
        "|---|---|---|---|",
        table_row(raw, "BBB Credit Spread", "credit_spread", "bps"),
        table_row(raw, "VIX", "vix"),
        table_row(raw, "2-10 Yield Curve", "yield_curve", "pp"),
        table_row(raw, "DXY", "dxy"),
        table_row(raw, "Gold/Oil Ratio", "gold_oil_ratio"),
        table_row(raw, "Policy Uncertainty (EPU)", "epu"),
        "",
        f"## Q3: Inflation Regime → {ir}",
        "",
        "| Indicator | Value | Date | Status |",
        "|---|---|---|---|",
        table_row(raw, "Core PCE YoY", "core_pce_yoy", "%"),
        table_row(raw, "5Y Breakeven", "breakeven_5y", "%"),
        table_row(raw, "Brent Oil", "brent", "$/bbl"),
        table_row(raw, "Gold YoY", "gold_yoy", "%"),
        table_row(raw, "M2 YoY", "m2_yoy", "%"),
        "",
        "## Tensions",
        "",
    ]

    if tension:
        lines.append(f"> ⚡ **{tension['message']}**")
        lines.append("")
        for v in tension.get("vault", []):
            lines.append(f"- [[{v}]]")
        lines.append("")
    else:
        lines.append("No major tensions detected for current regime tuple.")
        lines.append("")

    lines += ["## Rules Triggered", ""]
    if fired_rules:
        for rule in fired_rules:
            conf_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(rule.get("confidence", "medium"), "⚪")
            lines.append(f"### {conf_emoji} {rule['id']}: {rule['name']}")
            lines.append(f"**Action:** {rule['action']}")
            lines.append(f"**Vault:** [[{rule['vault']}]]  ")
            lines.append(f"**Confidence:** {rule.get('confidence', '?')}")
            lines.append("")
    else:
        lines.append("No rules triggered given current conditions.")
        lines.append("")

    lines += ["## Vault Chapters to Consult", "", "Based on current regime, prioritize reading:"]
    chapters: set = set()
    if cs in ("late", "crisis"):
        chapters.add("dalio/01-debt-cycle-mechanics")
        chapters.add("dalio/05-sovereign-debt-stress")
    if sd in ("deteriorating", "acute"):
        chapters.add("dalio/02-deleveraging-playbook")
    if ir in ("rising", "acute"):
        chapters.add("dalio/08-asset-returns-and-positioning")
        chapters.add("dalio/03-currency-monetary-systems")
    chapters.add("dalio/07-current-macro-position")
    for c in sorted(chapters):
        lines.append(f"- [[{c}]]")
    lines.append("")

    return "\n".join(lines)


@click.command()
@click.option("--json", "as_json", is_flag=True, default=False, help="Print scorecard summary JSON")
def main(as_json):
    """Generate content/dalio/scorecard.md from scorecard.json."""
    sc = load_scorecard()
    if not sc:
        raise click.ClickException("No scorecard.json found. Run 'gauge.py run' first.")
    if "regime" not in sc:
        raise click.ClickException("No regime classification. Run 'gauge.py score' first.")

    if as_json:
        # Output a clean summary for LLM consumption
        regime = sc.get("regime", {})
        summary = {
            "regime": regime,
            "pulled_at": sc.get("pulled_at", ""),
            "scored_at": sc.get("scored_at", ""),
            "rules_fired": sc.get("rules_fired", []),
            "tension": sc.get("tension"),
            "indicators": {
                k: {"value": v.get("value"), "date": v.get("date"), "stale": v.get("stale")}
                for k, v in sc.get("raw", {}).items()
            },
        }
        click.echo(json.dumps(summary, indent=2, default=str))
        return

    md = generate_report(sc)
    SCORECARD_MD.parent.mkdir(parents=True, exist_ok=True)
    SCORECARD_MD.write_text(md)
    print(f"✅ Report written to {SCORECARD_MD}")
    fired = sc.get("rules_fired", [])
    print(f"   Rules triggered: {len(fired)}")
    for r in fired:
        print(f"   - {r['id']}: {r['name']}")


if __name__ == "__main__":
    main()
