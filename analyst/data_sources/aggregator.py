"""Fans a single ticker out to every configured provider and assembles a
StockBundle. yfinance (via MarketDataProvider) is always used as the
baseline since it needs no API key; Finnhub/NewsAPI enrich it when keys
are configured.
"""

from __future__ import annotations

from analyst.analysis.technicals import compute_price_snapshot
from analyst.config import Settings
from analyst.data_sources.base import MacroSnapshot, StockBundle
from analyst.data_sources.finnhub_provider import FinnhubProvider
from analyst.data_sources.fred_provider import FredProvider
from analyst.data_sources.market_data import MarketDataProvider
from analyst.data_sources.newsapi_provider import NewsApiProvider

MACRO_QUERY = (
    "(AI infrastructure OR semiconductor OR data center) AND "
    "(interest rate OR Federal Reserve OR inflation OR capex)"
)


def build_bundle(ticker: str, settings: Settings, market: MarketDataProvider | None = None) -> StockBundle:
    market = market or MarketDataProvider()
    bundle = StockBundle(ticker=ticker)

    info: dict = {}
    try:
        info = market.get_info(ticker)
        bundle.company_name = market.get_company_name(ticker, info)
        bundle.sector = market.get_sector(ticker, info)
    except Exception as exc:
        bundle.errors.append(f"info fetch failed: {exc}")

    try:
        history = market.get_price_history(ticker)
        bundle.price = compute_price_snapshot(ticker, history, info)
    except Exception as exc:
        bundle.errors.append(f"price history fetch failed: {exc}")

    try:
        bundle.analyst = market.get_analyst_view(ticker, info)
    except Exception as exc:
        bundle.errors.append(f"analyst view fetch failed: {exc}")

    try:
        bundle.financials = market.get_financials(ticker, info)
    except Exception as exc:
        bundle.errors.append(f"financials fetch failed: {exc}")

    try:
        bundle.insider = market.get_insider_activity(ticker)
    except Exception as exc:
        bundle.errors.append(f"insider activity fetch failed: {exc}")

    try:
        bundle.news = market.get_news(ticker)
    except Exception as exc:
        bundle.errors.append(f"news fetch failed: {exc}")

    if settings.has_finnhub:
        finnhub = FinnhubProvider(settings.finnhub_api_key)
        try:
            extra_news = finnhub.get_company_news(ticker)
            seen_titles = {n.title for n in bundle.news}
            bundle.news.extend(n for n in extra_news if n.title not in seen_titles)
        except Exception as exc:
            bundle.errors.append(f"finnhub news fetch failed: {exc}")

        try:
            finnhub_insider = finnhub.get_insider_activity(ticker)
            if finnhub_insider.transactions and (
                bundle.insider is None or not bundle.insider.transactions
            ):
                bundle.insider = finnhub_insider
        except Exception as exc:
            bundle.errors.append(f"finnhub insider fetch failed: {exc}")

    if settings.has_newsapi and bundle.company_name:
        newsapi = NewsApiProvider(settings.newsapi_key)
        try:
            extra_news = newsapi.search(f'"{bundle.company_name}" OR {ticker}')
            seen_titles = {n.title for n in bundle.news}
            bundle.news.extend(n for n in extra_news if n.title not in seen_titles)
        except Exception as exc:
            bundle.errors.append(f"newsapi fetch failed: {exc}")

    return bundle


def build_macro_snapshot(settings: Settings) -> MacroSnapshot:
    snapshot = MacroSnapshot()

    if settings.has_fred:
        try:
            indicators = FredProvider(settings.fred_api_key).get_macro_indicators()
            for name, value in indicators.items():
                if value is not None:
                    snapshot.notes.append(f"{name.replace('_', ' ')}: {value:g}")
        except Exception as exc:
            snapshot.notes.append(f"FRED macro fetch failed: {exc}")

    if settings.has_newsapi:
        try:
            snapshot.headlines = NewsApiProvider(settings.newsapi_key).search(MACRO_QUERY, limit=8)
        except Exception as exc:
            snapshot.notes.append(f"macro news fetch failed: {exc}")

    if not settings.has_fred and not settings.has_newsapi:
        snapshot.notes.append(
            "No FRED_API_KEY or NEWSAPI_KEY configured -- macro section skipped. "
            "See .env.example."
        )

    return snapshot
