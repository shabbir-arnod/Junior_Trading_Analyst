"""Optional macroeconomic data provider backed by FRED (free API key).

Surfaces the handful of macro series that most directly move AI
infrastructure capex and valuations: the fed funds rate, CPI inflation,
and 10-year Treasury yield.
"""

from __future__ import annotations

import requests

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT_SECONDS = 10

SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "cpi_inflation": "CPIAUCSL",
    "treasury_10y_yield": "DGS10",
}


class FredProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _latest_observation(self, series_id: str) -> float | None:
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }
        try:
            resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            obs = data.get("observations", [])
            if not obs:
                return None
            value = obs[0].get("value")
            return float(value) if value not in (None, ".") else None
        except (requests.RequestException, ValueError, TypeError):
            return None

    def get_macro_indicators(self) -> dict[str, float | None]:
        return {name: self._latest_observation(series_id) for name, series_id in SERIES.items()}
