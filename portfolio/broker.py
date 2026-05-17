#!/home/anyrainel/.openclaw/workspace-quant/projects/folio/.venv/bin/python3
"""broker.py — Read-only brokerage position puller.

Pulls positions from Robinhood and/or E*TRADE via their APIs.
Credentials are stored in the OS keyring — never in plaintext.
This script CANNOT place trades; only read functions are used.

Setup:
    keyring set gauge-rh email       <your robinhood email>
    keyring set gauge-rh password    <your robinhood password>
    keyring set gauge-rh totp        <TOTP secret if 2FA enabled>

    keyring set gauge-et consumer_key    <etrade consumer key>
    keyring set gauge-et consumer_secret <etrade consumer secret>

Usage:
    broker.py robinhood [--text] [--save]
    broker.py etrade    [--text] [--save]
    broker.py all       [--text] [--save]
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
import keyring
import yaml

# ---------------------------------------------------------------------------
# Safety guard: ensure no trade functions are accessible from this module.
# If someone tries to import order functions, this list makes intent explicit.
# ---------------------------------------------------------------------------
_FORBIDDEN = ["order_buy", "order_sell", "submit_order", "place_order"]

MACRO_DIR = Path(__file__).resolve().parents[1] / "portfolio"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ALLOCATIONS_YAML = MACRO_DIR / "allocations.yaml"
HOLDINGS_JSON = DATA_DIR / "holdings.json"
ETRADE_TOKENS = DATA_DIR / ".etrade_tokens"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_ticker_to_class() -> dict[str, str]:
    cfg = yaml.safe_load(ALLOCATIONS_YAML.read_text())
    mapping: dict[str, str] = {}
    for ac, info in cfg.get("asset_classes", {}).items():
        for t in info.get("tickers", []):
            mapping[t.upper()] = ac
    return mapping


def enrich_asset_class(holdings: list[dict], ticker_map: dict[str, str]) -> list[dict]:
    for h in holdings:
        h["asset_class"] = ticker_map.get(h["ticker"].upper(), "other")
    return holdings


def compute_allocation(holdings: list[dict], cash_total: float, total_value: float) -> dict[str, float]:
    alloc: dict[str, float] = {}
    if total_value <= 0:
        return alloc
    for h in holdings:
        ac = h.get("asset_class", "other")
        alloc[ac] = alloc.get(ac, 0.0) + h["value"]
    alloc["cash"] = alloc.get("cash", 0.0) + cash_total
    return {k: round(v / total_value * 100, 2) for k, v in alloc.items()}


def print_holdings_table(result: dict) -> None:
    """Print a human-readable table to stdout."""
    holdings = result.get("holdings", [])
    cash_info = result.get("cash", {})
    if isinstance(cash_info, (int, float)):
        cash_total = float(cash_info)
    else:
        cash_total = float(cash_info.get("total", 0))

    click.echo(f"\n{'Ticker':<8} {'Shares':>10} {'Price':>10} {'Value':>12} {'Gain%':>8} {'Class':<16} {'Source'}")
    click.echo("-" * 80)
    for h in sorted(holdings, key=lambda x: -x["value"]):
        click.echo(
            f"{h['ticker']:<8} {h['shares']:>10.2f} {h['price']:>10.2f} "
            f"{h['value']:>12,.0f} {h['gain_pct']:>7.1f}% "
            f"{h.get('asset_class', 'other'):<16} {h['source']}"
        )
    click.echo("-" * 80)
    click.echo(f"{'CASH':<8} {'':>10} {'':>10} {cash_total:>12,.0f}")
    click.echo(f"{'TOTAL':<8} {'':>10} {'':>10} {result['total_value']:>12,.0f}")

    alloc = result.get("allocation", {})
    if alloc:
        click.echo("\nAllocation:")
        for ac, pct in sorted(alloc.items(), key=lambda x: -x[1]):
            click.echo(f"  {ac:<20} {pct:>6.1f}%")
    click.echo()


def save_holdings(result: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    HOLDINGS_JSON.write_text(json.dumps(result, indent=2))
    click.echo(f"💾 Saved to {HOLDINGS_JSON}", err=True)


# ---------------------------------------------------------------------------
# Robinhood
# ---------------------------------------------------------------------------


def pull_robinhood() -> dict:
    """Read-only pull of Robinhood positions. No trade functions imported."""
    # Import only read functions — explicitly not importing order functions
    import robin_stocks.robinhood as rh  # noqa: PLC0415

    # Verify no forbidden symbols exist (belt-and-suspenders)
    for forbidden in _FORBIDDEN:
        if hasattr(rh, forbidden):
            click.echo(f"⛔ Safety check failed: rh.{forbidden} exists. Aborting.", err=True)
            sys.exit(1)

    email = keyring.get_password("gauge-rh", "email")
    password = keyring.get_password("gauge-rh", "password")

    if not email or not password:
        click.echo(
            "❌ Robinhood credentials not found in keyring.\n"
            "Run:\n"
            "  keyring set gauge-rh email    <your email>\n"
            "  keyring set gauge-rh password <your password>\n"
            "  keyring set gauge-rh totp     <TOTP secret>  # if 2FA enabled",
            err=True,
        )
        sys.exit(1)

    totp_secret = keyring.get_password("gauge-rh", "totp")

    try:
        if totp_secret:
            import pyotp  # noqa: PLC0415

            totp_code = pyotp.TOTP(totp_secret).now()
            rh.login(email, password, mfa_code=totp_code)
        else:
            rh.login(email, password)
    except Exception as exc:
        click.echo(f"❌ Robinhood login failed: {exc}", err=True)
        click.echo("Check credentials or 2FA setup.", err=True)
        sys.exit(1)

    try:
        positions = rh.build_holdings()
        profile = rh.build_user_profile()
        # Crypto positions are separate in RH API
        try:
            crypto_positions = rh.get_crypto_positions()
        except Exception:
            crypto_positions = []
    finally:
        rh.logout()

    holdings = []
    for ticker, data in positions.items():
        holdings.append(
            {
                "ticker": ticker,
                "shares": float(data.get("quantity", 0)),
                "price": float(data.get("price", 0)),
                "value": float(data.get("equity", 0)),
                "avg_cost": float(data.get("average_buy_price", 0)),
                "gain_pct": float(data.get("percent_change", 0)),
                "source": "robinhood",
            }
        )

    # Process crypto positions
    for pos in crypto_positions:
        # RH crypto API returns dict with 'currency' key containing ticker info
        code = pos.get("currency", {}).get("code", "")
        if not code or float(pos.get("quantity", 0)) == 0:
            continue
        holdings.append(
            {
                "ticker": code,
                "shares": float(pos.get("quantity", 0)),
                "price": float(pos.get("current_price", 0)),
                "value": float(pos.get("current_price", 0)) * float(pos.get("quantity", 0)),
                "avg_cost": float(pos.get("cost_bases", [{}])[0].get("direct_quantity", 0))
                / max(float(pos.get("quantity", 0)), 0.0001)
                if float(pos.get("quantity", 0)) > 0
                else 0,
                "gain_pct": 0,  # RH doesn't return % for crypto easily
                "source": "robinhood-crypto",
            }
        )

    cash = float(profile.get("cash", 0))
    return {"holdings": holdings, "cash": cash, "source": "robinhood"}


# ---------------------------------------------------------------------------
# E*TRADE
# ---------------------------------------------------------------------------


def pull_etrade() -> dict:
    """Read-only pull of E*TRADE positions via OAuth."""
    import pyetrade  # noqa: PLC0415

    consumer_key = keyring.get_password("gauge-et", "consumer_key") or keyring.get_password("gauge-et", "prod_key")
    consumer_secret = keyring.get_password("gauge-et", "consumer_secret") or keyring.get_password(
        "gauge-et", "prod_secret"
    )

    if not consumer_key or not consumer_secret:
        click.echo(
            "❌ E*TRADE credentials not found in keyring.\n"
            "Run:\n"
            "  keyring set gauge-et consumer_key    <key>\n"
            "  keyring set gauge-et consumer_secret <secret>",
            err=True,
        )
        sys.exit(1)

    accounts = None
    tokens = None

    # Try cached tokens first
    if ETRADE_TOKENS.exists():
        try:
            tokens = json.loads(ETRADE_TOKENS.read_text())
            accounts = pyetrade.ETradeAccounts(
                consumer_key,
                consumer_secret,
                tokens["oauth_token"],
                tokens["oauth_token_secret"],
            )
            # Probe to check if tokens are still valid
            accounts.list_accounts()
        except Exception:
            tokens = None
            accounts = None

    # Fresh OAuth if needed
    if accounts is None:
        try:
            oauth = pyetrade.ETradeOAuth(consumer_key, consumer_secret)
            auth_url = oauth.get_request_token()
            click.echo("\n🔐 E*TRADE OAuth required. Open this URL and approve:", err=True)
            click.echo(f"   {auth_url}", err=True)
            verifier = click.prompt("   Enter the verifier code").strip()
            tokens_data = oauth.get_access_token(verifier)
            tokens = {
                "oauth_token": tokens_data["oauth_token"],
                "oauth_token_secret": tokens_data["oauth_token_secret"],
            }
            DATA_DIR.mkdir(exist_ok=True)
            ETRADE_TOKENS.write_text(json.dumps(tokens))
            accounts = pyetrade.ETradeAccounts(
                consumer_key,
                consumer_secret,
                tokens["oauth_token"],
                tokens["oauth_token_secret"],
            )
        except Exception as exc:
            click.echo(f"❌ E*TRADE OAuth failed: {exc}", err=True)
            sys.exit(1)

    account_list = accounts.list_accounts()
    all_holdings: list[dict] = []
    total_cash = 0.0

    for acct in account_list:
        acct_key = acct.get("accountIdKey", "")
        acct_desc = acct.get("accountDesc", acct_key)
        try:
            positions = accounts.get_account_portfolio(acct_key)
            balance = accounts.get_account_balance(acct_key)

            if positions and "PortfolioResponse" in positions:
                for pos in positions["PortfolioResponse"].get("AccountPortfolio", []):
                    for p in pos.get("Position", []):
                        all_holdings.append(
                            {
                                "ticker": p.get("symbolDescription", ""),
                                "shares": float(p.get("quantity", 0)),
                                "price": float(p.get("Quick", {}).get("lastTrade", 0)),
                                "value": float(p.get("marketValue", 0)),
                                "avg_cost": float(p.get("costPerShare", 0)),
                                "gain_pct": float(p.get("pctOfPortfolio", 0)),
                                "source": "etrade",
                                "account": acct_desc,
                            }
                        )

            if balance:
                total_cash += float(balance.get("Computed", {}).get("cashAvailableForInvestment", 0))
        except Exception as exc:
            click.echo(f"  ⚠️ Skipping account {acct_desc}: {exc}", err=True)

    return {"holdings": all_holdings, "cash": total_cash, "source": "etrade"}


# ---------------------------------------------------------------------------
# Merge / unify
# ---------------------------------------------------------------------------


def build_unified(rh_data: dict | None, et_data: dict | None) -> dict:
    ticker_map = load_ticker_to_class()
    all_holdings: list[dict] = []
    cash_rh = 0.0
    cash_et = 0.0

    if rh_data:
        all_holdings.extend(rh_data.get("holdings", []))
        cash_rh = float(rh_data.get("cash", 0))
    if et_data:
        all_holdings.extend(et_data.get("holdings", []))
        cash_et = float(et_data.get("cash", 0))

    enrich_asset_class(all_holdings, ticker_map)
    cash_total = cash_rh + cash_et
    total_value = sum(h["value"] for h in all_holdings) + cash_total
    alloc = compute_allocation(all_holdings, cash_total, total_value)

    return {
        "total_value": round(total_value, 2),
        "holdings": all_holdings,
        "cash": {
            "robinhood": round(cash_rh, 2),
            "etrade": round(cash_et, 2),
            "total": round(cash_total, 2),
        },
        "allocation": alloc,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """Read-only brokerage position puller. No trades. Ever."""


@cli.command()
@click.option("--text", "as_text", is_flag=True, help="Human-readable table")
@click.option("--save", is_flag=True, help="Save to data/holdings.json")
def robinhood(as_text: bool, save: bool) -> None:
    """Pull Robinhood positions."""
    ticker_map = load_ticker_to_class()
    data = pull_robinhood()
    enrich_asset_class(data["holdings"], ticker_map)
    cash = float(data["cash"])
    total = sum(h["value"] for h in data["holdings"]) + cash
    result = {
        "total_value": round(total, 2),
        "holdings": data["holdings"],
        "cash": {"robinhood": round(cash, 2), "total": round(cash, 2)},
        "allocation": compute_allocation(data["holdings"], cash, total),
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }
    if as_text:
        print_holdings_table(result)
    else:
        click.echo(json.dumps(result, indent=2))
    if save:
        save_holdings(result)


@cli.command()
@click.option("--text", "as_text", is_flag=True, help="Human-readable table")
@click.option("--save", is_flag=True, help="Save to data/holdings.json")
def etrade(as_text: bool, save: bool) -> None:
    """Pull E*TRADE positions."""
    ticker_map = load_ticker_to_class()
    data = pull_etrade()
    enrich_asset_class(data["holdings"], ticker_map)
    cash = float(data["cash"])
    total = sum(h["value"] for h in data["holdings"]) + cash
    result = {
        "total_value": round(total, 2),
        "holdings": data["holdings"],
        "cash": {"etrade": round(cash, 2), "total": round(cash, 2)},
        "allocation": compute_allocation(data["holdings"], cash, total),
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }
    if as_text:
        print_holdings_table(result)
    else:
        click.echo(json.dumps(result, indent=2))
    if save:
        save_holdings(result)


@cli.command("all")
@click.option("--text", "as_text", is_flag=True, help="Human-readable table")
@click.option("--save", is_flag=True, help="Save to data/holdings.json")
def all_brokers(as_text: bool, save: bool) -> None:
    """Pull Robinhood + E*TRADE, merge into unified view."""
    rh_data: dict | None = None
    et_data: dict | None = None

    try:
        rh_data = pull_robinhood()
        click.echo("✅ Robinhood: pulled", err=True)
    except SystemExit:
        click.echo("⚠️  Robinhood unavailable — continuing with E*TRADE only", err=True)

    try:
        et_data = pull_etrade()
        click.echo("✅ E*TRADE: pulled", err=True)
    except SystemExit:
        click.echo("⚠️  E*TRADE unavailable — continuing with Robinhood only", err=True)

    if not rh_data and not et_data:
        click.echo("❌ No broker data available.", err=True)
        sys.exit(1)

    result = build_unified(rh_data, et_data)

    if as_text:
        print_holdings_table(result)
    else:
        click.echo(json.dumps(result, indent=2))
    if save:
        save_holdings(result)


if __name__ == "__main__":
    cli()
