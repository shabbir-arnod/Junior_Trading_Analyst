import pytest

from analyst.alerts import AlertBook, evaluate_rule, new_alert_rule
from analyst.analysis.signal import StockSignal
from analyst.data_sources.base import PriceSnapshot


def test_new_alert_rule_requires_threshold_for_price_conditions():
    with pytest.raises(ValueError):
        new_alert_rule("NVDA", "price_above", threshold=None)
    rule = new_alert_rule("nvda", "price_above", threshold=150.0)
    assert rule.ticker == "NVDA"  # normalized to uppercase
    assert rule.id  # auto-generated


def test_new_alert_rule_rejects_unknown_condition():
    with pytest.raises(ValueError):
        new_alert_rule("NVDA", "moon_landing")


def test_evaluate_rule_price_above_triggers_correctly():
    rule = new_alert_rule("NVDA", "price_above", threshold=100.0)
    price = PriceSnapshot(ticker="NVDA", current_price=150.0)
    result = evaluate_rule(rule, price, None)
    assert result.triggered is True
    assert result.current_value == "$150.00"

    price_low = PriceSnapshot(ticker="NVDA", current_price=50.0)
    result = evaluate_rule(rule, price_low, None)
    assert result.triggered is False


def test_evaluate_rule_price_below_triggers_correctly():
    rule = new_alert_rule("NVDA", "price_below", threshold=100.0)
    result = evaluate_rule(rule, PriceSnapshot(ticker="NVDA", current_price=50.0), None)
    assert result.triggered is True


def test_evaluate_rule_signal_conditions():
    bullish_rule = new_alert_rule("NVDA", "signal_bullish")
    bearish_signal = StockSignal(ticker="NVDA", composite_score=-0.6, verdict="Strongly Bearish", confidence="High")
    result = evaluate_rule(bullish_rule, None, bearish_signal)
    assert result.triggered is False
    assert result.current_value == "Strongly Bearish"

    bullish_signal = StockSignal(ticker="NVDA", composite_score=0.6, verdict="Strongly Bullish", confidence="High")
    result = evaluate_rule(bullish_rule, None, bullish_signal)
    assert result.triggered is True


def test_evaluate_rule_missing_data_does_not_trigger():
    rule = new_alert_rule("NVDA", "price_above", threshold=100.0)
    result = evaluate_rule(rule, None, None)
    assert result.triggered is False
    assert result.current_value == "n/a"


def test_alert_book_roundtrip(tmp_path):
    path = tmp_path / "alerts.yaml"
    book = AlertBook.load(path)
    assert book.rules == []

    rule = new_alert_rule("NVDA", "price_above", threshold=150.0)
    book.add(rule)
    book.save()

    reloaded = AlertBook.load(path)
    assert len(reloaded.rules) == 1
    assert reloaded.rules[0].ticker == "NVDA"
    assert reloaded.rules[0].threshold == 150.0

    assert reloaded.remove(rule.id) is True
    reloaded.save()
    assert AlertBook.load(path).rules == []


def test_alert_book_remove_missing_id_returns_false(tmp_path):
    book = AlertBook.load(tmp_path / "alerts.yaml")
    assert book.remove("does-not-exist") is False
