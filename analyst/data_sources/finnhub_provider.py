"""Optional enrichment provider backed by Finnhub (free-tier API key).

Adds: broader company news, insider transactions, and analyst
recommendation trend history. All methods degrade to empty results on any
HTTP/parsing failure so a bad key or rate limit never breaks a report.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from analyst.data_sources.base import InsiderActivity, InsiderTransaction, NewsItem

BASE_URL = "https://finnhub.io/api/v1"
TIMEOUT_SECONDS = 10


class FinnhubProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def _get(self, path: str, params: dict) -> list | dict:
        params = {**params, "token": self._api_key}
        try:
            resp = requests.get(f"{BASE_URL}/{path}", params=params, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError):
            return []

    def get_company_news(self, symbol: str, days_back: int = 14, limit: int = 15) -> list[NewsItem]:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days_back)
        data = self._get(
            "company-news",
            {"symbol": symbol, "from": start.isoformat(), "to": today.isoformat()},
        )
        if not isinstance(data, list):
            return []
        items = []
        for raw in data[:limit]:
            ts = raw.get("datetime")
            published_at = (
                datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else None
            )
            items.append(
                NewsItem(
                    title=raw.get("headline", ""),
                    publisher=raw.get("source"),
                    link=raw.get("url"),
                    published_at=published_at,
                    summary=raw.get("summary"),
                )
            )
        return [item for item in items if item.title]

    def get_insider_activity(self, symbol: str, window_days: int = 180) -> InsiderActivity:
        activity = InsiderActivity(ticker=symbol, window_days=window_days)
        data = self._get("stock/insider-transactions", {"symbol": symbol})
        rows = data.get("data", []) if isinstance(data, dict) else []
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        for row in rows:
            date_str = row.get("transactionDate")
            try:
                tx_date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc) if date_str else None
            except ValueError:
                tx_date = None
            if tx_date is not None and tx_date < cutoff:
                continue
            change = row.get("change") or 0
            ttype = "buy" if change > 0 else ("sell" if change < 0 else "other")
            share_price = row.get("transactionPrice") or 0
            value = abs(change) * share_price if share_price else None
            activity.transactions.append(
                InsiderTransaction(
                    insider=row.get("name", "Unknown"),
                    relation=None,
                    transaction_type=ttype,
                    shares=abs(change) if change else None,
                    value=value,
                    date=tx_date,
                )
            )
        activity.buy_count = sum(1 for t in activity.transactions if t.transaction_type == "buy")
        activity.sell_count = sum(1 for t in activity.transactions if t.transaction_type == "sell")
        net_shares = sum(
            (t.shares or 0) * (1 if t.transaction_type == "buy" else -1)
            for t in activity.transactions
            if t.transaction_type in ("buy", "sell")
        )
        net_value = sum(
            (t.value or 0) * (1 if t.transaction_type == "buy" else -1)
            for t in activity.transactions
            if t.transaction_type in ("buy", "sell") and t.value is not None
        )
        activity.net_shares = net_shares if activity.transactions else None
        activity.net_value = net_value if activity.transactions else None
        return activity

    def get_recommendation_trend(self, symbol: str) -> dict | None:
        data = self._get("stock/recommendation", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return None
