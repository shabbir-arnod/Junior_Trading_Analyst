"""Environment/config loading. All keys are optional except where noted."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WATCHLIST_PATH = REPO_ROOT / "config" / "watchlist.yaml"
DEFAULT_ALERTS_PATH = REPO_ROOT / "config" / "alerts.yaml"


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    finnhub_api_key: str | None
    newsapi_key: str | None
    fred_api_key: str | None
    watchlist_path: Path
    alerts_path: Path = DEFAULT_ALERTS_PATH
    alert_webhook_url: str | None = None

    @property
    def has_llm(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_finnhub(self) -> bool:
        return bool(self.finnhub_api_key)

    @property
    def has_newsapi(self) -> bool:
        return bool(self.newsapi_key)

    @property
    def has_fred(self) -> bool:
        return bool(self.fred_api_key)

    @property
    def has_alert_webhook(self) -> bool:
        return bool(self.alert_webhook_url)


def load_settings(watchlist_path: Path | None = None, alerts_path: Path | None = None) -> Settings:
    _load_dotenv()
    return Settings(
        gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        finnhub_api_key=os.environ.get("FINNHUB_API_KEY") or None,
        newsapi_key=os.environ.get("NEWSAPI_KEY") or None,
        fred_api_key=os.environ.get("FRED_API_KEY") or None,
        watchlist_path=watchlist_path or DEFAULT_WATCHLIST_PATH,
        alerts_path=alerts_path or DEFAULT_ALERTS_PATH,
        alert_webhook_url=os.environ.get("ALERT_WEBHOOK_URL") or None,
    )
