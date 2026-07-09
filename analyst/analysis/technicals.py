"""Turns a raw OHLCV price history into a PriceSnapshot.

All-time high/low is approximated from the longest history the provider
returns (yfinance's "max" period for well-established tickers, less for
recent IPOs) -- it is labelled accordingly by the caller, not claimed to
be an exact all-time record sourced from exchange listing data.
"""

from __future__ import annotations

import pandas as pd

from analyst.data_sources.base import PriceSnapshot


def _momentum_pct(history: pd.DataFrame, trading_days_back: int, current_price: float) -> float | None:
    if len(history) <= trading_days_back:
        return None
    past_price = history["Close"].iloc[-1 - trading_days_back]
    if not past_price:
        return None
    return (current_price / past_price - 1) * 100


def compute_price_snapshot(
    ticker: str,
    history: pd.DataFrame,
    info: dict | None = None,
) -> PriceSnapshot:
    info = info or {}
    history = history.dropna(subset=["Close"])
    if history.empty:
        raise ValueError(f"Empty price history for {ticker}")

    current_price = float(history["Close"].iloc[-1])
    as_of = history.index[-1].to_pydatetime()

    prev_close = float(history["Close"].iloc[-2]) if len(history) > 1 else None
    day_change_pct = (current_price / prev_close - 1) * 100 if prev_close else None

    window_252 = history.tail(252)
    fifty_two_week_high = float(window_252["High"].max())
    fifty_two_week_low = float(window_252["Low"].min())

    all_time_high_idx = history["High"].idxmax()
    all_time_low_idx = history["Low"].idxmin()

    sma_50 = float(history["Close"].tail(50).mean()) if len(history) >= 50 else None
    sma_200 = float(history["Close"].tail(200).mean()) if len(history) >= 200 else None

    return PriceSnapshot(
        ticker=ticker,
        as_of=as_of,
        current_price=current_price,
        day_change_pct=day_change_pct,
        market_cap=info.get("marketCap"),
        avg_volume=info.get("averageVolume"),
        fifty_two_week_high=fifty_two_week_high,
        fifty_two_week_low=fifty_two_week_low,
        all_time_high=float(history.loc[all_time_high_idx, "High"]),
        all_time_high_date=all_time_high_idx.to_pydatetime(),
        all_time_low=float(history.loc[all_time_low_idx, "Low"]),
        all_time_low_date=all_time_low_idx.to_pydatetime(),
        sma_50=sma_50,
        sma_200=sma_200,
        momentum_1m_pct=_momentum_pct(history, 21, current_price),
        momentum_3m_pct=_momentum_pct(history, 63, current_price),
        momentum_6m_pct=_momentum_pct(history, 126, current_price),
        momentum_1y_pct=_momentum_pct(history, 252, current_price),
    )
