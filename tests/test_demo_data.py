from analyst.analysis.signal import compute_signal
from analyst.analysis.technicals import compute_price_snapshot
from analyst.data_sources.demo_data import DemoMarketDataProvider


def test_demo_provider_feeds_full_pipeline():
    provider = DemoMarketDataProvider()
    info = provider.get_info("NVDA")
    history = provider.get_price_history("NVDA")

    snapshot = compute_price_snapshot("NVDA", history, info)
    assert snapshot.current_price > 0
    assert snapshot.sma_200 is not None

    analyst = provider.get_analyst_view("NVDA")
    insider = provider.get_insider_activity("NVDA")
    signal = compute_signal("NVDA", snapshot, analyst, insider)
    assert signal.verdict != "Unrated"
    assert signal.composite_score is not None


def test_demo_provider_is_deterministic():
    a = DemoMarketDataProvider().get_price_history("AMD")
    b = DemoMarketDataProvider().get_price_history("AMD")
    assert a["Close"].iloc[-1] == b["Close"].iloc[-1]


def test_demo_news_is_watermarked():
    news = DemoMarketDataProvider().get_news("TSM")
    assert news
    assert all("[demo headline]" in item.title for item in news)
