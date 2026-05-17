#!/usr/bin/env python3
"""
Gauge Debate — counter-balancing analysis for trade decisions.

Usage:
    debate.py "Add $12k to GLD because late cycle gold floor rule fired"

Reads the current scorecard and vault, generates structured bull/bear
arguments, and outputs a synthesis with classified disagreements.

This script generates the PROMPTS and CONTEXT for bull/bear analysis.
The actual LLM work happens via OpenClaw sub-agents (spawned by the
calling agent) or can be run manually by pasting the prompts.

Output: data/debates/YYYY-MM-DD-<slug>.md
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

# Paths
PROJECT = Path(__file__).resolve().parent.parent.parent
DATA = PROJECT / "data"
SCORECARD = DATA / "scorecard.json"
VAULT = PROJECT / "content" / "dalio"
DEBATES_DIR = DATA / "debates"
RULES = Path(__file__).resolve().parent / "rules.yaml"


def load_scorecard():
    if not SCORECARD.exists():
        return None
    return json.loads(SCORECARD.read_text())


def load_rules_yaml():
    import yaml

    if not RULES.exists():
        return []
    return yaml.safe_load(RULES.read_text()).get("rules", [])


def find_relevant_vault_pages(trade_description, scorecard):
    """Find vault pages relevant to this trade based on regime + keywords."""
    regime = scorecard.get("regime", {})
    cycle = regime.get("cycle_stage", "unknown")
    stress = regime.get("stress_direction", "unknown")
    inflation = regime.get("inflation_regime", "unknown")

    # Always relevant
    pages = [
        "07-current-macro-position/index.md",
        "09-investing-principles/index.md",
    ]

    # Regime-driven
    if cycle in ("late", "crisis"):
        pages.append("05-sovereign-debt-stress/index.md")
        pages.append("01-debt-cycle-mechanics/bubble-formation-signals.md")
    if stress in ("deteriorating", "acute"):
        pages.append("02-deleveraging-playbook/index.md")
    if inflation in ("rising", "acute"):
        pages.append("02-deleveraging-playbook/deflationary-vs-inflationary-types.md")
        pages.append("08-asset-returns-and-positioning/gold-real-assets-in-devaluation.md")

    # Keyword-driven
    desc_lower = trade_description.lower()
    if any(w in desc_lower for w in ("gold", "gld", "slv", "silver", "commodity")):
        pages.append("08-asset-returns-and-positioning/gold-real-assets-in-devaluation.md")
        pages.append("08-asset-returns-and-positioning/all-weather-framework.md")
    if any(w in desc_lower for w in ("china", "mchi", "cnxt", "em", "emerging")):
        pages.append("06-geopolitical-cycles/us-china-rivalry.md")
    if any(w in desc_lower for w in ("bond", "treasury", "duration", "tlt", "ief")):
        pages.append("03-currency-monetary-systems/index.md")
    if any(w in desc_lower for w in ("put", "hedge", "vix", "protect")):
        pages.append("01-debt-cycle-mechanics/bubble-top-and-depression.md")
    if any(w in desc_lower for w in ("defense", "ita", "war", "military")):
        pages.append("06-geopolitical-cycles/economic-war-precedes-hot-war.md")

    # Deduplicate preserving order
    seen = set()
    unique = []
    for p in pages:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def load_vault_pages(page_paths):
    """Load vault page contents, truncated to first 2000 chars each."""
    contents = {}
    for p in page_paths:
        full = VAULT / p
        if full.exists():
            text = full.read_text()
            if len(text) > 2000:
                text = text[:2000] + "\n...[truncated]"
            contents[p] = text
    return contents


def build_context_block(trade_description, scorecard, vault_pages):
    """Build the shared context block that both bull and bear agents see."""
    regime = scorecard.get("regime", {})
    raw = scorecard.get("raw", {})
    rules_fired = scorecard.get("rules_fired", [])

    lines = [
        "## Current Macro Regime",
        (
            f"Cycle: {regime.get('cycle_stage', '?')}"
            f" | Stress: {regime.get('stress_direction', '?')}"
            f" | Inflation: {regime.get('inflation_regime', '?')}"
        ),
        "",
        "## Key Indicators",
    ]
    for key, val in raw.items():
        v = val.get("value", "?")
        stale = " ⚠️STALE" if val.get("stale") else ""
        lines.append(f"- {key}: {v}{stale}")

    lines.append("")
    lines.append("## Rules Currently Firing")
    if rules_fired:
        for r in rules_fired:
            lines.append(f"- [{r.get('confidence', '?').upper()}] {r.get('id')}: {r.get('name')} → {r.get('action')}")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("## Relevant Vault Pages")
    for path, content in vault_pages.items():
        lines.append(f"\n### {path}\n")
        lines.append(content)

    return "\n".join(lines)


def generate_debate(trade_description):
    """Generate the full debate document with bull/bear prompts and context."""
    scorecard = load_scorecard()
    if not scorecard:
        print("ERROR: No scorecard.json found. Run 'gauge.py run' first.")
        sys.exit(1)

    page_paths = find_relevant_vault_pages(trade_description, scorecard)
    vault_pages = load_vault_pages(page_paths)
    context = build_context_block(trade_description, scorecard, vault_pages)

    today_str = date.today().isoformat()
    slug = re.sub(r"[^a-z0-9]+", "-", trade_description.lower().strip())[:60].strip("-")
    r_cycle = scorecard["regime"]["cycle_stage"]
    r_stress = scorecard["regime"]["stress_direction"]
    r_inflation = scorecard["regime"]["inflation_regime"]

    # Build the debate document
    doc = f"""---
date: {today_str}
trade: "{trade_description}"
regime: [{r_cycle}, {r_stress}, {r_inflation}]
---

# Debate: {trade_description}

Generated {today_str} | Regime: ({r_cycle}, {r_stress}, {r_inflation})

---

## Shared Context

{context}

---

## Bull Case Prompt

> You are arguing FOR this trade: "{trade_description}"
>
> Using ONLY the vault pages and indicators provided above, make the strongest
> possible case for this trade. Cite specific atoms or vault sections. Address:
> 1. What in the current regime supports this trade?
> 2. What historical analog from the vault supports it?
> 3. What's the expected return and timeframe?
> 4. What would make you wrong? (name the specific indicator or event)
>
> Be specific, not generic. If the vault doesn't support the trade, say so.

[BULL CASE — to be filled by agent or human]

---

## Bear Case Prompt

> You are arguing AGAINST this trade: "{trade_description}"
>
> Using ONLY the vault pages and indicators provided above, make the strongest
> possible case against this trade. Cite specific atoms or vault sections. Address:
> 1. What in the current regime argues against this trade?
> 2. What historical analog shows this trade failing?
> 3. What's the downside risk and how bad could it get?
> 4. What would make you wrong? (name the specific indicator or event)
>
> Be specific, not generic. If the vault actually supports the trade, acknowledge it.

[BEAR CASE — to be filled by agent or human]

---

## Synthesis

> After reading both cases, classify each disagreement as:
> - **Factual** (resolvable with data we could get)
> - **Judgment** (irreducible uncertainty, must decide under ambiguity)
>
> Then give a recommendation: proceed / modify / reject, with sizing guidance.

[SYNTHESIS — to be filled by agent or human]
"""

    # Write to file
    DEBATES_DIR.mkdir(parents=True, exist_ok=True)
    out_file = DEBATES_DIR / f"{today_str}-{slug}.md"
    out_file.write_text(doc)
    print(f"Debate written to {out_file}")
    print(f"Context includes {len(vault_pages)} vault pages, {len(scorecard.get('raw', {}))} indicators")
    return str(out_file)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: debate.py '<trade description>'")
        print("Example: debate.py 'Add $12k to GLD because late cycle gold floor'")
        sys.exit(1)

    trade = " ".join(sys.argv[1:])
    generate_debate(trade)
