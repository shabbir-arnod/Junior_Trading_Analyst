"""Composite Bullish/Bearish signal generation.

Combines analyst sentiment, price momentum/trend, and insider activity
into a single -1..+1 score with a human-readable verdict and a timing
note. This is a heuristic aggregation of public data, NOT financial
advice -- see the disclaimer emitted alongside every report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analyst.data_sources.base import AnalystView, InsiderActivity, PriceSnapshot

VERDICT_THRESHOLDS = (
    (0.5, "Strongly Bullish"),
    (0.15, "Bullish"),
    (-0.15, "Neutral"),
    (-0.5, "Bearish"),
)

COMPONENT_WEIGHTS = {
    "Analyst sentiment": 0.4,
    "Price momentum": 0.3,
    "Trend (50d vs 200d SMA)": 0.15,
    "Insider activity": 0.15,
}


def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def weighted_composite(components: dict[str, float | None]) -> float | None:
    """Renormalized weighted average over whichever named components (keys
    from COMPONENT_WEIGHTS) are not None. Public so the backtester computes
    the identical composite score formula used in production, just fed
    point-in-time historical inputs instead of live ones."""
    available = {k: v for k, v in components.items() if v is not None}
    if not available:
        return None
    total_weight = sum(COMPONENT_WEIGHTS[name] for name in available)
    return sum(COMPONENT_WEIGHTS[name] * value for name, value in available.items()) / total_weight


@dataclass
class StockSignal:
    ticker: str
    composite_score: float | None
    verdict: str
    confidence: str
    rationale: list[str] = field(default_factory=list)
    timing_note: str = ""


def _analyst_component(analyst: AnalystView | None) -> float | None:
    if analyst is None:
        return None
    if analyst.recommendation_mean is not None:
        return _clip((3 - analyst.recommendation_mean) / 2)
    if analyst.upside_pct is not None:
        return _clip(analyst.upside_pct / 20)
    return None


def momentum_score(momentum_3m_pct: float | None, momentum_1y_pct: float | None) -> float | None:
    """Public so the backtester can reproduce this exact formula against
    historical (point-in-time) momentum figures."""
    samples = [m for m in (momentum_3m_pct, momentum_1y_pct) if m is not None]
    if not samples:
        return None
    avg = sum(samples) / len(samples)
    return _clip(avg / 30)


def trend_score(sma_50: float | None, sma_200: float | None) -> float | None:
    """Public so the backtester can reproduce this exact formula against
    historical (point-in-time) SMA values."""
    if not sma_50 or not sma_200:
        return None
    return _clip((sma_50 / sma_200 - 1) * 10)


def _momentum_component(price: PriceSnapshot | None) -> float | None:
    if price is None:
        return None
    return momentum_score(price.momentum_3m_pct, price.momentum_1y_pct)


def _trend_component(price: PriceSnapshot | None) -> float | None:
    if price is None:
        return None
    return trend_score(price.sma_50, price.sma_200)


def _insider_component(insider: InsiderActivity | None) -> float | None:
    if insider is None or not insider.transactions:
        return None
    if insider.net_value:
        return _clip(insider.net_value / 5_000_000)
    net_count = insider.buy_count - insider.sell_count
    total = insider.buy_count + insider.sell_count
    return _clip(net_count / total) if total else None


def verdict_for(score: float) -> str:
    for threshold, label in VERDICT_THRESHOLDS:
        if score >= threshold:
            return label
    return "Strongly Bearish"


def _timing_note(price: PriceSnapshot | None, verdict: str) -> str:
    if price is None or not price.current_price or not price.fifty_two_week_high or not price.fifty_two_week_low:
        return "Insufficient price history to judge entry timing."

    pct_from_high = (price.current_price / price.fifty_two_week_high - 1) * 100
    pct_above_low = (price.current_price / price.fifty_two_week_low - 1) * 100
    near_high = pct_from_high >= -5
    near_low = pct_above_low <= 10
    bullish = verdict in ("Bullish", "Strongly Bullish")
    bearish = verdict in ("Bearish", "Strongly Bearish")

    if near_high and bullish:
        return (
            "Trading within 5% of its 52-week high with a bullish signal -- "
            "momentum favors the bulls, but chasing new highs carries elevated "
            "pullback risk. Scaling in or waiting for a dip is often preferable "
            "to a lump-sum entry here."
        )
    if near_low and bullish:
        return (
            "Trading near its 52-week low while the composite signal stays "
            "bullish -- this divergence can mark a potential value entry, but "
            "confirm the drawdown isn't being driven by a deteriorating "
            "fundamental story before buying."
        )
    if near_high and bearish:
        return (
            "Trading near its 52-week high even as signals weaken -- elevated "
            "downside risk; this is not a favorable spot to be initiating a "
            "new long position."
        )
    if near_low and bearish:
        return (
            "Trading near its 52-week low with a bearish signal -- the "
            "market/analysts may be pricing in a further leg down. Wait for "
            "signal confirmation before treating this as a bottom."
        )
    return (
        "No strong timing edge detected from price position alone -- "
        "dollar-cost averaging is generally preferable to a lump-sum entry "
        "when there's no clear extreme in either direction."
    )


def compute_signal(
    ticker: str,
    price: PriceSnapshot | None,
    analyst: AnalystView | None,
    insider: InsiderActivity | None,
) -> StockSignal:
    components = {
        "Analyst sentiment": _analyst_component(analyst),
        "Price momentum": _momentum_component(price),
        "Trend (50d vs 200d SMA)": _trend_component(price),
        "Insider activity": _insider_component(insider),
    }

    available = {k: v for k, v in components.items() if v is not None}
    rationale = []
    for name, value in components.items():
        if value is None:
            rationale.append(f"{name}: no data available")
        else:
            direction = "bullish" if value > 0.1 else ("bearish" if value < -0.1 else "neutral")
            rationale.append(f"{name}: {direction} ({value:+.2f})")

    if not available:
        return StockSignal(
            ticker=ticker,
            composite_score=None,
            verdict="Unrated",
            confidence="Low",
            rationale=rationale,
            timing_note="Insufficient data to generate a signal.",
        )

    composite_score = weighted_composite(components)
    verdict = verdict_for(composite_score)

    if len(available) >= 4:
        confidence = "High"
    elif len(available) >= 2:
        confidence = "Medium"
    else:
        confidence = "Low"

    return StockSignal(
        ticker=ticker,
        composite_score=composite_score,
        verdict=verdict,
        confidence=confidence,
        rationale=rationale,
        timing_note=_timing_note(price, verdict),
    )
