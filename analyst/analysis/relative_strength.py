"""How a stock's momentum compares to its peer group (the rest of the
watchlist) and to a broad market benchmark (S&P 500) -- is this name
actually outperforming, or just riding a rising tide? Pure excess-return
arithmetic on already-fetched PriceSnapshot data; no new data source.
"""

from __future__ import annotations

from dataclasses import dataclass

from analyst.data_sources.base import PriceSnapshot


@dataclass
class RelativeStrength:
    ticker: str
    momentum_3m_pct: float
    peer_avg_momentum_3m_pct: float | None
    benchmark_momentum_3m_pct: float | None
    vs_peers_pp: float | None  # percentage-point spread vs. peer average
    vs_benchmark_pp: float | None  # percentage-point spread vs. benchmark


def compute_relative_strength(
    price: PriceSnapshot | None,
    peer_prices: list[PriceSnapshot],
    benchmark_price: PriceSnapshot | None,
) -> RelativeStrength | None:
    if price is None or price.momentum_3m_pct is None:
        return None

    peer_momentums = [
        p.momentum_3m_pct for p in peer_prices
        if p is not None and p.momentum_3m_pct is not None and p.ticker != price.ticker
    ]
    peer_avg = sum(peer_momentums) / len(peer_momentums) if peer_momentums else None
    benchmark_momentum = benchmark_price.momentum_3m_pct if benchmark_price else None

    return RelativeStrength(
        ticker=price.ticker,
        momentum_3m_pct=price.momentum_3m_pct,
        peer_avg_momentum_3m_pct=peer_avg,
        benchmark_momentum_3m_pct=benchmark_momentum,
        vs_peers_pp=(price.momentum_3m_pct - peer_avg) if peer_avg is not None else None,
        vs_benchmark_pp=(
            (price.momentum_3m_pct - benchmark_momentum) if benchmark_momentum is not None else None
        ),
    )
