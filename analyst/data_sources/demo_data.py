"""Offline demo provider: deterministic synthetic data per ticker.

Activated by setting the environment variable JTA_DEMO=1 before launching
the dashboard (or by passing this provider explicitly). Useful for trying
the UI with no internet access or API keys -- every number it produces is
fake and clearly watermarked in the UI.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from analyst.data_sources.base import (
    AnalystView,
    CompanyFinancials,
    EarningsOutlook,
    EpsEstimate,
    InsiderActivity,
    InsiderTransaction,
    NewsItem,
    OptionsSnapshot,
)

_DEMO_HEADLINES = [
    "{name} announces next-generation AI accelerator platform",
    "{name} beats quarterly revenue estimates on data center demand",
    "{name} signs multi-year AI infrastructure deal with hyperscaler",
    "Analysts raise price targets on {name} after strong guidance",
    "{name} expands manufacturing capacity to meet AI chip demand",
]


def _seed_for(symbol: str) -> int:
    return int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)


class DemoMarketDataProvider:
    """Duck-typed drop-in for MarketDataProvider with synthetic data."""

    def _rng(self, symbol: str) -> np.random.Generator:
        return np.random.default_rng(_seed_for(symbol))

    def get_price_history(self, symbol: str, period: str = "5y") -> pd.DataFrame:
        rng = self._rng(symbol)
        n_days = 1260 if period in ("5y", "max") else 504
        start_price = float(rng.uniform(20, 400))
        drift = rng.uniform(0.0002, 0.0012)
        steps = rng.normal(drift, 0.025, n_days)
        closes = start_price * np.exp(np.cumsum(steps))
        dates = pd.date_range(end=datetime.now(timezone.utc), periods=n_days, freq="B")
        return pd.DataFrame(
            {
                "Open": closes * (1 + rng.normal(0, 0.004, n_days)),
                "High": closes * (1 + np.abs(rng.normal(0, 0.012, n_days))),
                "Low": closes * (1 - np.abs(rng.normal(0, 0.012, n_days))),
                "Close": closes,
                "Volume": rng.integers(5_000_000, 60_000_000, n_days),
            },
            index=dates,
        )

    def get_info(self, symbol: str) -> dict:
        rng = self._rng(symbol)
        return {
            "longName": f"{symbol} (Demo Data) Inc.",
            "sector": "Technology (demo)",
            "marketCap": float(rng.uniform(2e10, 3e12)),
            "averageVolume": float(rng.uniform(5e6, 5e7)),
        }

    def get_company_name(self, symbol: str, info: dict | None = None) -> str:
        return f"{symbol} (Demo Data) Inc."

    def get_sector(self, symbol: str, info: dict | None = None) -> str:
        return "Technology (demo)"

    def get_analyst_view(self, symbol: str, info: dict | None = None) -> AnalystView:
        rng = self._rng(symbol)
        mean = float(rng.uniform(1.3, 3.5))
        upside = float(rng.uniform(-15, 45))
        keys = ["strong_buy", "buy", "hold", "hold", "sell"]
        return AnalystView(
            ticker=symbol,
            recommendation_key=keys[min(int(mean) - 1, 4)],
            recommendation_mean=round(mean, 1),
            num_analysts=int(rng.integers(8, 45)),
            target_mean=None,
            target_high=None,
            target_low=None,
            upside_pct=round(upside, 1),
        )

    def get_financials(self, symbol: str, info: dict | None = None) -> CompanyFinancials:
        rng = self._rng(symbol)
        return CompanyFinancials(
            ticker=symbol,
            revenue_ttm=float(rng.uniform(2e9, 1.5e11)),
            revenue_growth_yoy_pct=round(float(rng.uniform(-5, 90)), 1),
            gross_margin_pct=round(float(rng.uniform(35, 75)), 1),
            operating_margin_pct=round(float(rng.uniform(5, 45)), 1),
            net_margin_pct=round(float(rng.uniform(2, 35)), 1),
            eps_ttm=round(float(rng.uniform(0.5, 25)), 2),
            pe_ratio=round(float(rng.uniform(15, 80)), 1),
            forward_pe=round(float(rng.uniform(12, 60)), 1),
            free_cash_flow=float(rng.uniform(5e8, 5e10)),
        )

    def get_insider_activity(self, symbol: str, window_days: int = 180) -> InsiderActivity:
        rng = self._rng(symbol)
        n_buys = int(rng.integers(0, 4))
        n_sells = int(rng.integers(0, 6))
        transactions = []
        now = datetime.now(timezone.utc)
        for i in range(n_buys):
            transactions.append(InsiderTransaction(
                insider=f"Demo Insider {i + 1}", relation="Officer", transaction_type="buy",
                shares=float(rng.integers(1_000, 50_000)), value=float(rng.integers(100_000, 5_000_000)),
                date=now - timedelta(days=int(rng.integers(1, window_days))),
            ))
        for i in range(n_sells):
            transactions.append(InsiderTransaction(
                insider=f"Demo Insider {n_buys + i + 1}", relation="Officer", transaction_type="sell",
                shares=float(rng.integers(1_000, 80_000)), value=float(rng.integers(100_000, 9_000_000)),
                date=now - timedelta(days=int(rng.integers(1, window_days))),
            ))
        net_value = sum(t.value for t in transactions if t.transaction_type == "buy") - sum(
            t.value for t in transactions if t.transaction_type == "sell"
        )
        return InsiderActivity(
            ticker=symbol, window_days=window_days,
            buy_count=n_buys, sell_count=n_sells,
            net_shares=None, net_value=net_value if transactions else None,
            transactions=transactions,
        )

    def get_news(self, symbol: str, limit: int = 10) -> list[NewsItem]:
        rng = self._rng(symbol)
        name = symbol
        now = datetime.now(timezone.utc)
        items = []
        for i, template in enumerate(_DEMO_HEADLINES[:limit]):
            items.append(NewsItem(
                title=template.format(name=name) + " [demo headline]",
                publisher="DemoWire",
                link=None,
                published_at=now - timedelta(days=int(rng.integers(0, 10)) + i),
                summary=None,
            ))
        return items

    def get_options_snapshot(self, symbol: str, info: dict | None = None) -> OptionsSnapshot:
        rng = self._rng(symbol)
        current_price = float(rng.uniform(20, 400))
        put_call_ratio = float(rng.uniform(0.5, 1.6))
        atm_iv = float(rng.uniform(25, 70))
        realized_vol = float(atm_iv * rng.uniform(0.7, 1.15))
        return OptionsSnapshot(
            ticker=symbol,
            expiration="(demo)",
            current_price=current_price,
            put_call_volume_ratio=put_call_ratio,
            put_call_oi_ratio=put_call_ratio * float(rng.uniform(0.85, 1.15)),
            atm_implied_vol_pct=atm_iv,
            realized_vol_30d_pct=realized_vol,
            call_volume=float(rng.integers(1_000, 60_000)),
            put_volume=float(rng.integers(1_000, 60_000)),
        )

    def get_earnings_outlook(self, symbol: str) -> EarningsOutlook:
        rng = self._rng(symbol)
        now = datetime.now(timezone.utc)
        days_out = int(rng.integers(-5, 90))
        next_date = now + timedelta(days=days_out)
        revision_pct = float(rng.uniform(-8, 8))
        direction = "up" if revision_pct > 1 else ("down" if revision_pct < -1 else "flat")
        estimates = []
        for label in ("Current Qtr.", "Next Qtr.", "Current Year", "Next Year"):
            base = float(rng.uniform(0.5, 12))
            estimates.append(EpsEstimate(
                period_label=label,
                current_estimate=round(base, 2),
                estimate_90d_ago=round(base / (1 + revision_pct / 100), 2),
                num_analysts=int(rng.integers(5, 40)),
            ))
        return EarningsOutlook(
            ticker=symbol,
            next_earnings_date=next_date,
            days_until_earnings=days_out,
            estimates=estimates,
            revision_direction=direction,
        )
