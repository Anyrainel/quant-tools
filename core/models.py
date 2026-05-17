"""Shared data models and utilities for quant-tools."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RegimeReading:
    """A single macro regime snapshot."""

    date: date
    debt_cycle_stage: str  # early | mid | late | depression | recovery
    stress_level: str  # calm | stable | elevated | acute | crisis
    inflation_regime: str  # deflation | low | stable | elevated | acute
    indicators: dict = field(default_factory=dict)
    # e.g. {"bbb_spread": 81.0, "vix": 17.5, "gold_yoy": 0.4681}

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "debt_cycle_stage": self.debt_cycle_stage,
            "stress_level": self.stress_level,
            "inflation_regime": self.inflation_regime,
            "indicators": self.indicators,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RegimeReading":
        return cls(
            date=date.fromisoformat(d["date"]),
            debt_cycle_stage=d["debt_cycle_stage"],
            stress_level=d["stress_level"],
            inflation_regime=d["inflation_regime"],
            indicators=d.get("indicators", {}),
        )


@dataclass
class Holding:
    """A single position in the portfolio."""

    ticker: str
    shares: float
    price: float
    value: float
    avg_cost: float
    total_return: float
    gain_pct: float
    asset_class: str = "other"
    source: str = "unknown"  # broker name (robinhood, etrade, manual)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "shares": self.shares,
            "price": self.price,
            "value": self.value,
            "avg_cost": self.avg_cost,
            "total_return": self.total_return,
            "gain_pct": self.gain_pct,
            "asset_class": self.asset_class,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Holding":
        return cls(
            ticker=d["ticker"],
            shares=d.get("shares", 0),
            price=d.get("price", 0),
            value=d.get("value", 0),
            avg_cost=d.get("avg_cost", 0),
            total_return=d.get("total_return", 0),
            gain_pct=d.get("gain_pct", 0),
            asset_class=d.get("asset_class", "other"),
            source=d.get("source", "unknown"),
        )


@dataclass
class PortfolioSnapshot:
    """Full portfolio at a point in time."""

    date: date
    total_value: float
    cash: float
    holdings: list[Holding] = field(default_factory=list)

    def allocation(self) -> dict[str, float]:
        """Return asset class → percentage."""
        by_class: dict[str, float] = {}
        for h in self.holdings:
            by_class[h.asset_class] = by_class.get(h.asset_class, 0) + h.value
        total = self.total_value or 1
        return {k: v / total for k, v in by_class.items()}

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "total_value": self.total_value,
            "cash": self.cash,
            "holdings": [h.to_dict() for h in self.holdings],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PortfolioSnapshot":
        return cls(
            date=date.fromisoformat(d["date"]),
            total_value=d["total_value"],
            cash=d.get("cash", 0),
            holdings=[Holding.from_dict(h) for h in d.get("holdings", [])],
        )


@dataclass
class SignalReport:
    """Structured output for the guidance engine."""

    date: date
    regime: RegimeReading
    portfolio: PortfolioSnapshot
    fired_rules: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    confidence: str = "medium"  # low | medium | high

    def to_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "regime": self.regime.to_dict(),
            "portfolio": self.portfolio.to_dict(),
            "fired_rules": self.fired_rules,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
        }
