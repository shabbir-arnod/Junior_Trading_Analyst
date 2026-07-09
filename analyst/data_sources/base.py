"""Shared data contracts for every data source provider.

Providers (market_data.py, finnhub_provider.py, newsapi_provider.py,
fred_provider.py) all populate these same dataclasses so the analysis
layer never needs to know which provider a field came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceSnapshot:
    ticker: str
    currency: str = "USD"
    as_of: datetime | None = None
    current_price: float | None = None
    day_change_pct: float | None = None
    market_cap: float | None = None
    avg_volume: float | None = None

    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    all_time_high: float | None = None
    all_time_high_date: datetime | None = None
    all_time_low: float | None = None
    all_time_low_date: datetime | None = None

    sma_50: float | None = None
    sma_200: float | None = None
    momentum_1m_pct: float | None = None
    momentum_3m_pct: float | None = None
    momentum_6m_pct: float | None = None
    momentum_1y_pct: float | None = None


@dataclass
class AnalystView:
    ticker: str
    recommendation_key: str | None = None  # e.g. strongBuy/buy/hold/sell/strongSell
    recommendation_mean: float | None = None  # 1.0 (strong buy) - 5.0 (strong sell)
    num_analysts: int | None = None
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    upside_pct: float | None = None  # vs current price


@dataclass
class InsiderTransaction:
    insider: str
    relation: str | None
    transaction_type: str  # "buy" | "sell" | "other"
    shares: float | None
    value: float | None
    date: datetime | None


@dataclass
class InsiderActivity:
    ticker: str
    window_days: int = 180
    buy_count: int = 0
    sell_count: int = 0
    net_shares: float | None = None
    net_value: float | None = None
    transactions: list[InsiderTransaction] = field(default_factory=list)


@dataclass
class NewsItem:
    title: str
    publisher: str | None
    link: str | None
    published_at: datetime | None
    summary: str | None = None


@dataclass
class CompanyFinancials:
    ticker: str
    revenue_ttm: float | None = None
    revenue_growth_yoy_pct: float | None = None
    gross_margin_pct: float | None = None
    operating_margin_pct: float | None = None
    net_margin_pct: float | None = None
    eps_ttm: float | None = None
    pe_ratio: float | None = None
    forward_pe: float | None = None
    free_cash_flow: float | None = None
    debt_to_equity: float | None = None


@dataclass
class MacroSnapshot:
    headlines: list[NewsItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class StockBundle:
    """Everything gathered for one ticker, feeding the analysis layer."""

    ticker: str
    company_name: str | None = None
    sector: str | None = None
    price: PriceSnapshot | None = None
    analyst: AnalystView | None = None
    insider: InsiderActivity | None = None
    news: list[NewsItem] = field(default_factory=list)
    financials: CompanyFinancials | None = None
    errors: list[str] = field(default_factory=list)
