"""Price/signal alert rules: persistence, evaluation, and webhook notify.

Designed to run two ways:
1. Inside the Streamlit app, reusing already-fetched (cached) price/signal
   data -- evaluate_rule() is the pure, no-network piece for this.
2. As a standalone scheduled job (see analyst.cli's `alerts-check` command
   and .github/workflows/alerts.yml) that fetches fresh data itself via
   evaluate_alerts() and posts to a webhook -- this is what lets alerts
   fire even when nobody has the app open, which a Streamlit Cloud app
   alone cannot do (it only runs code while a page is being viewed).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from analyst.analysis.signal import StockSignal
from analyst.config import Settings
from analyst.data_sources.base import PriceSnapshot

VALID_CONDITIONS = ("price_above", "price_below", "signal_bullish", "signal_bearish")
BULLISH_VERDICTS = ("Bullish", "Strongly Bullish")
BEARISH_VERDICTS = ("Bearish", "Strongly Bearish")


@dataclass
class AlertRule:
    id: str
    ticker: str
    condition: str  # one of VALID_CONDITIONS
    threshold: float | None = None  # required for price_above / price_below

    def describe(self) -> str:
        if self.condition == "price_above":
            return f"{self.ticker} price rises above ${self.threshold:,.2f}"
        if self.condition == "price_below":
            return f"{self.ticker} price falls below ${self.threshold:,.2f}"
        if self.condition == "signal_bullish":
            return f"{self.ticker} signal turns Bullish"
        if self.condition == "signal_bearish":
            return f"{self.ticker} signal turns Bearish"
        return f"{self.ticker}: {self.condition}"


def new_alert_rule(ticker: str, condition: str, threshold: float | None = None) -> AlertRule:
    if condition not in VALID_CONDITIONS:
        raise ValueError(f"Unknown condition '{condition}', expected one of {VALID_CONDITIONS}")
    if condition in ("price_above", "price_below") and threshold is None:
        raise ValueError(f"'{condition}' requires a threshold")
    return AlertRule(id=uuid.uuid4().hex[:8], ticker=ticker.upper(), condition=condition, threshold=threshold)


@dataclass
class AlertBook:
    path: Path
    rules: list[AlertRule] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "AlertBook":
        if not path.exists():
            return cls(path=path, rules=[])
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        rules = [AlertRule(**r) for r in (raw.get("alerts") or [])]
        return cls(path=path, rules=rules)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"alerts": [asdict(r) for r in self.rules]}
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def add(self, rule: AlertRule) -> None:
        self.rules.append(rule)

    def remove(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < before


@dataclass
class AlertResult:
    rule: AlertRule
    triggered: bool
    current_value: str
    error: str | None = None


def evaluate_rule(rule: AlertRule, price: PriceSnapshot | None, signal: StockSignal | None) -> AlertResult:
    """Pure evaluation against already-fetched data -- no network calls.
    Used both by the Streamlit app (with its own cached data) and by
    evaluate_alerts() below (after it fetches fresh data itself)."""
    try:
        if rule.condition == "price_above":
            current = price.current_price if price else None
            triggered = current is not None and rule.threshold is not None and current > rule.threshold
            return AlertResult(rule, triggered, f"${current:,.2f}" if current is not None else "n/a")
        if rule.condition == "price_below":
            current = price.current_price if price else None
            triggered = current is not None and rule.threshold is not None and current < rule.threshold
            return AlertResult(rule, triggered, f"${current:,.2f}" if current is not None else "n/a")
        if rule.condition == "signal_bullish":
            verdict = signal.verdict if signal else "Unrated"
            return AlertResult(rule, verdict in BULLISH_VERDICTS, verdict)
        if rule.condition == "signal_bearish":
            verdict = signal.verdict if signal else "Unrated"
            return AlertResult(rule, verdict in BEARISH_VERDICTS, verdict)
        return AlertResult(rule, False, "n/a", error=f"Unknown condition '{rule.condition}'")
    except Exception as exc:
        return AlertResult(rule, False, "error", error=str(exc))


def evaluate_alerts(rules: list[AlertRule], settings: Settings, market=None) -> list[AlertResult]:
    """Fetches fresh data itself -- for the standalone CLI/cron path where
    there's no Streamlit cache to reuse."""
    from analyst.analysis.signal import compute_signal
    from analyst.data_sources.aggregator import build_bundle
    from analyst.data_sources.market_data import MarketDataProvider

    market = market or MarketDataProvider()
    cache: dict[str, tuple] = {}
    results = []

    for rule in rules:
        if rule.ticker not in cache:
            try:
                bundle = build_bundle(rule.ticker, settings, market=market)
                signal = compute_signal(rule.ticker, bundle.price, bundle.analyst, bundle.insider)
                cache[rule.ticker] = (bundle.price, signal)
            except Exception as exc:
                results.append(AlertResult(rule, False, "error", error=str(exc)))
                continue
        price, signal = cache[rule.ticker]
        results.append(evaluate_rule(rule, price, signal))

    return results


def notify_webhook(webhook_url: str, triggered: list[AlertResult]) -> bool:
    """POSTs a plain-text summary. Sends both `text` (Slack-compatible) and
    `content` (Discord-compatible) keys in one payload since most webhook
    receivers ignore unknown keys -- covers both without asking the user
    which service they're using."""
    import requests

    if not triggered:
        return True
    lines = [f"- {r.rule.describe()} -- now {r.current_value}" for r in triggered]
    message = "🔔 Junior Trading Analyst: alert(s) triggered\n" + "\n".join(lines)
    try:
        resp = requests.post(webhook_url, json={"text": message, "content": message}, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        return False
