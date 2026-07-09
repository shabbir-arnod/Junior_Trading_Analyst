"""Primary market data provider, backed by yfinance.

Needs no API key, so it's the baseline every report can rely on. Every
public method is defensive: yfinance's schema shifts between versions and
some fields are simply unavailable for some tickers, so failures are
caught and surfaced as strings rather than raising.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from analyst.data_sources.base import (
    AnalystView,
    CompanyFinancials,
    InsiderActivity,
    InsiderTransaction,
    NewsItem,
)


def _to_datetime(value) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return pd.to_datetime(value, utc=True).to_pydatetime()
    except (ValueError, TypeError, OverflowError):
        return None


class MarketDataProvider:
    """Thin wrapper around yfinance.Ticker with defensive field access."""

    def __init__(self):
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "yfinance is required. Install dependencies with "
                "`pip install -r requirements.txt`."
            ) from exc
        self._yf = yf

    def _ticker(self, symbol: str):
        return self._yf.Ticker(symbol)

    def get_price_history(self, symbol: str, period: str = "5y") -> pd.DataFrame:
        history = self._ticker(symbol).history(period=period, auto_adjust=False)
        if history is None or history.empty:
            raise ValueError(f"No price history returned for {symbol}")
        return history

    def get_info(self, symbol: str) -> dict:
        t = self._ticker(symbol)
        try:
            return dict(t.get_info())
        except Exception:
            return dict(getattr(t, "info", None) or {})

    def get_company_name(self, symbol: str, info: dict | None = None) -> str | None:
        info = info if info is not None else self.get_info(symbol)
        return info.get("longName") or info.get("shortName")

    def get_sector(self, symbol: str, info: dict | None = None) -> str | None:
        info = info if info is not None else self.get_info(symbol)
        return info.get("sector") or info.get("industry")

    def get_analyst_view(self, symbol: str, info: dict | None = None) -> AnalystView:
        info = info if info is not None else self.get_info(symbol)
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        target_mean = info.get("targetMeanPrice")
        upside_pct = None
        if current_price and target_mean:
            try:
                upside_pct = (float(target_mean) / float(current_price) - 1) * 100
            except (TypeError, ZeroDivisionError):
                upside_pct = None
        return AnalystView(
            ticker=symbol,
            recommendation_key=info.get("recommendationKey"),
            recommendation_mean=info.get("recommendationMean"),
            num_analysts=info.get("numberOfAnalystOpinions"),
            target_mean=target_mean,
            target_high=info.get("targetHighPrice"),
            target_low=info.get("targetLowPrice"),
            upside_pct=upside_pct,
        )

    def get_financials(self, symbol: str, info: dict | None = None) -> CompanyFinancials:
        info = info if info is not None else self.get_info(symbol)

        def pct(key: str) -> float | None:
            value = info.get(key)
            return value * 100 if isinstance(value, (int, float)) else None

        return CompanyFinancials(
            ticker=symbol,
            revenue_ttm=info.get("totalRevenue"),
            revenue_growth_yoy_pct=pct("revenueGrowth"),
            gross_margin_pct=pct("grossMargins"),
            operating_margin_pct=pct("operatingMargins"),
            net_margin_pct=pct("profitMargins"),
            eps_ttm=info.get("trailingEps"),
            pe_ratio=info.get("trailingPE"),
            forward_pe=info.get("forwardPE"),
            free_cash_flow=info.get("freeCashflow"),
            debt_to_equity=info.get("debtToEquity"),
        )

    def get_insider_activity(self, symbol: str, window_days: int = 180) -> InsiderActivity:
        activity = InsiderActivity(ticker=symbol, window_days=window_days)
        try:
            df = self._ticker(symbol).insider_transactions
        except Exception:
            df = None
        if df is None or df.empty:
            return activity

        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=window_days)
        for _, row in df.iterrows():
            start_date = _to_datetime(row.get("Start Date") or row.get("Date"))
            if start_date is not None and start_date < cutoff:
                continue
            text = str(row.get("Text", "")).lower()
            if "sale" in text or "sell" in text:
                ttype = "sell"
            elif "purchase" in text or "buy" in text:
                ttype = "buy"
            else:
                ttype = "other"
            shares = row.get("Shares")
            value = row.get("Value")
            activity.transactions.append(
                InsiderTransaction(
                    insider=str(row.get("Insider", "Unknown")),
                    relation=row.get("Position"),
                    transaction_type=ttype,
                    shares=float(shares) if pd.notna(shares) else None,
                    value=float(value) if pd.notna(value) else None,
                    date=start_date,
                )
            )

        activity.buy_count = sum(1 for t in activity.transactions if t.transaction_type == "buy")
        activity.sell_count = sum(1 for t in activity.transactions if t.transaction_type == "sell")
        net_shares = 0.0
        net_value = 0.0
        has_shares = has_value = False
        for t in activity.transactions:
            sign = 1 if t.transaction_type == "buy" else (-1 if t.transaction_type == "sell" else 0)
            if t.shares is not None:
                net_shares += sign * t.shares
                has_shares = True
            if t.value is not None:
                net_value += sign * t.value
                has_value = True
        activity.net_shares = net_shares if has_shares else None
        activity.net_value = net_value if has_value else None
        return activity

    def get_news(self, symbol: str, limit: int = 10) -> list[NewsItem]:
        try:
            raw_items = self._ticker(symbol).news or []
        except Exception:
            raw_items = []
        items: list[NewsItem] = []
        for raw in raw_items[:limit]:
            content = raw.get("content", raw)
            title = content.get("title") or raw.get("title")
            if not title:
                continue
            link = (content.get("canonicalUrl") or {}).get("url") or raw.get("link")
            publisher = (content.get("provider") or {}).get("displayName") or raw.get("publisher")
            published = content.get("pubDate") or raw.get("providerPublishTime")
            items.append(
                NewsItem(
                    title=title,
                    publisher=publisher,
                    link=link,
                    published_at=_to_datetime(published),
                    summary=content.get("summary"),
                )
            )
        return items
