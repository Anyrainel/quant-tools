#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""
Macro Regime Gauge — pull 16 indicators, classify regime, output JSON.
Each sub-command does ONE thing. Compose via scorecard.json.

Usage:
    gauge.py pull          # fetch indicators → data/scorecard.json
    gauge.py score         # classify regime from scorecard.json
    gauge.py run           # pull + score in one shot
    gauge.py check         # evaluate which rules fire
    gauge.py --json        # dump scorecard as JSON (for piping)
    gauge.py --text        # human-readable summary (default)
"""

import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import click
import yaml

try:
    from core.cache import put_bulk

    _CACHE_ENABLED = True
except ImportError:
    _CACHE_ENABLED = False

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SCORECARD_JSON = DATA / "scorecard.json"
HISTORY_DIR = DATA / "history"
CONFIG_FILE = Path(__file__).parent / "config.yaml"
RULES_FILE = Path(__file__).parent / "rules.yaml"

# ── Config ────────────────────────────────────────────────────────────────────


def load_env():
    env_path = DATA / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def load_config():
    return yaml.safe_load(CONFIG_FILE.read_text())


def load_rules():
    return yaml.safe_load(RULES_FILE.read_text())["rules"]


def load_scorecard():
    if SCORECARD_JSON.exists():
        return json.loads(SCORECARD_JSON.read_text())
    return {}


def save_scorecard(data):
    SCORECARD_JSON.write_text(json.dumps(data, indent=2, default=str))


# ── Data helpers ──────────────────────────────────────────────────────────────


def is_stale(date_str, max_days=60):
    if not date_str:
        return True
    try:
        d = date.fromisoformat(str(date_str)[:10])
        return (date.today() - d).days > max_days
    except Exception:
        return True


def ind(value, dt, stale_days):
    """Build a standard indicator record."""
    if value is None:
        return {"value": None, "date": None, "stale": True}
    return {"value": value, "date": dt, "stale": is_stale(dt, stale_days)}


def cache_series(source, key, series):
    if _CACHE_ENABLED:
        put_bulk(source, key, {str(idx.date()): float(v) for idx, v in series.items()})


# ── Pull ──────────────────────────────────────────────────────────────────────


def pull_fred(fred, series_id, lookback=400):
    try:
        start = (datetime.today() - timedelta(days=lookback)).strftime("%Y-%m-%d")
        s = fred.get_series(series_id, observation_start=start).dropna()
        if s.empty:
            return None, None
        cache_series("fred", series_id, s)
        return float(s.iloc[-1]), str(s.index[-1].date())
    except Exception as e:
        print(f"  WARN: FRED {series_id}: {e}", file=sys.stderr)
        return None, None


def pull_fred_yoy(fred, series_id):
    try:
        start = (datetime.today() - timedelta(days=400)).strftime("%Y-%m-%d")
        s = fred.get_series(series_id, observation_start=start).dropna()
        if len(s) < 12:
            return None, None
        cache_series("fred", series_id, s)
        latest, dt = float(s.iloc[-1]), str(s.index[-1].date())
        year_ago = float(s.iloc[-13]) if len(s) >= 13 else float(s.iloc[0])
        return round((latest / year_ago - 1) * 100, 2), dt
    except Exception as e:
        print(f"  WARN: FRED YoY {series_id}: {e}", file=sys.stderr)
        return None, None


def pull_yf(ticker, period="5d"):
    try:
        import yfinance as yf

        closes = yf.Ticker(ticker).history(period=period)["Close"].dropna()
        if closes.empty:
            return None, None
        cache_series("yfinance", ticker, closes)
        return float(closes.iloc[-1]), str(closes.index[-1].date())
    except Exception as e:
        print(f"  WARN: yfinance {ticker}: {e}", file=sys.stderr)
        return None, None


def pull_yf_yoy(ticker):
    try:
        import yfinance as yf

        closes = yf.Ticker(ticker).history(period="400d")["Close"].dropna()
        if len(closes) < 200:
            return None, None
        cache_series("yfinance", ticker, closes)
        latest, dt = float(closes.iloc[-1]), str(closes.index[-1].date())
        year_ago = float(closes.iloc[max(0, len(closes) - 252)])
        return round((latest / year_ago - 1) * 100, 2), dt
    except Exception as e:
        print(f"  WARN: yfinance YoY {ticker}: {e}", file=sys.stderr)
        return None, None


def pull_all():
    load_env()
    import fredapi

    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        raise click.ClickException("FRED_API_KEY not set in data/.env")
    fred = fredapi.Fred(api_key=fred_key)
    raw = {}

    print("Pulling Q1: Debt Cycle Stage...")

    debt, debt_dt = pull_fred(fred, "GFDEBTN", 500)
    rev, rev_dt = pull_fred(fred, "FGRECPT", 500)
    dr = round(debt / (rev * 1000) * 100, 1) if debt and rev else None
    raw["debt_revenue"] = ind(dr, debt_dt, 120)
    print(f"  debt_revenue: {raw['debt_revenue']['value'] or 'FAILED'}%")

    dgs10, dgs10_dt = pull_fred(fred, "DGS10")
    raw["r_minus_g"] = ind(round(dgs10 - 3.9, 2) if dgs10 else None, dgs10_dt, 10)
    print(f"  r_minus_g: {raw['r_minus_g']['value'] or 'FAILED'}pp")

    deficit, def_dt = pull_fred(fred, "FYFSD", 800)
    rev2, _ = pull_fred(fred, "FGRECPT", 800)
    pdr = round(-deficit / (rev2 * 1000) * 100, 1) if deficit is not None and rev2 else None
    raw["primary_deficit_revenue"] = ind(pdr, def_dt, 400)
    print(f"  primary_deficit_revenue: {raw['primary_deficit_revenue']['value'] or 'FAILED'}%")

    walcl, walcl_dt = pull_fred(fred, "WALCL", 60)
    gdp, _ = pull_fred(fred, "GDP", 200)
    fbg = round(walcl / (gdp * 1000) * 100, 1) if walcl and gdp else None
    raw["fed_bs_gdp"] = ind(fbg, walcl_dt, 14)
    print(f"  fed_bs_gdp: {raw['fed_bs_gdp']['value'] or 'FAILED'}%")

    print("Pulling Q2: Near-Term Stress Direction...")

    spread, spread_dt = pull_fred(fred, "BAMLC0A0CM")
    raw["credit_spread"] = ind(round(spread * 100, 1) if spread else None, spread_dt, 7)
    print(f"  credit_spread: {raw['credit_spread']['value'] or 'FAILED'}bps")

    vix_val, vix_dt = pull_yf("^VIX")
    raw["vix"] = ind(round(vix_val, 1) if vix_val else None, vix_dt, 5)
    print(f"  vix: {raw['vix']['value'] or 'FAILED'}")

    t10y2y, curve_dt = pull_fred(fred, "T10Y2Y")
    raw["yield_curve"] = ind(round(t10y2y, 2) if t10y2y is not None else None, curve_dt, 7)
    print(f"  yield_curve: {raw['yield_curve']['value'] or 'FAILED'}pp")

    dxy_val, dxy_dt = pull_yf("DX-Y.NYB")
    raw["dxy"] = ind(round(dxy_val, 2) if dxy_val else None, dxy_dt, 5)
    print(f"  dxy: {raw['dxy']['value'] or 'FAILED'}")

    gold_val, gold_dt = pull_yf("GC=F")
    oil_val, oil_dt = pull_yf("BZ=F")
    gor = round(gold_val / oil_val, 2) if gold_val and oil_val else None
    raw["gold_oil_ratio"] = ind(gor, gold_dt, 5)
    print(f"  gold_oil_ratio: {raw['gold_oil_ratio']['value'] or 'FAILED'}")

    print("Pulling Q3: Inflation Regime...")

    core_pce, pce_dt = pull_fred_yoy(fred, "PCEPILFE")
    raw["core_pce_yoy"] = ind(core_pce, pce_dt, 45)
    print(f"  core_pce_yoy: {raw['core_pce_yoy']['value'] or 'FAILED'}%")

    bei, bei_dt = pull_fred(fred, "T5YIE")
    raw["breakeven_5y"] = ind(round(bei, 2) if bei else None, bei_dt, 7)
    print(f"  breakeven_5y: {raw['breakeven_5y']['value'] or 'FAILED'}%")

    raw["brent"] = ind(round(oil_val, 2) if oil_val else None, oil_dt, 5)
    print(f"  brent: {raw['brent']['value'] or 'FAILED'}$/bbl")

    gold_yoy, gyoy_dt = pull_yf_yoy("GC=F")
    raw["gold_yoy"] = ind(gold_yoy, gyoy_dt, 5)
    print(f"  gold_yoy: {raw['gold_yoy']['value'] or 'FAILED'}%")

    m2_yoy, m2_dt = pull_fred_yoy(fred, "M2SL")
    raw["m2_yoy"] = ind(m2_yoy, m2_dt, 45)
    print(f"  m2_yoy: {raw['m2_yoy']['value'] or 'FAILED'}%")

    print("Pulling credit-to-GDP gap + EPU...")

    try:
        start = (datetime.today() - timedelta(days=365 * 15)).strftime("%Y-%m-%d")
        s = fred.get_series("QUSPAM770A", observation_start=start).dropna()
        if len(s) >= 40:
            gap_series = (s - s.rolling(window=40, min_periods=40).mean()).dropna()
            if not gap_series.empty:
                gap_val = round(float(gap_series.iloc[-1]), 2)
                gap_dt = str(gap_series.index[-1].date())
                raw["credit_gap"] = ind(gap_val, gap_dt, 120)
                print(f"  credit_gap: {gap_val}pp")
            else:
                raw["credit_gap"] = ind(None, None, 0)
                print("  credit_gap: insufficient data")
        else:
            raw["credit_gap"] = ind(None, None, 0)
            print(f"  credit_gap: only {len(s)} obs, need 40")
    except Exception as e:
        print(f"  WARN: credit_gap: {e}", file=sys.stderr)
        raw["credit_gap"] = ind(None, None, 0)

    epu_val, epu_dt = pull_fred(fred, "USEPUINDXM", 90)
    raw["epu"] = ind(round(epu_val, 1) if epu_val else None, epu_dt, 60)
    print(f"  epu: {raw['epu']['value'] or 'FAILED'}")

    return raw


# ── Score ─────────────────────────────────────────────────────────────────────

SEVERITY = {
    "cycle_stage": ["early", "mid", "late", "crisis"],
    "stress_direction": ["stable", "deteriorating", "acute"],
    "inflation_regime": ["disinflation", "stable", "rising", "acute"],
}

TENSIONS = {
    ("late", "stable", "rising"): {
        "pattern": "late_stable_rising",
        "message": (
            "Late cycle but no acute stress yet — complacency risk. "
            "The bubble hasn't popped but conditions are deteriorating structurally."
        ),
        "vault": ["dalio/01-debt-cycle-mechanics/bubble-formation-signals"],
    },
    ("late", "deteriorating", "disinflation"): {
        "pattern": "late_deteriorating_disinflation",
        "message": ("Stress building but deflationary — deflationary deleveraging path. Bonds may outperform."),
        "vault": ["dalio/02-deleveraging-playbook/deflationary-vs-inflationary-types"],
    },
    ("late", "acute", "rising"): {
        "pattern": "late_acute_rising",
        "message": "Full crisis + inflation — ugly inflationary deleveraging. Gold, commodities, no nominal bonds.",
        "vault": [
            "dalio/02-deleveraging-playbook/deflationary-vs-inflationary-types",
            "dalio/08-asset-returns-and-positioning/gold-real-assets-in-devaluation",
        ],
    },
    ("crisis", "acute", "rising"): {
        "pattern": "crisis_acute_rising",
        "message": (
            "Full meltdown + inflation. Sovereign debt crisis. "
            "Hard assets, short duration, international diversification."
        ),
        "vault": [
            "dalio/05-sovereign-debt-stress",
            "dalio/08-asset-returns-and-positioning/gold-real-assets-in-devaluation",
        ],
    },
    ("crisis", "acute", "disinflation"): {
        "pattern": "crisis_acute_disinflation",
        "message": "Deflationary depression path. Bonds are king. Gold works. Avoid equities until spreads peak.",
        "vault": ["dalio/02-deleveraging-playbook/deflationary-vs-inflationary-types"],
    },
}


def in_range(val, rng):
    return rng[0] <= val <= rng[1]


def classify_question(question_key, raw, thresholds, severity_order):
    stages = thresholds[question_key]
    votes = {s: [] for s in severity_order}
    for stage in severity_order:
        if stage not in stages:
            continue
        for ind_key, rng in stages[stage].items():
            val = (raw.get(ind_key) or {}).get("value")
            if val is not None and in_range(val, rng):
                votes[stage].append(ind_key)

    best_stage, best_count = severity_order[0], 0
    for stage in reversed(severity_order):
        if len(votes[stage]) > best_count:
            best_count = len(votes[stage])
            best_stage = stage

    disagreement = sum(1 for s in severity_order if votes[s]) > 1
    return best_stage, votes, disagreement


def classify_stress_weighted(raw, cfg):
    thresholds = cfg["thresholds"]["stress_direction"]
    indicators_cfg = cfg.get("indicators", {})
    severity_order = SEVERITY["stress_direction"]
    all_keys = set(k for sv in thresholds.values() for k in sv)

    votes = {s: [] for s in severity_order}
    weighted_sum = total_weight = 0.0

    for ind_key in all_keys:
        val = (raw.get(ind_key) or {}).get("value")
        if val is None:
            continue
        weight = float(indicators_cfg.get(ind_key, {}).get("weight", 1))
        voted_stage = next(
            (
                s
                for s in reversed(severity_order)
                if s in thresholds and ind_key in thresholds[s] and in_range(val, thresholds[s][ind_key])
            ),
            None,
        )
        if voted_stage is None:
            continue
        votes[voted_stage].append(ind_key)
        weighted_sum += severity_order.index(voted_stage) * weight
        total_weight += weight

    if total_weight == 0:
        return severity_order[0], votes, False

    avg = weighted_sum / total_weight
    best_stage = "stable" if avg < 0.5 else ("deteriorating" if avg < 1.5 else "acute")
    disagreement = sum(1 for s in severity_order if votes[s]) > 1
    return best_stage, votes, disagreement


def check_crisis_override(raw):
    credit_gap = (raw.get("credit_gap") or {}).get("value")
    debt_rev = (raw.get("debt_revenue") or {}).get("value")
    r_g = (raw.get("r_minus_g") or {}).get("value")
    vix = (raw.get("vix") or {}).get("value")
    spread = (raw.get("credit_spread") or {}).get("value")
    has_stress = (vix is not None and vix > 25) or (spread is not None and spread > 2.5)

    reasons = []
    if credit_gap is not None and credit_gap > 18 and has_stress:
        reasons.append(f"credit_gap={credit_gap:.1f}pp + stress confirmed")
    if credit_gap is not None and credit_gap > 25:
        reasons.append(f"credit_gap={credit_gap:.1f}pp (extreme bubble)")
    if debt_rev is not None and r_g is not None and debt_rev > 700 and r_g > 1.5:
        reasons.append(f"debt/rev={debt_rev:.0f}% + r-g={r_g:.1f}pp (sovereign spiral)")
    if credit_gap is not None and debt_rev is not None and credit_gap > 12 and debt_rev > 600 and has_stress:
        reasons.append(f"credit_gap={credit_gap:.1f}pp + debt/rev={debt_rev:.0f}% + stress (compound)")
    return reasons


def score_all(raw, cfg):
    thresholds = cfg["thresholds"]
    cs, cs_votes, cs_dis = classify_question("cycle_stage", raw, thresholds, SEVERITY["cycle_stage"])
    sd, sd_votes, sd_dis = classify_stress_weighted(raw, cfg)
    ir, ir_votes, ir_dis = classify_question("inflation_regime", raw, thresholds, SEVERITY["inflation_regime"])

    crisis_reasons = check_crisis_override(raw)
    if crisis_reasons:
        cs = "crisis"
        cs_dis = True
        cs_votes.setdefault("crisis", []).append("OVERRIDE: " + "; ".join(crisis_reasons))

    regime = {"cycle_stage": cs, "stress_direction": sd, "inflation_regime": ir}
    votes = {"cycle_stage": cs_votes, "stress_direction": sd_votes, "inflation_regime": ir_votes}
    disagreements = {"cycle_stage": cs_dis, "stress_direction": sd_dis, "inflation_regime": ir_dis}
    tension = TENSIONS.get((cs, sd, ir))
    return regime, votes, disagreements, tension


def compute_conviction(disagreements: dict) -> float:
    n = sum(1 for v in disagreements.values() if v)
    return max(0.4, round(1.0 - n * 0.2, 2))


# ── Rules ─────────────────────────────────────────────────────────────────────


def check_rules(rules, raw, regime, portfolio=None):
    fired = []
    for rule in rules:
        match = True
        for key, val in rule.get("condition", {}).items():
            if key in ("cycle_stage", "stress_direction", "inflation_regime"):
                if regime.get(key) not in val:
                    match = False
                    break
            elif key in ("gold_pct_portfolio", "cash_pct"):
                if portfolio is None:
                    continue
                pv = portfolio.get(key)
                if pv is not None and not in_range(pv, val):
                    match = False
                    break
            else:
                iv = (raw.get(key) or {}).get("value")
                if iv is not None and not in_range(iv, val):
                    match = False
                    break
        if match:
            fired.append(rule)
    return fired


# ── Output ────────────────────────────────────────────────────────────────────


def build_json_output(sc):
    regime = sc.get("regime", {})
    conviction = compute_conviction(sc.get("disagreements", {}))
    tension = sc.get("tension")
    return {
        "regime": regime,
        "conviction": conviction,
        "tensions": [tension] if tension else [],
        "indicators": sc.get("raw", {}),
        "rules_fired": sc.get("rules_fired", []),
        "scored_at": sc.get("scored_at", ""),
        "pulled_at": sc.get("pulled_at", ""),
    }


def print_text_summary(sc):
    regime = sc.get("regime", {})
    cs = regime.get("cycle_stage", "?")
    sd = regime.get("stress_direction", "?")
    ir = regime.get("inflation_regime", "?")
    conviction = compute_conviction(sc.get("disagreements", {}))
    raw = sc.get("raw", {})
    tension = sc.get("tension")
    fired = sc.get("rules_fired", [])

    pulled = sum(1 for v in raw.values() if v.get("value") is not None)
    print(f"\n{'=' * 50}")
    print(f"🌍 MACRO REGIME: ({cs.upper()}, {sd.upper()}, {ir.upper()})")
    print(f"   Conviction: {conviction:.1f} | Indicators: {pulled}/16")
    print(f"{'=' * 50}")
    if tension:
        print(f"\n⚡ Tension: {tension['message'][:100]}")
    disagreeing = [k for k, v in sc.get("disagreements", {}).items() if v]
    if disagreeing:
        print(f"\n⚠️  Disagreements: {', '.join(disagreeing)}")
    if fired:
        print(f"\n📋 Rules fired ({len(fired)}):")
        for r in fired:
            sym = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r.get("confidence", ""), "⚪")
            print(f"   {sym} {r['id']}: {r['name']}")
            print(f"      Action: {r['action']}")
    print(f"\n   Scorecard: {SCORECARD_JSON}")
    print(f"   Scored at: {sc.get('scored_at', '?')[:19]}")


# ── CLI ───────────────────────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output scorecard as JSON")
@click.option("--text", "as_text", is_flag=True, default=False, help="Output human-readable summary")
@click.pass_context
def cli(ctx, as_json, as_text):
    """Macro Regime Gauge — classify the current macro environment."""
    if ctx.invoked_subcommand is None:
        sc = load_scorecard()
        if not sc:
            raise click.ClickException("No scorecard.json. Run 'gauge.py run' first.")
        if as_json:
            click.echo(json.dumps(build_json_output(sc), indent=2, default=str))
        else:
            print_text_summary(sc)


@cli.command()
def pull():
    """Fetch all 16 indicators from FRED + yfinance."""
    raw = pull_all()
    sc = load_scorecard()
    sc["raw"] = raw
    sc["pulled_at"] = datetime.utcnow().isoformat()
    save_scorecard(sc)
    pulled = sum(1 for v in raw.values() if v.get("value") is not None)
    print(f"\n✅ Pulled {pulled}/16 indicators. Saved to {SCORECARD_JSON}")


@cli.command()
def score():
    """Classify regime from raw data in scorecard.json."""
    sc = load_scorecard()
    raw = sc.get("raw", {})
    if not raw:
        raise click.ClickException("No raw data. Run 'pull' first.")
    cfg = load_config()
    regime, votes, disagreements, tension = score_all(raw, cfg)
    sc.update(
        {
            "regime": regime,
            "votes": {k: {s: list(v) for s, v in sv.items()} for k, sv in votes.items()},
            "disagreements": disagreements,
            "tension": tension,
            "scored_at": datetime.utcnow().isoformat(),
            "rules_fired": check_rules(load_rules(), raw, regime),
        }
    )
    save_scorecard(sc)
    cs, sd, ir = regime["cycle_stage"], regime["stress_direction"], regime["inflation_regime"]
    print(f"\n📊 Regime: ({cs}, {sd}, {ir}) | Conviction: {compute_conviction(disagreements):.1f}")
    if tension:
        print(f"⚡ Tension: {tension['message'][:80]}...")
    print(f"   Rules fired: {len(sc['rules_fired'])}")


@cli.command()
@click.option("--folio", is_flag=True, default=False, help="Load portfolio from folio.py for allocation rules.")
def check(folio):
    """Evaluate which rules fire and print them."""
    sc = load_scorecard()
    raw, regime = sc.get("raw", {}), sc.get("regime", {})
    if not regime:
        raise click.ClickException("No regime data. Run 'score' first.")

    portfolio = None
    if folio:
        portfolio = _fetch_folio_portfolio()
        if portfolio:
            print(
                f"  📦 Folio: total=${portfolio['total']:,.0f}, "
                f"gold={portfolio['gold_pct_portfolio']}%, cash={portfolio['cash_pct']}%"
            )
        else:
            print("  ⚠️  Folio data unavailable — allocation rules skipped.")

    fired = check_rules(load_rules(), raw, regime, portfolio)
    print(f"\n📋 Rules fired: {len(fired)}/{len(load_rules())}")
    cs2 = regime.get("cycle_stage")
    sd2 = regime.get("stress_direction")
    ir2 = regime.get("inflation_regime")
    print(f"   Regime: ({cs2}, {sd2}, {ir2})")
    for rule in fired:
        print(f"\n  [{rule.get('confidence', '?').upper()}] {rule['id']}: {rule['name']}")
        print(f"         Action: {rule['action']}")
        print(f"         Vault: {rule['vault']}")


@cli.command()
def run():
    """Pull → score → save history snapshot."""
    print("=== PULL ===")
    raw = pull_all()
    sc = load_scorecard()
    sc["raw"] = raw
    sc["pulled_at"] = datetime.utcnow().isoformat()

    print("\n=== SCORE ===")
    cfg = load_config()
    regime, votes, disagreements, tension = score_all(raw, cfg)
    sc.update(
        {
            "regime": regime,
            "votes": {k: {s: list(v) for s, v in sv.items()} for k, sv in votes.items()},
            "disagreements": disagreements,
            "tension": tension,
            "scored_at": datetime.utcnow().isoformat(),
            "rules_fired": check_rules(load_rules(), raw, regime),
        }
    )
    save_scorecard(sc)

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_file = HISTORY_DIR / f"{date.today()}.json"
    shutil.copy(SCORECARD_JSON, history_file)

    print_text_summary(sc)
    print(f"   History: {history_file}")


# ── Folio helper ──────────────────────────────────────────────────────────────


def _fetch_folio_portfolio():
    import re
    import subprocess

    folio_py = ROOT.parent / "folio" / "folio.py"
    folio_venv = ROOT.parent / "folio" / ".venv" / "bin" / "python"
    python_bin = str(folio_venv) if folio_venv.exists() else sys.executable
    if not folio_py.exists():
        return None
    try:
        result = subprocess.run([python_bin, str(folio_py), "show"], capture_output=True, text=True, timeout=15)
        if result.returncode != 0 or not result.stdout:
            return None
        holdings = {}
        total_value = 0.0
        for line in result.stdout.splitlines():
            m = re.match(r"^(\S+)\s+.+?\s+(\w+)\s+[\d.]+\s+\$?[\d,.]+\s+\$?[\d,.]+\s+\$?([\d,]+\.\d+)", line)
            if m:
                try:
                    val = float(m.group(3).replace(",", ""))
                    holdings[m.group(1)] = {"type": m.group(2), "value": val}
                    total_value += val
                except ValueError:
                    pass
        if not total_value or not holdings:
            return None
        gld = sum(v["value"] for k, v in holdings.items() if k in ("GLD", "GOLD", "IAU"))
        cash = sum(v["value"] for k, v in holdings.items() if v["type"] == "cash")
        return {
            "total": total_value,
            "holdings": holdings,
            "gold_pct_portfolio": round(gld / total_value * 100, 1),
            "cash_pct": round(cash / total_value * 100, 1),
        }
    except Exception as e:
        print(f"  WARN: folio parse failed: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    cli()
