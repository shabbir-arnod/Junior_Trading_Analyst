"""Historical backtest of the PRICE-ONLY composite signal.

This intentionally backtests only the momentum + trend components.
Analyst sentiment and insider activity aren't available as a true
point-in-time history from yfinance (only the current snapshot is), so
including them would either require lookahead bias (using today's
analyst rating to score yesterday) or be impossible. Every result from
this module is labelled "price-only" for that reason -- it validates a
narrower claim than the live composite signal, and callers must not
present it as validating the full 4-component score.

Method: at each historical rebalance point, compute the momentum/trend
components using only data available up to and including that point,
then look forward `horizon_days` trading days and record the actual
return. Bucketing by verdict and averaging the forward return across all
historical samples answers: "historically, when this price-only signal
said X, what tended to happen next?"
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analyst.analysis.signal import (
    VERDICT_THRESHOLDS,
    momentum_score,
    trend_score,
    verdict_for,
    weighted_composite,
)

MOMENTUM_3M_DAYS = 63
MOMENTUM_1Y_DAYS = 252
SMA_SHORT_DAYS = 50
SMA_LONG_DAYS = 200
MIN_TRAILING_DAYS = SMA_LONG_DAYS  # need a full trailing year for SMA200/1Y momentum


@dataclass
class BacktestBucket:
    verdict: str
    sample_count: int
    avg_forward_return_pct: float | None
    hit_rate_pct: float | None  # % of samples where forward return was positive


@dataclass
class BacktestResult:
    ticker: str
    horizon_days: int
    total_samples: int
    buckets: list[BacktestBucket] = field(default_factory=list)
    note: str = ""


def backtest_price_signal(
    ticker: str,
    history: pd.DataFrame,
    horizon_days: int = 20,
    step_days: int = 5,
) -> BacktestResult:
    """Vectorized backtest over the full history in `history`.

    step_days subsamples the daily series (default: weekly) so adjacent,
    highly-overlapping windows don't inflate the apparent sample count --
    the underlying data is still daily, just not every single day is used
    as a separate "independent" observation.
    """
    closes = history["Close"].dropna()
    n = len(closes)
    min_days_needed = MIN_TRAILING_DAYS + horizon_days
    if n < min_days_needed:
        return BacktestResult(
            ticker=ticker,
            horizon_days=horizon_days,
            total_samples=0,
            note=(
                "Not enough price history to backtest -- need at least "
                f"~{min_days_needed} trading days, have {n}."
            ),
        )

    sma_50 = closes.rolling(SMA_SHORT_DAYS).mean()
    sma_200 = closes.rolling(SMA_LONG_DAYS).mean()
    mom_3m = (closes / closes.shift(MOMENTUM_3M_DAYS) - 1) * 100
    mom_1y = (closes / closes.shift(MOMENTUM_1Y_DAYS) - 1) * 100
    forward_return_pct = (closes.shift(-horizon_days) / closes - 1) * 100

    verdict_returns: dict[str, list[float]] = {label: [] for _, label in VERDICT_THRESHOLDS}
    verdict_returns["Strongly Bearish"] = []

    start_idx = SMA_LONG_DAYS
    end_idx = n - horizon_days
    for i in range(start_idx, end_idx, step_days):
        m_score = momentum_score(mom_3m.iloc[i], mom_1y.iloc[i])
        t_score = trend_score(sma_50.iloc[i], sma_200.iloc[i])
        fwd = forward_return_pct.iloc[i]
        if pd.isna(fwd):
            continue
        components = {"Price momentum": m_score, "Trend (50d vs 200d SMA)": t_score}
        score = weighted_composite(components)
        if score is None:
            continue
        verdict = verdict_for(score)
        verdict_returns[verdict].append(float(fwd))

    buckets = []
    total_samples = 0
    order = [label for _, label in VERDICT_THRESHOLDS] + ["Strongly Bearish"]
    seen = set()
    ordered_labels = [label for label in order if not (label in seen or seen.add(label))]
    for label in ordered_labels:
        returns = verdict_returns.get(label, [])
        total_samples += len(returns)
        if returns:
            avg_return = sum(returns) / len(returns)
            hit_rate = sum(1 for r in returns if r > 0) / len(returns) * 100
        else:
            avg_return, hit_rate = None, None
        buckets.append(BacktestBucket(
            verdict=label, sample_count=len(returns),
            avg_forward_return_pct=avg_return, hit_rate_pct=hit_rate,
        ))

    note = (
        f"Price-only signal (momentum + trend, no analyst/insider data -- "
        f"those aren't available historically). Forward return measured "
        f"{horizon_days} trading days after each sample."
    )
    return BacktestResult(ticker=ticker, horizon_days=horizon_days, total_samples=total_samples,
                           buckets=buckets, note=note)
