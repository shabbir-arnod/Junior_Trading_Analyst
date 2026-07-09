from analyst.analysis.signal import compute_signal
from analyst.data_sources.base import (
    AnalystView,
    InsiderActivity,
    InsiderTransaction,
    PriceSnapshot,
)


def test_strongly_bullish_signal():
    price = PriceSnapshot(
        ticker="AAA",
        current_price=100,
        fifty_two_week_high=150,
        fifty_two_week_low=80,
        sma_50=105,
        sma_200=90,
        momentum_3m_pct=25,
        momentum_1y_pct=40,
    )
    analyst = AnalystView(ticker="AAA", recommendation_mean=1.2, upside_pct=20)
    insider = InsiderActivity(
        ticker="AAA",
        transactions=[
            InsiderTransaction("A", "CEO", "buy", 1000, 6_000_000, None),
        ],
        buy_count=1,
        sell_count=0,
        net_shares=1000,
        net_value=6_000_000,
    )

    signal = compute_signal("AAA", price, analyst, insider)
    assert signal.composite_score > 0.5
    assert signal.verdict == "Strongly Bullish"
    assert signal.confidence == "High"


def test_strongly_bearish_signal():
    price = PriceSnapshot(
        ticker="BBB",
        current_price=50,
        fifty_two_week_high=150,
        fifty_two_week_low=45,
        sma_50=55,
        sma_200=90,
        momentum_3m_pct=-30,
        momentum_1y_pct=-50,
    )
    analyst = AnalystView(ticker="BBB", recommendation_mean=4.8, upside_pct=-30)
    insider = InsiderActivity(
        ticker="BBB",
        transactions=[
            InsiderTransaction("B", "CFO", "sell", 5000, -8_000_000, None),
        ],
        buy_count=0,
        sell_count=1,
        net_shares=-5000,
        net_value=-8_000_000,
    )

    signal = compute_signal("BBB", price, analyst, insider)
    assert signal.composite_score < -0.5
    assert signal.verdict == "Strongly Bearish"


def test_no_data_returns_unrated():
    signal = compute_signal("CCC", None, None, None)
    assert signal.composite_score is None
    assert signal.verdict == "Unrated"
    assert signal.confidence == "Low"


def test_partial_data_lowers_confidence():
    analyst = AnalystView(ticker="DDD", recommendation_mean=2.0)
    signal = compute_signal("DDD", None, analyst, None)
    assert signal.composite_score is not None
    assert signal.confidence == "Low"


def test_timing_note_flags_near_high_bullish():
    price = PriceSnapshot(
        ticker="EEE",
        current_price=148,
        fifty_two_week_high=150,
        fifty_two_week_low=80,
        sma_50=145,
        sma_200=120,
        momentum_3m_pct=20,
        momentum_1y_pct=30,
    )
    analyst = AnalystView(ticker="EEE", recommendation_mean=1.5)
    signal = compute_signal("EEE", price, analyst, None)
    assert "52-week high" in signal.timing_note
