"""Optional enrichment provider backed by NewsAPI.org (free-tier key).

Used for broad-web press-release / deal / macro-economic headline search
that goes beyond a single ticker's dedicated news feed.
"""

from __future__ import annotations

from datetime import datetime

import requests

from analyst.data_sources.base import NewsItem

BASE_URL = "https://newsapi.org/v2/everything"
TIMEOUT_SECONDS = 10


class NewsApiProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, limit: int = 10, language: str = "en") -> list[NewsItem]:
        params = {
            "q": query,
            "language": language,
            "sortBy": "publishedAt",
            "pageSize": limit,
            "apiKey": self._api_key,
        }
        try:
            resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return []

        items = []
        for raw in data.get("articles", [])[:limit]:
            published_at = None
            if raw.get("publishedAt"):
                try:
                    published_at = datetime.fromisoformat(raw["publishedAt"].replace("Z", "+00:00"))
                except ValueError:
                    published_at = None
            items.append(
                NewsItem(
                    title=raw.get("title", ""),
                    publisher=(raw.get("source") or {}).get("name"),
                    link=raw.get("url"),
                    published_at=published_at,
                    summary=raw.get("description"),
                )
            )
        return [item for item in items if item.title]
