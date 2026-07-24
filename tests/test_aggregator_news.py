from pathlib import Path

from analyst.config import Settings
from analyst.data_sources.aggregator import get_industry_headlines


def _settings(newsapi_key: str | None) -> Settings:
    return Settings(
        anthropic_api_key=None,
        finnhub_api_key=None,
        newsapi_key=newsapi_key,
        fred_api_key=None,
        watchlist_path=Path("config/watchlist.yaml"),
    )


def test_get_industry_headlines_without_key_returns_empty():
    assert get_industry_headlines(_settings(None)) == []


def test_get_industry_headlines_swallows_provider_errors(monkeypatch):
    import analyst.data_sources.aggregator as aggregator

    class BoomProvider:
        def __init__(self, api_key):
            pass

        def search(self, query, limit=10):
            raise RuntimeError("network down")

    monkeypatch.setattr(aggregator, "NewsApiProvider", BoomProvider)
    assert get_industry_headlines(_settings("fake-key")) == []
