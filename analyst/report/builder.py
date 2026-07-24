"""Assembles the final markdown report: a watchlist summary table plus a
detailed per-ticker section for every tracked stock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from analyst.analysis.signal import StockSignal, compute_signal
from analyst.analysis.synthesizer import generate_narrative
from analyst.config import Settings
from analyst.data_sources.aggregator import build_bundle, build_macro_snapshot
from analyst.data_sources.base import MacroSnapshot, StockBundle
from analyst.data_sources.market_data import MarketDataProvider

DISCLAIMER = (
    "**Disclaimer:** This report is generated from public market data and "
    "an automated heuristic/LLM analysis. It is for informational purposes "
    "only, is not financial advice, and may contain errors or missing "
    "data. Always do your own research and consult a licensed financial "
    "advisor before making investment decisions."
)


@dataclass
class TickerReport:
    bundle: StockBundle
    signal: StockSignal
    narrative: str | None = None


def _fmt_price(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "n/a"


def _fmt_pct(value: float | None) -> str:
    return f"{value:+.1f}%" if value is not None else "n/a"


def _fmt_date(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value is not None else "n/a"


def _fmt_large_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.2f}{suffix}"
    return f"${value:,.0f}"


def collect_ticker_report(
    ticker: str,
    settings: Settings,
    market: MarketDataProvider,
    macro: MacroSnapshot | None,
    include_llm: bool,
) -> TickerReport:
    bundle = build_bundle(ticker, settings, market=market)
    signal = compute_signal(ticker, bundle.price, bundle.analyst, bundle.insider)

    narrative = None
    if include_llm and settings.has_llm:
        try:
            narrative = generate_narrative(bundle, signal, macro, settings.gemini_api_key)
        except Exception as exc:
            narrative = f"_Narrative generation failed: {exc}_"

    return TickerReport(bundle=bundle, signal=signal, narrative=narrative)


def _summary_table(reports: list[TickerReport]) -> str:
    lines = [
        "| Ticker | Company | Price | 1D | Verdict | Score | Analyst Upside | 52w Position |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        price = r.bundle.price
        analyst = r.bundle.analyst
        score = f"{r.signal.composite_score:+.2f}" if r.signal.composite_score is not None else "n/a"

        pos = "n/a"
        if price and price.current_price and price.fifty_two_week_high and price.fifty_two_week_low:
            span = price.fifty_two_week_high - price.fifty_two_week_low
            if span > 0:
                pct = (price.current_price - price.fifty_two_week_low) / span * 100
                pos = f"{pct:.0f}% of 52w range"

        lines.append(
            "| {ticker} | {company} | {price} | {chg} | {verdict} | {score} | {upside} | {pos} |".format(
                ticker=r.bundle.ticker,
                company=(r.bundle.company_name or "n/a")[:30],
                price=_fmt_price(price.current_price if price else None),
                chg=_fmt_pct(price.day_change_pct if price else None),
                verdict=r.signal.verdict,
                score=score,
                upside=_fmt_pct(analyst.upside_pct if analyst else None),
                pos=pos,
            )
        )
    return "\n".join(lines)


def _ticker_section(r: TickerReport) -> str:
    bundle, signal = r.bundle, r.signal
    price, analyst, insider, financials = bundle.price, bundle.analyst, bundle.insider, bundle.financials

    parts = [f"## {bundle.ticker} -- {bundle.company_name or 'Unknown company'}"]
    if bundle.sector:
        parts.append(f"*Sector: {bundle.sector}*")

    parts.append(
        f"\n**Signal: {signal.verdict}**"
        + (f" (score {signal.composite_score:+.2f}, confidence: {signal.confidence})" if signal.composite_score is not None else "")
    )
    parts.append(f"\n{signal.timing_note}")
    parts.append("\nSignal components:\n" + "\n".join(f"- {line}" for line in signal.rationale))

    if price:
        parts.append(
            "\n### Price & Technicals\n"
            f"- Current: {_fmt_price(price.current_price)} ({_fmt_pct(price.day_change_pct)} today), as of {_fmt_date(price.as_of)}\n"
            f"- 52-week range: {_fmt_price(price.fifty_two_week_low)} - {_fmt_price(price.fifty_two_week_high)}\n"
            f"- All-time high (observed): {_fmt_price(price.all_time_high)} on {_fmt_date(price.all_time_high_date)}\n"
            f"- All-time low (observed): {_fmt_price(price.all_time_low)} on {_fmt_date(price.all_time_low_date)}\n"
            f"- 50d SMA: {_fmt_price(price.sma_50)} | 200d SMA: {_fmt_price(price.sma_200)}\n"
            f"- Momentum: 1M {_fmt_pct(price.momentum_1m_pct)} | 3M {_fmt_pct(price.momentum_3m_pct)} | "
            f"6M {_fmt_pct(price.momentum_6m_pct)} | 1Y {_fmt_pct(price.momentum_1y_pct)}\n"
            f"- Market cap: {_fmt_large_number(price.market_cap)}"
        )

    if analyst:
        parts.append(
            "\n### Analyst Ratings\n"
            f"- Consensus: {analyst.recommendation_key or 'n/a'} "
            f"(mean {analyst.recommendation_mean if analyst.recommendation_mean is not None else 'n/a'}, "
            f"{analyst.num_analysts or 'n/a'} analysts)\n"
            f"- Price target: mean {_fmt_price(analyst.target_mean)}, "
            f"range {_fmt_price(analyst.target_low)}-{_fmt_price(analyst.target_high)} "
            f"({_fmt_pct(analyst.upside_pct)} implied upside)"
        )

    if financials:
        parts.append(
            "\n### Financials\n"
            f"- Revenue (TTM): {_fmt_large_number(financials.revenue_ttm)} "
            f"(YoY growth {_fmt_pct(financials.revenue_growth_yoy_pct)})\n"
            f"- Margins: gross {_fmt_pct(financials.gross_margin_pct)}, "
            f"operating {_fmt_pct(financials.operating_margin_pct)}, "
            f"net {_fmt_pct(financials.net_margin_pct)}\n"
            f"- EPS (TTM): {financials.eps_ttm if financials.eps_ttm is not None else 'n/a'} | "
            f"P/E: {financials.pe_ratio if financials.pe_ratio is not None else 'n/a'} "
            f"(fwd {financials.forward_pe if financials.forward_pe is not None else 'n/a'})\n"
            f"- Free cash flow: {_fmt_large_number(financials.free_cash_flow)}"
        )

    if insider and insider.transactions:
        net_shares_line = (
            f"- Net shares: {insider.net_shares:+,.0f}" if insider.net_shares is not None else "- Net shares: n/a"
        )
        parts.append(
            f"\n### Insider Activity (last {insider.window_days} days)\n"
            f"- {insider.buy_count} buy transaction(s), {insider.sell_count} sell transaction(s)\n"
            f"{net_shares_line}"
        )
    else:
        parts.append("\n### Insider Activity\n- No recent insider transactions found.")

    if bundle.news:
        news_lines = []
        for item in bundle.news[:8]:
            date_str = _fmt_date(item.published_at)
            source = f" ({item.publisher})" if item.publisher else ""
            link = f" - {item.link}" if item.link else ""
            news_lines.append(f"- [{date_str}] {item.title}{source}{link}")
        parts.append("\n### Recent News\n" + "\n".join(news_lines))
    else:
        parts.append("\n### Recent News\n- No recent news found.")

    if r.narrative:
        parts.append(f"\n### Analyst Note (AI-synthesized)\n{r.narrative}")

    if bundle.errors:
        parts.append("\n### Data Gaps\n" + "\n".join(f"- {e}" for e in bundle.errors))

    return "\n".join(parts)


def build_report(
    tickers: list[str],
    settings: Settings,
    include_llm: bool = True,
    market: MarketDataProvider | None = None,
) -> str:
    market = market or MarketDataProvider()
    macro = build_macro_snapshot(settings)

    reports = [
        collect_ticker_report(ticker, settings, market, macro, include_llm) for ticker in tickers
    ]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        "# AI Infrastructure Stock Analyst Report",
        f"_Generated {generated_at}_",
        "",
        DISCLAIMER,
        "",
        "## Watchlist Summary",
        _summary_table(reports),
    ]

    if macro.notes or macro.headlines:
        macro_lines = ["", "## Macro / Sector Backdrop"]
        macro_lines.extend(f"- {note}" for note in macro.notes)
        for item in macro.headlines[:8]:
            date_str = _fmt_date(item.published_at)
            source = f" ({item.publisher})" if item.publisher else ""
            macro_lines.append(f"- [{date_str}] {item.title}{source}")
        sections.extend(macro_lines)

    sections.append("")
    for r in reports:
        sections.append(_ticker_section(r))
        sections.append("")

    sections.append(DISCLAIMER)
    return "\n".join(sections)
