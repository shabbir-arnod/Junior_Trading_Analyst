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


def test_demo_options_snapshot_has_consistent_ratios():
    snap = DemoMarketDataProvider().get_options_snapshot("NVDA")
    assert snap.put_call_volume_ratio > 0
    assert snap.atm_implied_vol_pct > 0
    assert snap.realized_vol_30d_pct > 0
    assert snap.expiration == "(demo)"


def test_demo_earnings_outlook_revision_direction_matches_estimates():
    outlook = DemoMarketDataProvider().get_earnings_outlook("AMD")
    assert outlook.revision_direction in ("up", "down", "flat")
    assert len(outlook.estimates) == 4
    for est in outlook.estimates:
        assert est.current_estimate > 0
        assert est.num_analysts >= 5
