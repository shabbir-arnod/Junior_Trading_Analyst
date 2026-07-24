import pandas as pd
import pytest

from analyst.config import Settings
from analyst.data_sources.base import AnalystView, CompanyFinancials, InsiderActivity, NewsItem
from analyst.report.builder import build_report


class FakeMarketDataProvider:
    """Duck-typed stand-in for MarketDataProvider with no network calls."""

    def get_info(self, symbol):
        return {"longName": f"{symbol} Inc.", "sector": "Technology", "marketCap": 1e12}

    def get_company_name(self, symbol, info=None):
        return f"{symbol} Inc."

    def get_sector(self, symbol, info=None):
        return "Technology"

    def get_price_history(self, symbol, period="5y"):
        dates = pd.date_range(end="2026-07-09", periods=260, freq="B", tz="UTC")
        closes = [100 + i * 0.05 for i in range(260)]
        return pd.DataFrame(
            {
                "Open": closes,
                "High": [c * 1.01 for c in closes],
                "Low": [c * 0.99 for c in closes],
                "Close": closes,
                "Volume": [1_000_000] * len(closes),
            },
            index=dates,
        )

    def get_analyst_view(self, symbol, info=None):
        return AnalystView(ticker=symbol, recommendation_key="buy", recommendation_mean=2.0, num_analysts=10)

    def get_financials(self, symbol, info=None):
        return CompanyFinancials(ticker=symbol, revenue_ttm=5e10, revenue_growth_yoy_pct=15.0)

    def get_insider_activity(self, symbol, window_days=180):
        return InsiderActivity(ticker=symbol, window_days=window_days)

    def get_news(self, symbol, limit=10):
        return [NewsItem(title=f"{symbol} announces new AI chip", publisher="TestWire", link=None, published_at=None)]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        gemini_api_key=None,
        finnhub_api_key=None,
        newsapi_key=None,
        fred_api_key=None,
        watchlist_path=tmp_path / "watchlist.yaml",
    )


def test_build_report_contains_all_tickers(settings):
    report = build_report(["NVDA", "AMD"], settings, include_llm=False, market=FakeMarketDataProvider())
    assert "NVDA" in report
    assert "AMD" in report
    assert "Watchlist Summary" in report
    assert "Disclaimer" in report


def test_build_report_skips_llm_without_key(settings):
    report = build_report(["NVDA"], settings, include_llm=True, market=FakeMarketDataProvider())
    assert "Analyst Note (AI-synthesized)" not in report


def test_build_report_includes_news_and_financials(settings):
    report = build_report(["NVDA"], settings, include_llm=False, market=FakeMarketDataProvider())
    assert "announces new AI chip" in report
    assert "Revenue (TTM)" in report
