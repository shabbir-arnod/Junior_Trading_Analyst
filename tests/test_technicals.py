import pandas as pd
import pytest

from analyst.analysis.technicals import compute_price_snapshot


def _make_history(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range(end="2026-07-09", periods=len(closes), freq="B", tz="UTC")
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


def test_basic_snapshot_fields():
    closes = [100 + i * 0.1 for i in range(300)]
    history = _make_history(closes)
    snapshot = compute_price_snapshot("TEST", history, info={"marketCap": 1e12, "averageVolume": 5e6})

    assert snapshot.ticker == "TEST"
    assert snapshot.current_price == pytest.approx(closes[-1])
    assert snapshot.market_cap == 1e12
    assert snapshot.sma_50 is not None
    assert snapshot.sma_200 is not None
    assert snapshot.fifty_two_week_high >= snapshot.current_price
    assert snapshot.fifty_two_week_low <= snapshot.current_price


def test_all_time_high_low_from_history():
    closes = [50] * 10 + [200] + [50] * 10 + [10] + [50] * 10
    history = _make_history(closes)
    snapshot = compute_price_snapshot("TEST", history)

    assert snapshot.all_time_high == pytest.approx(200 * 1.01)
    assert snapshot.all_time_low == pytest.approx(10 * 0.99)


def test_momentum_requires_enough_history():
    closes = [100, 101, 102]
    history = _make_history(closes)
    snapshot = compute_price_snapshot("TEST", history)

    assert snapshot.momentum_1m_pct is None
    assert snapshot.momentum_1y_pct is None


def test_day_change_pct():
    closes = [100, 110]
    history = _make_history(closes)
    snapshot = compute_price_snapshot("TEST", history)
    assert snapshot.day_change_pct == pytest.approx(10.0)


def test_empty_history_raises():
    history = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    with pytest.raises(ValueError):
        compute_price_snapshot("TEST", history)
