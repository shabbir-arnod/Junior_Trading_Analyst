from analyst.analysis.relative_strength import compute_relative_strength
from analyst.data_sources.base import PriceSnapshot


def _price(ticker: str, momentum_3m: float | None) -> PriceSnapshot:
    return PriceSnapshot(ticker=ticker, momentum_3m_pct=momentum_3m)


def test_outperformer_shows_positive_spreads():
    price = _price("NVDA", 20.0)
    peers = [_price("AMD", 10.0), _price("AVGO", 5.0), _price("NVDA", 20.0)]  # self excluded
    benchmark = _price("^GSPC", 8.0)

    rs = compute_relative_strength(price, peers, benchmark)
    assert rs.peer_avg_momentum_3m_pct == 7.5  # avg of AMD/AVGO only, NVDA excluded
    assert rs.vs_peers_pp == 12.5
    assert rs.vs_benchmark_pp == 12.0


def test_underperformer_shows_negative_spreads():
    price = _price("XYZ", -5.0)
    peers = [_price("A", 10.0), _price("B", 10.0)]
    benchmark = _price("^GSPC", 8.0)

    rs = compute_relative_strength(price, peers, benchmark)
    assert rs.vs_peers_pp == -15.0
    assert rs.vs_benchmark_pp == -13.0


def test_missing_price_returns_none():
    assert compute_relative_strength(None, [], None) is None
    assert compute_relative_strength(PriceSnapshot(ticker="X", momentum_3m_pct=None), [], None) is None


def test_no_peer_data_gives_none_spread_not_crash():
    price = _price("SOLO", 5.0)
    rs = compute_relative_strength(price, [], None)
    assert rs.peer_avg_momentum_3m_pct is None
    assert rs.vs_peers_pp is None
    assert rs.vs_benchmark_pp is None
