#!/usr/bin/env python3
"""
Historical Macro Regime Timeline — 2000-Q1 to 2026-Q1
Runs the gauge classifier for every quarter-end and outputs:
  - stdout: color-coded text timeline
  - data/timeline.csv: indicator values + regime per quarter
  - data/timeline_summary.md: phase analysis

Usage: python3 scripts/macro/timeline.py [--force-warm]
"""
import argparse
import csv
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

# ── Paths & imports ───────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "core"))  # noqa: E402
sys.path.insert(0, str(ROOT / "signals"))  # noqa: E402

from core.cache import get_latest_before, is_cached_series, put_bulk  # noqa: E402
from signals.gauge import (  # noqa: E402
    SEVERITY,
    check_crisis_override,
    classify_question,
    classify_stress_weighted,
    load_config,
    load_env,
)

# ── Config ────────────────────────────────────────────────────────────────────

# FRED series to pre-warm (full history)
FRED_SERIES = [
    "GFDEBTN", "FGRECPT", "FYFSD", "WALCL", "GDP",
    "DGS10", "T10Y2Y", "T5YIE", "BAA10Y",
    "PCEPILFE", "M2SL", "QUSPAM770A", "USEPUINDXM",
    "GOLDAMGBD228NLBM", "DCOILBRENTEU",
]
YF_TICKERS = ["^VIX", "DX-Y.NYB"]
WARM_START = "1990-01-01"

# Emoji
STAGE_EMOJI = {"early": "🟢", "mid": "🟡", "late": "🟠", "crisis": "🔴"}
STRESS_EMOJI = {"stable": "✅", "deteriorating": "⚠️", "acute": "🚨"}
INFL_EMOJI = {"disinflation": "❄️", "stable": "💤", "rising": "🔥", "acute": "💥"}


# ── Cache warming ─────────────────────────────────────────────────────────────


def warm_cache(fred, force=False):
    """Bulk-fetch full history for all series and cache them."""
    import yfinance as yf_lib

    print("🌡️  Warming cache (first run may take a few minutes)...")
    for series_id in FRED_SERIES:
        if not force and is_cached_series("fred", series_id):
            print(f"   FRED {series_id}: ✓ cached")
            continue
        try:
            s = fred.get_series(series_id, observation_start=WARM_START)
            s = s.dropna()
            if not s.empty:
                put_bulk("fred", series_id, {str(idx.date()): float(v) for idx, v in s.items()})
                print(f"   FRED {series_id}: {len(s)} obs cached")
            else:
                print(f"   FRED {series_id}: no data returned")
        except Exception as e:
            print(f"   FRED {series_id}: FAILED — {e}")

    for ticker in YF_TICKERS:
        if not force and is_cached_series("yfinance", ticker):
            print(f"   yfinance {ticker}: ✓ cached")
            continue
        try:
            t = yf_lib.Ticker(ticker)
            hist = t.history(start=WARM_START, auto_adjust=True)
            if not hist.empty:
                closes = hist["Close"].dropna()
                put_bulk("yfinance", ticker, {str(idx.date()): float(v) for idx, v in closes.items()})
                print(f"   yfinance {ticker}: {len(closes)} obs cached")
            else:
                print(f"   yfinance {ticker}: no data")
        except Exception as e:
            print(f"   yfinance {ticker}: FAILED — {e}")
    print()


# ── Date helpers ──────────────────────────────────────────────────────────────


def quarter_ends(start_year=2000, start_q=1, end_year=2026, end_q=1):
    """Yield (year, quarter, last_business_day_of_quarter) tuples."""
    y, q = start_year, start_q
    while (y, q) <= (end_year, end_q):
        end_month = q * 3
        if end_month == 12:
            last_day = date(y, 12, 31)
        else:
            last_day = date(y, end_month + 1, 1) - timedelta(days=1)
        while last_day.weekday() >= 5:  # Sat=5, Sun=6
            last_day -= timedelta(days=1)
        yield y, q, last_day
        q += 1
        if q > 4:
            q, y = 1, y + 1


def get_val(source, series, as_of):
    val, _ = get_latest_before(source, series, str(as_of))
    return val


def get_yoy(source, series, as_of):
    """YoY % change as of date vs ~1 year prior."""
    val_now, _ = get_latest_before(source, series, str(as_of))
    if val_now is None:
        return None
    prior = date(as_of.year - 1, as_of.month, min(as_of.day, 28))
    val_prior, _ = get_latest_before(source, series, str(prior))
    if val_prior is None or val_prior == 0:
        return None
    return round((val_now / val_prior - 1) * 100, 2)


# ── Indicator computation ─────────────────────────────────────────────────────

# In-memory QUSPAM770A series for rolling gap computation
_QUSPAM_SERIES = None  # [(date_str, value), ...]


def _ensure_quspam():
    global _QUSPAM_SERIES
    if _QUSPAM_SERIES is None:
        from core.cache import preload_series
        _QUSPAM_SERIES = preload_series("fred", "QUSPAM770A")
    return _QUSPAM_SERIES


def compute_credit_gap(as_of):
    """Compute BIS credit-to-GDP gap: value minus 10yr (40-quarter) rolling mean."""
    rows = _ensure_quspam()
    # Get observations <= as_of
    as_of_str = str(as_of)
    subset = [(d, v) for d, v in rows if d <= as_of_str and v is not None]
    if len(subset) < 40:
        return None
    vals = [v for _, v in subset]
    window = vals[-40:]
    rolling_mean = sum(window) / len(window)
    return round(vals[-1] - rolling_mean, 2)


def compute_raw_for_date(target_date):
    """Build a raw indicator dict for a specific date using the cache."""
    r = {}

    # 1. debt_revenue: GFDEBTN(millions) / FGRECPT(billions) * 100
    debt = get_val("fred", "GFDEBTN", target_date)
    rev = get_val("fred", "FGRECPT", target_date)
    r["debt_revenue"] = {"value": round(debt / (rev * 1000) * 100, 1) if debt and rev else None}

    # 2. r_minus_g: DGS10 - 3.9
    dgs10 = get_val("fred", "DGS10", target_date)
    r["r_minus_g"] = {"value": round(dgs10 - 3.9, 2) if dgs10 is not None else None}

    # 3. primary_deficit_revenue: -FYFSD / FGRECPT * 100
    deficit = get_val("fred", "FYFSD", target_date)
    r["primary_deficit_revenue"] = {
        "value": round(-deficit / (rev * 1000) * 100, 1) if deficit is not None and rev else None
    }

    # 4. fed_bs_gdp: WALCL(millions) / GDP(billions) * 100 / 1000
    walcl = get_val("fred", "WALCL", target_date)
    gdp = get_val("fred", "GDP", target_date)
    r["fed_bs_gdp"] = {"value": round(walcl / (gdp * 1000) * 100, 1) if walcl and gdp else None}

    # 5. credit_spread: BAA10Y in % (config uses BAA10Y for historical range)
    baa = get_val("fred", "BAA10Y", target_date)
    r["credit_spread"] = {"value": round(baa, 2) if baa is not None else None}

    # 6. vix
    vix = get_val("yfinance", "^VIX", target_date)
    r["vix"] = {"value": round(vix, 1) if vix is not None else None}

    # 7. yield_curve: T10Y2Y
    curve = get_val("fred", "T10Y2Y", target_date)
    r["yield_curve"] = {"value": round(curve, 2) if curve is not None else None}

    # 8. dxy: DX-Y.NYB
    dxy = get_val("yfinance", "DX-Y.NYB", target_date)
    r["dxy"] = {"value": round(dxy, 2) if dxy is not None else None}

    # 9. gold_oil_ratio: GOLDAMGBD228NLBM / DCOILBRENTEU
    gold = get_val("fred", "GOLDAMGBD228NLBM", target_date)
    oil = get_val("fred", "DCOILBRENTEU", target_date)
    r["gold_oil_ratio"] = {"value": round(gold / oil, 2) if gold and oil else None}

    # 10. core_pce_yoy
    r["core_pce_yoy"] = {"value": get_yoy("fred", "PCEPILFE", target_date)}

    # 11. breakeven_5y: T5YIE (starts 2003-01-02)
    bei = get_val("fred", "T5YIE", target_date)
    r["breakeven_5y"] = {"value": round(bei, 2) if bei is not None else None}

    # 12. brent
    r["brent"] = {"value": round(oil, 2) if oil else None}

    # 13. gold_yoy
    r["gold_yoy"] = {"value": get_yoy("fred", "GOLDAMGBD228NLBM", target_date)}

    # 14. m2_yoy
    r["m2_yoy"] = {"value": get_yoy("fred", "M2SL", target_date)}

    # 15. credit_gap
    r["credit_gap"] = {"value": compute_credit_gap(target_date)}

    # 16. epu
    epu = get_val("fred", "USEPUINDXM", target_date)
    r["epu"] = {"value": round(epu, 1) if epu is not None else None}

    return r


# ── Classifier wrapper ────────────────────────────────────────────────────────


def classify_date(raw, cfg):
    """Run full classifier pipeline on a raw dict. Returns (cs, sd, ir)."""
    thresholds = cfg["thresholds"]

    cs, _, _ = classify_question("cycle_stage", raw, thresholds, SEVERITY["cycle_stage"])
    sd, _, _ = classify_stress_weighted(raw, cfg)
    ir, _, _ = classify_question("inflation_regime", raw, thresholds, SEVERITY["inflation_regime"])

    crisis_reasons = check_crisis_override(raw)
    if crisis_reasons:
        cs = "crisis"

    return cs, sd, ir


# ── Output helpers ────────────────────────────────────────────────────────────

IND_KEYS = [
    "debt_revenue", "r_minus_g", "primary_deficit_revenue", "fed_bs_gdp",
    "credit_spread", "vix", "yield_curve", "dxy", "gold_oil_ratio",
    "core_pce_yoy", "breakeven_5y", "brent", "gold_yoy", "m2_yoy",
    "credit_gap", "epu",
]


def fmt_regime(cs, sd, ir):
    se = STAGE_EMOJI.get(cs, "❓")
    ss = STRESS_EMOJI.get(sd, "❓")
    si = INFL_EMOJI.get(ir, "❓")
    return f"{se}{cs:<7} {ss}{sd:<15} {si}{ir}"


def write_csv(rows, path):
    fieldnames = ["date", "cycle_stage", "stress_direction", "inflation_regime"] + IND_KEYS
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_summary(rows, path):
    stage_counts = Counter(r["cycle_stage"] for r in rows)
    stress_counts = Counter(r["stress_direction"] for r in rows)
    infl_counts = Counter(r["inflation_regime"] for r in rows)
    total = len(rows)

    lines = ["# Macro Regime Timeline Summary (2000-Q1 to 2026-Q1)", ""]
    lines.append(f"**Total quarters analyzed:** {total}")
    lines.append("")

    lines.append("## Cycle Stage Distribution")
    lines.append("")
    for stage in ["early", "mid", "late", "crisis"]:
        n = stage_counts.get(stage, 0)
        pct = n / total * 100
        lines.append(f"- **{stage}**: {n} quarters ({pct:.0f}%)")
    lines.append("")

    lines.append("## Stress Direction Distribution")
    lines.append("")
    for s in ["stable", "deteriorating", "acute"]:
        n = stress_counts.get(s, 0)
        lines.append(f"- **{s}**: {n} quarters ({n/total*100:.0f}%)")
    lines.append("")

    lines.append("## Inflation Regime Distribution")
    lines.append("")
    for ir in ["disinflation", "stable", "rising", "acute"]:
        n = infl_counts.get(ir, 0)
        lines.append(f"- **{ir}**: {n} quarters ({n/total*100:.0f}%)")
    lines.append("")

    lines.append("## Regime Transition Points")
    lines.append("")
    lines.append("| Quarter | Cycle Stage | Stress | Inflation | Change |")
    lines.append("|---------|-------------|--------|-----------|--------|")
    prev = None
    for r in rows:
        cur = (r["cycle_stage"], r["stress_direction"], r["inflation_regime"])
        if prev is None or cur != prev:
            changed = ""
            if prev:
                changes = []
                if cur[0] != prev[0]:
                    changes.append(f"stage: {prev[0]}→{cur[0]}")
                if cur[1] != prev[1]:
                    changes.append(f"stress: {prev[1]}→{cur[1]}")
                if cur[2] != prev[2]:
                    changes.append(f"infl: {prev[2]}→{cur[2]}")
                changed = ", ".join(changes)
            lines.append(f"| {r['date']} | {cur[0]} | {cur[1]} | {cur[2]} | {changed} |")
            prev = cur
    lines.append("")

    # Phase duration analysis
    lines.append("## Phase Duration Analysis (Cycle Stage)")
    lines.append("")
    runs = []
    current_stage = rows[0]["cycle_stage"]
    run_len = 1
    for r in rows[1:]:
        if r["cycle_stage"] == current_stage:
            run_len += 1
        else:
            runs.append((current_stage, run_len))
            current_stage = r["cycle_stage"]
            run_len = 1
    runs.append((current_stage, run_len))

    from collections import defaultdict
    run_by_stage = defaultdict(list)
    for stage, length in runs:
        run_by_stage[stage].append(length)
    for stage in ["early", "mid", "late", "crisis"]:
        lens = run_by_stage.get(stage, [])
        if lens:
            avg = sum(lens) / len(lens)
            lines.append(f"- **{stage}**: {len(lens)} runs, avg {avg:.1f} quarters, "
                         f"min {min(lens)}, max {max(lens)}")
    lines.append("")

    lines.append("## Continuity Assessment")
    lines.append("")
    # Check if cycle stage follows a typical early→mid→late→crisis→early progression
    total_transitions = len(runs) - 1
    progressive = sum(
        1 for i in range(len(runs) - 1)
        if SEVERITY["cycle_stage"].index(runs[i+1][0]) >= SEVERITY["cycle_stage"].index(runs[i][0])
        or runs[i+1][0] == "early"
    )
    pct = progressive / total_transitions * 100 if total_transitions > 0 else 0
    lines.append(f"- {pct:.0f}% of cycle stage transitions are progressive "
                 f"(escalation or reset to early)")
    if pct > 65:
        lines.append("- **Pattern: Broadly cyclical** — regime follows recognizable debt-cycle phases")
    else:
        lines.append("- **Pattern: Volatile/mixed** — more regime reversals than a textbook cycle")
    lines.append("")

    path.write_text("\n".join(lines))


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Historical macro regime timeline")
    parser.add_argument("--force-warm", action="store_true", help="Re-fetch all series even if cached")
    args = parser.parse_args()

    load_env()
    import fredapi
    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        print("ERROR: FRED_API_KEY not set in data/.env", file=sys.stderr)
        sys.exit(1)
    fred = fredapi.Fred(api_key=fred_key)

    warm_cache(fred, force=args.force_warm)

    cfg = load_config()
    quarters = list(quarter_ends())

    print(f"📅 Running classifier for {len(quarters)} quarters (2000-Q1 to 2026-Q1)...\n")

    csv_rows = []
    prev_regime = None

    for y, q, qdate in quarters:
        raw = compute_raw_for_date(qdate)
        cs, sd, ir = classify_date(raw, cfg)

        available = sum(1 for k in IND_KEYS if raw.get(k, {}).get("value") is not None)
        regime_str = fmt_regime(cs, sd, ir)
        label = f"{y}-Q{q}  ({qdate})"

        change_marker = ""
        if prev_regime and (cs, sd, ir) != prev_regime:
            change_marker = " ◄ TRANSITION"
        prev_regime = (cs, sd, ir)

        print(f"  {label}  {regime_str}  [{available}/16]{change_marker}")

        row = {"date": str(qdate), "cycle_stage": cs, "stress_direction": sd, "inflation_regime": ir}
        for k in IND_KEYS:
            row[k] = raw.get(k, {}).get("value")
        csv_rows.append(row)

    # Write outputs
    csv_path = DATA / "timeline.csv"
    write_csv(csv_rows, csv_path)
    print(f"\n✅ CSV written: {csv_path}")

    summary_path = DATA / "timeline_summary.md"
    write_summary(csv_rows, summary_path)
    print(f"✅ Summary written: {summary_path}")


if __name__ == "__main__":
    main()
