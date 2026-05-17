#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
Gauge Macro Classifier — Historical Backtest
Tests 4 known regimes and checks classification accuracy.
Usage: python3 scripts/macro/backtest.py
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CONFIG_FILE = Path(__file__).parent / "config.yaml"


def load_env():
    env_path = DATA / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def fred_at(fred, series_id, target_date, lookback_days=90):
    """Get FRED value nearest to (but not after) target_date."""
    try:
        start = (target_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")
        s = fred.get_series(series_id, observation_start=start, observation_end=end).dropna()
        if s.empty:
            return None
        return float(s.iloc[-1])
    except Exception as e:
        print(f"  WARN {series_id}: {e}", file=sys.stderr)
        return None


def fred_yoy(fred, series_id, target_date):
    """Compute YoY % change for a monthly FRED series."""
    try:
        start = (target_date - timedelta(days=400)).strftime("%Y-%m-%d")
        end = target_date.strftime("%Y-%m-%d")
        s = fred.get_series(series_id, observation_start=start, observation_end=end).dropna()
        if len(s) < 13:
            return None
        v_now = s.iloc[-1]
        v_year_ago = s.iloc[-13]
        return float((v_now - v_year_ago) / v_year_ago * 100)
    except Exception as e:
        print(f"  WARN {series_id} YoY: {e}", file=sys.stderr)
        return None


def yf_close_series(ticker, start, end):
    """Return a clean 1D Close series for a single ticker."""
    import yfinance as yf

    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        return None
    close = df["Close"]
    # newer yfinance returns DataFrame with ticker as column
    if hasattr(close, "squeeze"):
        close = close.squeeze()
    return close.dropna()


def yf_at(ticker, target_date):
    """Get yfinance close price nearest to target_date."""
    try:
        start = (target_date - timedelta(days=10)).strftime("%Y-%m-%d")
        end = (target_date + timedelta(days=5)).strftime("%Y-%m-%d")
        close = yf_close_series(ticker, start, end)
        if close is None or len(close) == 0:
            return None
        return float(close.iloc[-1])
    except Exception as e:
        print(f"  WARN yf {ticker}: {e}", file=sys.stderr)
        return None


def yf_yoy(ticker, target_date):
    """Compute YoY % return from yfinance."""
    try:
        start = (target_date - timedelta(days=380)).strftime("%Y-%m-%d")
        end = (target_date + timedelta(days=5)).strftime("%Y-%m-%d")
        close = yf_close_series(ticker, start, end)
        if close is None or len(close) < 200:
            return None
        v_now = float(close.iloc[-1])
        idx = max(0, len(close) - 252)
        v_year_ago = float(close.iloc[idx])
        return (v_now - v_year_ago) / v_year_ago * 100
    except Exception as e:
        print(f"  WARN yf {ticker} YoY: {e}", file=sys.stderr)
        return None


def pull_period(fred, target_date):
    """Pull all indicator values for a given date. Returns raw dict."""
    td = target_date
    raw = {}

    # --- Cycle Stage ---
    gfdebtn = fred_at(fred, "GFDEBTN", td, lookback_days=120)
    fgrecpt = fred_at(fred, "FGRECPT", td, lookback_days=400)
    # GFDEBTN in millions, FGRECPT in billions → /1000 to match units
    raw["debt_revenue"] = {"value": gfdebtn / (fgrecpt * 1000) * 100 if gfdebtn and fgrecpt else None}

    walcl = fred_at(fred, "WALCL", td, lookback_days=120)
    gdp = fred_at(fred, "GDP", td, lookback_days=180)
    # WALCL in millions, GDP in billions → walcl/(gdp*1000)*100
    raw["fed_bs_gdp"] = {"value": walcl / (gdp * 1000) * 100 if walcl and gdp else None}

    dgs10 = fred_at(fred, "DGS10", td)
    g_est = 3.9
    raw["r_minus_g"] = {"value": dgs10 - g_est if dgs10 else None}

    # primary_deficit_revenue: FYFSD in millions, FGRECPT in billions
    fyfsd = fred_at(fred, "FYFSD", td, lookback_days=400)
    raw["primary_deficit_revenue"] = {"value": -fyfsd / (fgrecpt * 1000) * 100 if fyfsd and fgrecpt else None}

    # --- Stress Direction ---
    raw["credit_spread"] = {"value": fred_at(fred, "BAMLC0A0CM", td)}
    raw["yield_curve"] = {"value": fred_at(fred, "T10Y2Y", td)}
    raw["vix"] = {"value": yf_at("^VIX", td)}
    raw["dxy"] = {"value": yf_at("DX-Y.NYB", td)}

    gold = yf_at("GC=F", td)
    brent = yf_at("BZ=F", td)
    raw["gold_oil_ratio"] = {"value": gold / brent if gold and brent else None}

    # --- Inflation Regime ---
    raw["core_pce_yoy"] = {"value": fred_yoy(fred, "PCEPILFE", td)}
    raw["m2_yoy"] = {"value": fred_yoy(fred, "M2SL", td)}
    raw["brent"] = {"value": brent}
    raw["gold_yoy"] = {"value": yf_yoy("GC=F", td)}

    t5yie = fred_at(fred, "T5YIE", td)  # starts 2003-01-02
    raw["breakeven_5y"] = {"value": t5yie}

    # --- BIS Credit-to-GDP Gap (#15) ---
    try:
        start_gap = (td - timedelta(days=365 * 15)).strftime("%Y-%m-%d")
        s_gap = fred.get_series(
            "QUSPAM770A", observation_start=start_gap, observation_end=td.strftime("%Y-%m-%d")
        ).dropna()
        if len(s_gap) >= 40:
            rolling_mean = s_gap.rolling(window=40, min_periods=40).mean()
            gap_series = (s_gap - rolling_mean).dropna()
            raw["credit_gap"] = {"value": float(gap_series.iloc[-1]) if not gap_series.empty else None}
        else:
            raw["credit_gap"] = {"value": None}
    except Exception as e:
        print(f"  WARN credit_gap: {e}", file=sys.stderr)
        raw["credit_gap"] = {"value": None}

    return raw


def in_range(val, rng):
    return rng[0] <= val <= rng[1]


def classify_question(question_key, raw, thresholds, severity_order):
    stages = thresholds[question_key]
    votes = {s: [] for s in severity_order}
    for stage in severity_order:
        if stage not in stages:
            continue
        for ind_key, rng in stages[stage].items():
            ind = raw.get(ind_key, {})
            val = ind.get("value") if ind else None
            if val is not None and in_range(val, rng):
                votes[stage].append(ind_key)

    best_stage = severity_order[0]
    best_count = 0
    for stage in reversed(severity_order):
        count = len(votes[stage])
        if count > best_count:
            best_count = count
            best_stage = stage
    return best_stage, votes


SEVERITY = {
    "cycle_stage": ["early", "mid", "late", "crisis"],
    "stress_direction": ["stable", "deteriorating", "acute"],
    "inflation_regime": ["disinflation", "stable", "rising", "acute"],
}


def classify_stress_weighted(raw, cfg):
    """Weighted voting for Q2 — mirrors gauge.py logic."""
    thresholds = cfg["thresholds"]["stress_direction"]
    indicators_cfg = cfg.get("indicators", {})
    severity_order = SEVERITY["stress_direction"]
    all_keys: set = set()
    for st in thresholds.values():
        all_keys.update(st.keys())
    votes: dict = {s: [] for s in severity_order}
    weighted_sum = 0.0
    total_weight = 0.0
    for ind_key in all_keys:
        ind = raw.get(ind_key, {})
        val = ind.get("value") if ind else None
        if val is None:
            continue
        weight = float(indicators_cfg.get(ind_key, {}).get("weight", 1))
        voted_stage = None
        for stage in reversed(severity_order):
            if stage in thresholds and ind_key in thresholds[stage]:
                rng = thresholds[stage][ind_key]
                if in_range(val, rng):
                    voted_stage = stage
                    break
        if voted_stage is None:
            continue
        votes[voted_stage].append(ind_key)
        score = severity_order.index(voted_stage)
        weighted_sum += score * weight
        total_weight += weight
    if total_weight == 0:
        return severity_order[0], votes
    avg = weighted_sum / total_weight
    if avg < 0.5:
        best = "stable"
    elif avg < 1.5:
        best = "deteriorating"
    else:
        best = "acute"
    return best, votes


def classify_all(raw, cfg):
    t = cfg["thresholds"]
    cs, cs_v = classify_question("cycle_stage", raw, t, SEVERITY["cycle_stage"])
    sd, sd_v = classify_stress_weighted(raw, cfg)  # weighted
    ir, ir_v = classify_question("inflation_regime", raw, t, SEVERITY["inflation_regime"])
    return {"cycle_stage": cs, "stress_direction": sd, "inflation_regime": ir}, {
        "cycle_stage": cs_v,
        "stress_direction": sd_v,
        "inflation_regime": ir_v,
    }


def main():
    load_env()
    import fredapi

    fred = fredapi.Fred(api_key=os.environ["FRED_API_KEY"])
    cfg = yaml.safe_load(CONFIG_FILE.read_text())

    periods = [
        ("Jul 2007", datetime(2007, 7, 31), "Late/Stable/Stable"),
        (
            "Oct 2008",
            datetime(2008, 10, 31),
            "Late/Acute/Disinflation or Crisis/Acute/Disinflation",
        ),
        ("Mar 2020", datetime(2020, 3, 31), "Late/Acute/Disinflation"),
        (
            "Jun 2022",
            datetime(2022, 6, 30),
            "Late/Deteriorating/Rising or Late/Stable/Acute",
        ),
    ]

    results = []
    raw_data = {}

    for label, dt, expected in periods:
        print(f"\nPulling {label} ({dt.date()})...", flush=True)
        raw = pull_period(fred, dt)
        raw_data[label] = raw

        # print indicator values
        print("  Indicators:")
        for k, v in raw.items():
            val = v.get("value") if v else None
            print(f"    {k}: {val:.3f}" if val is not None else f"    {k}: N/A")

        regime, votes = classify_all(raw, cfg)
        classified = f"{regime['cycle_stage']}/{regime['stress_direction']}/{regime['inflation_regime']}"

        # check match (case-insensitive, any expected variant)
        expected_variants = [e.strip().lower() for e in expected.split(" or ")]
        match = classified.lower() in expected_variants
        results.append((label, expected, classified, "✓" if match else "✗", votes))

    # Summary table
    print("\n" + "=" * 90)
    print(f"{'Period':<10} {'Expected':<45} {'Classified':<35} {'Match'}")
    print("-" * 90)
    for label, expected, classified, match, _ in results:
        print(f"{label:<10} {expected:<45} {classified:<35} {match}")
    print("=" * 90)

    # Vote breakdown
    print("\nVote breakdown:")
    for label, _, _, _, votes in results:
        print(f"\n  {label}:")
        for q, v in votes.items():
            non_empty = {s: inds for s, inds in v.items() if inds}
            print(f"    {q}: {non_empty}")

    mismatches = [(l, e, c, v) for l, e, c, m, v in results if m == "✗"]
    if mismatches:
        print(f"\n⚠ {len(mismatches)} mismatch(es) — review thresholds")
        for label, expected, classified, votes in mismatches:
            print(f"  {label}: expected {expected}, got {classified}")
    else:
        print("\n✓ All periods classified correctly!")


if __name__ == "__main__":
    main()
