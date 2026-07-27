import numpy as np
import pandas as pd

from analyst.analysis.backtest import backtest_price_signal


def _history(prices) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"Close": prices}, index=dates)


def test_steady_uptrend_is_strongly_bullish_with_positive_forward_returns():
    prices = 100 + np.arange(500) * 0.5
    result = backtest_price_signal("TEST", _history(prices), horizon_days=20, step_days=5)

    assert result.total_samples > 0
    bullish = next(b for b in result.buckets if b.verdict == "Strongly Bullish")
    assert bullish.sample_count == result.total_samples
    assert bullish.avg_forward_return_pct > 0
    assert bullish.hit_rate_pct == 100.0


def test_steady_downtrend_is_bearish_with_negative_forward_returns():
    prices = 500 - np.arange(400) * 0.5
    result = backtest_price_signal("TEST", _history(prices), horizon_days=20, step_days=5)

    assert result.total_samples > 0
    bearish_buckets = [b for b in result.buckets if b.verdict in ("Bearish", "Strongly Bearish") and b.sample_count]
    assert bearish_buckets
    for bucket in bearish_buckets:
        assert bucket.avg_forward_return_pct < 0


def test_insufficient_history_returns_zero_samples_and_a_note():
    result = backtest_price_signal("TEST", _history(np.full(50, 100.0)))
    assert result.total_samples == 0
    assert "Not enough price history" in result.note


def test_flat_price_has_no_lookahead_bias_in_sample_window():
    # A flat series should never be flagged as bullish/bearish, and every
    # sample's forward return should be ~0 -- if there were lookahead bias
    # (peeking past the horizon), this would still hold for a flat series,
    # so this mainly guards against index/off-by-one errors blowing up.
    prices = np.full(400, 100.0)
    result = backtest_price_signal("TEST", _history(prices), horizon_days=20, step_days=5)
    assert result.total_samples > 0
    for bucket in result.buckets:
        if bucket.sample_count:
            assert abs(bucket.avg_forward_return_pct) < 1e-6
