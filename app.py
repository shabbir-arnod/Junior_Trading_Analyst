"""Junior Trading Analyst - web dashboard.

Run with:  streamlit run app.py
Then open the browser tab it launches (usually http://localhost:8501).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from html import escape as html_escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analyst.alerts import AlertBook, AlertResult, VALID_CONDITIONS, evaluate_rule, new_alert_rule
from analyst.analysis.backtest import BacktestResult, backtest_price_signal
from analyst.analysis.relative_strength import RelativeStrength, compute_relative_strength
from analyst.analysis.signal import StockSignal, compute_signal
from analyst.analysis.synthesizer import generate_narrative
from analyst.config import load_settings
from analyst.data_sources.aggregator import build_bundle, build_macro_snapshot, get_industry_headlines
from analyst.data_sources.base import EarningsOutlook, OptionsSnapshot, PriceSnapshot, StockBundle
from analyst.data_sources.market_data import MarketDataProvider
from analyst.report.builder import DISCLAIMER
from analyst.universe import Watchlist

st.set_page_config(page_title="Junior Trading Analyst", page_icon="📈", layout="wide")

# Dark-surface palette (validated status/ink tokens; see dataviz skill reference).
PAGE_BG = "#0d0d0d"
SURFACE = "#1a1a19"
SURFACE_RAISED = "#232322"
INK_PRIMARY = "#ffffff"
INK_SECONDARY = "#c3c2b7"
INK_MUTED = "#898781"
GRID_HAIRLINE = "#2c2c2a"
BORDER_HAIRLINE = "rgba(255,255,255,0.10)"

COLOR_UP = "#0ca30c"       # status: good  -- price/score up, bullish
COLOR_DOWN = "#d03b3b"     # status: critical -- price/score down, bearish
COLOR_NEUTRAL = "#898781"  # muted -- flat / no signal
COLOR_SMA50 = "#3987e5"    # categorical slot 1 (dark step) -- 50-day average
COLOR_SMA200 = "#c98500"   # categorical slot 3 (dark step) -- 200-day average

VERDICT_TONE = {
    "Strongly Bullish": ("up", "🟢"),
    "Bullish": ("up", "🟢"),
    "Neutral": ("neutral", "⚪"),
    "Bearish": ("down", "🔴"),
    "Strongly Bearish": ("down", "🔴"),
    "Unrated": ("neutral", "⚫"),
}
VERDICT_BADGES = {k: f"{icon} {k}" for k, (_, icon) in VERDICT_TONE.items()}

TIMEFRAMES = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252, "All": None}

# Yahoo Finance tickers for the Markets section (commodities futures + index
# tickers) -- these aren't stocks, so they skip the analyst/insider/financials
# fields entirely and just show price + trend.
COMMODITIES = {"GC=F": "Gold (Futures)", "SI=F": "Silver (Futures)"}
INDICES = {
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
    "^DJI": "Dow Jones Industrial Average",
    "^RUT": "Russell 2000",
}

CACHE_TTL_SECONDS = 15 * 60
NEWS_TTL_SECONDS = 7 * 24 * 60 * 60  # AI News tab refreshes on a weekly cadence
DEMO_MODE = os.environ.get("JTA_DEMO", "").strip() in ("1", "true", "yes")

APP_CSS = f"""
<style>
.stApp {{ background: {PAGE_BG}; }}
[data-testid="stSidebar"] {{ background: {SURFACE}; border-right: 1px solid {BORDER_HAIRLINE}; }}
[data-testid="stMetric"] {{
    background: {SURFACE}; border: 1px solid {BORDER_HAIRLINE}; border-radius: 14px;
    padding: 14px 16px;
}}
div[data-testid="stExpander"] {{
    background: {SURFACE}; border: 1px solid {BORDER_HAIRLINE}; border-radius: 16px;
    overflow: hidden;
}}
.stButton > button, .stFormSubmitButton > button {{
    border-radius: 999px; font-weight: 600;
}}
div[data-testid="stDataFrame"] {{ border-radius: 12px; overflow: hidden; }}

.jta-hero {{
    background: {SURFACE}; border: 1px solid {BORDER_HAIRLINE}; border-radius: 20px;
    padding: 20px 24px; margin-bottom: 14px;
}}
.jta-hero-top {{ display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px; }}
.jta-hero-ticker {{ font-size: 1.05rem; font-weight: 700; color: {INK_PRIMARY}; letter-spacing: 0.02em; }}
.jta-hero-company {{ font-size: 0.9rem; color: {INK_MUTED}; }}
.jta-hero-price {{ font-size: 2.6rem; font-weight: 700; color: {INK_PRIMARY}; line-height: 1.1; }}
.jta-hero-delta {{ display: inline-flex; align-items: center; gap: 4px; margin-top: 6px;
    font-size: 1rem; font-weight: 600; padding: 3px 10px; border-radius: 999px; }}
.jta-hero-delta.up {{ color: {COLOR_UP}; background: rgba(12,163,12,0.14); }}
.jta-hero-delta.down {{ color: {COLOR_DOWN}; background: rgba(208,59,59,0.14); }}
.jta-hero-delta.neutral {{ color: {COLOR_NEUTRAL}; background: rgba(137,135,129,0.14); }}

.jta-chip-row {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }}
.jta-chip {{
    background: {SURFACE_RAISED}; border-left: 3px solid {COLOR_NEUTRAL}; border-radius: 10px;
    padding: 8px 14px; min-width: 120px;
}}
.jta-chip.up {{ border-left-color: {COLOR_UP}; }}
.jta-chip.down {{ border-left-color: {COLOR_DOWN}; }}
.jta-chip-label {{ font-size: 0.72rem; color: {INK_MUTED}; text-transform: uppercase; letter-spacing: 0.04em; }}
.jta-chip-value {{ font-size: 1.05rem; font-weight: 600; color: {INK_PRIMARY}; }}

.jta-row {{
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    background: {SURFACE}; border: 1px solid {BORDER_HAIRLINE}; border-radius: 14px;
    padding: 12px 18px; margin-bottom: 8px;
}}
.jta-row-left {{ display: flex; flex-direction: column; min-width: 90px; }}
.jta-row-ticker {{ font-weight: 700; color: {INK_PRIMARY}; font-size: 1rem; }}
.jta-row-name {{ font-size: 0.78rem; color: {INK_MUTED}; }}
.jta-row-signal {{ font-size: 0.9rem; color: {INK_SECONDARY}; flex: 1; text-align: center; }}
.jta-row-right {{ display: flex; flex-direction: column; align-items: flex-end; min-width: 100px; }}
.jta-row-price {{ font-weight: 700; color: {INK_PRIMARY}; font-size: 1rem; }}
.jta-row-delta {{ font-size: 0.85rem; font-weight: 600; }}
.jta-row-delta.up {{ color: {COLOR_UP}; }}
.jta-row-delta.down {{ color: {COLOR_DOWN}; }}
.jta-row-delta.neutral {{ color: {COLOR_NEUTRAL}; }}

.jta-news-row {{
    background: {SURFACE}; border: 1px solid {BORDER_HAIRLINE}; border-radius: 14px;
    padding: 12px 18px; margin-bottom: 8px;
}}
.jta-news-title a {{ color: {INK_PRIMARY}; font-weight: 600; text-decoration: none; }}
.jta-news-title a:hover {{ text-decoration: underline; }}
.jta-news-meta {{ display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 0.8rem; color: {INK_MUTED}; }}
.jta-news-tag {{
    background: {SURFACE_RAISED}; color: {INK_SECONDARY}; border-radius: 999px;
    padding: 1px 10px; font-weight: 600; font-size: 0.72rem; letter-spacing: 0.02em;
}}

.jta-bt-row {{
    display: grid; grid-template-columns: 1.4fr 0.8fr 1fr 0.8fr; gap: 8px; align-items: center;
    padding: 8px 12px; border-radius: 8px; margin-bottom: 4px; background: {SURFACE_RAISED};
}}
.jta-bt-row.header {{ background: transparent; color: {INK_MUTED}; font-size: 0.75rem;
    text-transform: uppercase; letter-spacing: 0.03em; }}
.jta-bt-verdict {{ font-weight: 600; color: {INK_PRIMARY}; }}
.jta-bt-value.up {{ color: {COLOR_UP}; font-weight: 600; }}
.jta-bt-value.down {{ color: {COLOR_DOWN}; font-weight: 600; }}
.jta-bt-value.neutral {{ color: {INK_SECONDARY}; }}

.jta-alert-row {{
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    background: {SURFACE}; border: 1px solid {BORDER_HAIRLINE}; border-radius: 12px;
    padding: 10px 16px; margin-bottom: 8px;
}}
.jta-alert-row.triggered {{ border-color: {COLOR_DOWN}; background: rgba(208,59,59,0.10); }}
.jta-alert-status {{ font-weight: 700; font-size: 0.85rem; }}
.jta-alert-status.triggered {{ color: {COLOR_DOWN}; }}
.jta-alert-status.ok {{ color: {COLOR_UP}; }}
</style>
"""


def inject_css() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def tone_of(value: float | None, epsilon: float = 0.0) -> str:
    if value is None:
        return "neutral"
    if value > epsilon:
        return "up"
    if value < -epsilon:
        return "down"
    return "neutral"


def arrow(tone: str) -> str:
    return {"up": "▲", "down": "▼", "neutral": "•"}[tone]


def safe_href(url: str | None) -> str | None:
    """Only allow http(s) links into raw HTML -- blocks javascript: URIs
    and similar from externally-sourced news links."""
    if url and url.strip().lower().startswith(("http://", "https://")):
        return url
    return None


def _apply_streamlit_secrets() -> None:
    """Copy top-level string secrets (Streamlit Cloud's Secrets box) into
    environment variables so analyst.config.load_settings() sees them."""
    try:
        for key, value in st.secrets.items():
            if isinstance(value, str) and key not in os.environ:
                os.environ[key] = value
    except FileNotFoundError:
        pass  # no secrets.toml configured -- normal for local runs


def _make_provider():
    if DEMO_MODE:
        from analyst.data_sources.demo_data import DemoMarketDataProvider

        return DemoMarketDataProvider()
    return MarketDataProvider()


def fmt_price(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "n/a"


def fmt_pct(value: float | None) -> str:
    return f"{value:+.1f}%" if value is not None else "n/a"


def fmt_relative(dt: datetime | None) -> str:
    if dt is None:
        return "Date unknown"
    days = (datetime.now(timezone.utc) - dt).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"{days} days ago"
    return dt.strftime("%b %d, %Y")


def display_name_for(ticker: str, fallback: str | None) -> str:
    """Commodities/indices get a fixed friendly name (Yahoo's own metadata
    for futures contracts is inconsistent/ugly, e.g. rolling contract
    months); stocks fall back to whatever yfinance returned."""
    return COMMODITIES.get(ticker) or INDICES.get(ticker) or fallback or ""


def fmt_big(value: float | None) -> str:
    if value is None:
        return "n/a"
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= threshold:
            return f"${value / threshold:,.2f}{suffix}"
    return f"${value:,.0f}"


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_ticker_data(ticker: str) -> tuple[StockBundle, StockSignal, pd.DataFrame | None]:
    settings = load_settings()
    market = _make_provider()
    bundle = build_bundle(ticker, settings, market=market)
    signal = compute_signal(ticker, bundle.price, bundle.analyst, bundle.insider)
    try:
        history = market.get_price_history(ticker, period="2y")
    except Exception:
        history = None
    return bundle, signal, history


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_options_snapshot(ticker: str) -> OptionsSnapshot | None:
    """None (not an error banner) if the ticker simply has no listed
    options -- true for most commodities/index tickers and plenty of
    smaller stocks."""
    try:
        return _make_provider().get_options_snapshot(ticker)
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_earnings_outlook(ticker: str) -> EarningsOutlook | None:
    try:
        return _make_provider().get_earnings_outlook(ticker)
    except Exception:
        return None


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_market_snapshot(tickers: tuple[str, ...]) -> dict[str, dict]:
    """Price + day change for non-stock instruments (commodities, indices).

    Computed straight from the close-price series rather than yfinance's
    .info dict, which is unreliable for futures/index tickers.
    """
    market = _make_provider()
    out: dict[str, dict] = {}
    for ticker in tickers:
        try:
            history = market.get_price_history(ticker, period="1y")
            closes = history["Close"].dropna()
            price = float(closes.iloc[-1]) if len(closes) >= 1 else None
            change_pct = (
                (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
                if len(closes) >= 2 and closes.iloc[-2] else None
            )
            out[ticker] = {"price": price, "change_pct": change_pct, "history": history}
        except Exception:
            out[ticker] = {"price": None, "change_pct": None, "history": None}
    return out


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_macro_notes() -> tuple[list[str], list[str]]:
    settings = load_settings()
    macro = build_macro_snapshot(settings)
    headlines = [
        f"{item.title}" + (f" ({item.publisher})" if item.publisher else "")
        for item in macro.headlines[:8]
    ]
    return macro.notes, headlines


@st.cache_data(ttl=NEWS_TTL_SECONDS, show_spinner=False)
def fetch_weekly_ai_news(tickers: tuple[str, ...]) -> tuple[list[dict], datetime]:
    """AI-industry news across the whole watchlist plus broad industry
    headlines. Cached for a week so the tab refreshes on that cadence;
    the UI also offers a manual "Refresh now" button that clears this
    cache early.
    """
    settings = load_settings()
    market = _make_provider()
    seen_titles: set[str] = set()
    items: list[dict] = []

    for ticker in tickers:
        try:
            for n in market.get_news(ticker, limit=6):
                if n.title not in seen_titles:
                    seen_titles.add(n.title)
                    items.append({
                        "title": n.title, "publisher": n.publisher, "link": n.link,
                        "published_at": n.published_at, "tag": ticker,
                    })
        except Exception:
            continue

    for n in get_industry_headlines(settings, limit=25):
        if n.title not in seen_titles:
            seen_titles.add(n.title)
            items.append({
                "title": n.title, "publisher": n.publisher, "link": n.link,
                "published_at": n.published_at, "tag": "AI Industry",
            })

    items.sort(key=lambda d: d["published_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items, datetime.now(timezone.utc)


def price_chart(history: pd.DataFrame, lookback_days: int | None, show_ma: bool) -> go.Figure:
    closes_full = history["Close"].dropna()
    sma50 = closes_full.rolling(50).mean()
    sma200 = closes_full.rolling(200).mean()

    closes = closes_full if lookback_days is None else closes_full.tail(lookback_days)
    trend = tone_of(closes.iloc[-1] - closes.iloc[0]) if len(closes) >= 2 else "neutral"
    line_color = {"up": COLOR_UP, "down": COLOR_DOWN, "neutral": COLOR_NEUTRAL}[trend]
    fill_color = {"up": "rgba(12,163,12,0.12)", "down": "rgba(208,59,59,0.12)",
                  "neutral": "rgba(137,135,129,0.10)"}[trend]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=closes.index, y=closes, name="Close", fill="tozeroy",
        fillcolor=fill_color, line=dict(color=line_color, width=2.5),
        hovertemplate="%{y:$,.2f}<extra>Close</extra>",
    ))
    if show_ma:
        fig.add_trace(go.Scatter(
            x=sma50.reindex(closes.index).index, y=sma50.reindex(closes.index), name="50-day avg",
            line=dict(color=COLOR_SMA50, width=1.5), hovertemplate="%{y:$,.2f}<extra>50-day avg</extra>",
        ))
        fig.add_trace(go.Scatter(
            x=sma200.reindex(closes.index).index, y=sma200.reindex(closes.index), name="200-day avg",
            line=dict(color=COLOR_SMA200, width=1.5), hovertemplate="%{y:$,.2f}<extra>200-day avg</extra>",
        ))

    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=10, b=10),
        hovermode="x unified",
        showlegend=show_ma,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    font=dict(color=INK_SECONDARY), bgcolor="rgba(0,0,0,0)"),
        yaxis=dict(title=None, gridcolor=GRID_HAIRLINE, tickprefix="$",
                   tickfont=dict(color=INK_MUTED), zeroline=False, range=[closes.min() * 0.97, closes.max() * 1.03]),
        xaxis=dict(title=None, showgrid=False, tickfont=dict(color=INK_MUTED)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK_PRIMARY),
    )
    return fig


def render_ticker_details(
    bundle: StockBundle,
    signal: StockSignal,
    history: pd.DataFrame | None,
    peer_prices: list[PriceSnapshot] | None = None,
    benchmark_price: PriceSnapshot | None = None,
):
    price, analyst, insider, fin = bundle.price, bundle.analyst, bundle.insider, bundle.financials
    display_name = display_name_for(bundle.ticker, bundle.company_name)

    rel_strength = compute_relative_strength(price, peer_prices or [], benchmark_price)
    options_snap = fetch_options_snapshot(bundle.ticker)
    earnings = fetch_earnings_outlook(bundle.ticker)

    day_tone = tone_of(price.day_change_pct if price else None)
    st.markdown(
        f"""
        <div class="jta-hero">
          <div class="jta-hero-top">
            <span class="jta-hero-ticker">{html_escape(bundle.ticker)}</span>
            <span class="jta-hero-company">{html_escape(display_name)}</span>
          </div>
          <div class="jta-hero-price">{fmt_price(price.current_price if price else None)}</div>
          <div class="jta-hero-delta {day_tone}">{arrow(day_tone)} {fmt_pct(price.day_change_pct if price else None)} today</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    signal_tone, signal_icon = VERDICT_TONE.get(signal.verdict, ("neutral", "⚫"))

    if rel_strength and rel_strength.vs_benchmark_pp is not None:
        rel_value = f"{rel_strength.vs_benchmark_pp:+.1f}pp vs S&P"
        rel_tone = tone_of(rel_strength.vs_benchmark_pp, epsilon=1.0)
    else:
        rel_value, rel_tone = "n/a", "neutral"

    if options_snap and options_snap.put_call_volume_ratio is not None:
        pcr = options_snap.put_call_volume_ratio
        options_value = f"P/C {pcr:.2f}"
        options_tone = "down" if pcr > 1.1 else ("up" if pcr < 0.7 else "neutral")
    else:
        options_value, options_tone = "n/a", "neutral"

    if earnings and earnings.days_until_earnings is not None:
        arrow_map = {"up": "↑", "down": "↓", "flat": "→"}
        earnings_value = f"{earnings.days_until_earnings}d {arrow_map.get(earnings.revision_direction, '')}".strip()
        earnings_tone = {"up": "up", "down": "down"}.get(earnings.revision_direction, "neutral")
    else:
        earnings_value, earnings_tone = "n/a", "neutral"

    chips = [
        ("Signal", f"{signal_icon} {signal.verdict}", signal_tone),
        ("Score", f"{signal.composite_score:+.2f}" if signal.composite_score is not None else "n/a", signal_tone),
        ("Analyst target", fmt_price(analyst.target_mean if analyst else None),
         tone_of(analyst.upside_pct if analyst else None)),
        ("Market cap", fmt_big(price.market_cap if price else None), "neutral"),
        ("Rel. strength (3M)", rel_value, rel_tone),
        ("Options flow", options_value, options_tone),
        ("Next earnings", earnings_value, earnings_tone),
    ]
    chip_html = "".join(
        f'<div class="jta-chip {tone}"><div class="jta-chip-label">{label}</div>'
        f'<div class="jta-chip-value">{value}</div></div>'
        for label, value, tone in chips
    )
    st.markdown(f'<div class="jta-chip-row">{chip_html}</div>', unsafe_allow_html=True)

    st.info(f"**Timing view:** {signal.timing_note}")

    with st.expander("📊 Signal track record (price-only backtest)"):
        if history is not None and not history.empty:
            bt = backtest_price_signal(bundle.ticker, history)
            if bt.total_samples == 0:
                st.caption(bt.note)
            else:
                st.caption(bt.note)
                rows_html = [
                    '<div class="jta-bt-row header"><div>Verdict</div><div>Samples</div>'
                    '<div>Avg forward return</div><div>Hit rate</div></div>'
                ]
                for b in bt.buckets:
                    if b.sample_count == 0:
                        rows_html.append(
                            f'<div class="jta-bt-row"><div class="jta-bt-verdict">{html_escape(b.verdict)}</div>'
                            '<div>0</div><div class="jta-bt-value neutral">—</div>'
                            '<div class="jta-bt-value neutral">—</div></div>'
                        )
                        continue
                    ret_tone = tone_of(b.avg_forward_return_pct)
                    rows_html.append(
                        f'<div class="jta-bt-row"><div class="jta-bt-verdict">{html_escape(b.verdict)}</div>'
                        f'<div>{b.sample_count}</div>'
                        f'<div class="jta-bt-value {ret_tone}">{fmt_pct(b.avg_forward_return_pct)}</div>'
                        f'<div class="jta-bt-value neutral">{b.hit_rate_pct:.0f}%</div></div>'
                    )
                st.markdown("".join(rows_html), unsafe_allow_html=True)
                st.caption(
                    f"Based on {bt.total_samples} historical samples. Past patterns are not a "
                    "guarantee of future results -- this validates the price-only formula's "
                    "historical tendency, not a prediction."
                )
        else:
            st.caption("Not enough price history available to backtest.")

    if history is not None and not history.empty:
        ctrl_left, ctrl_right = st.columns([3, 1])
        with ctrl_left:
            timeframe = st.pills(
                "Timeframe", list(TIMEFRAMES.keys()), default="1Y", key=f"tf_{bundle.ticker}",
                label_visibility="collapsed",
            ) or "1Y"
        with ctrl_right:
            show_ma = st.toggle("Moving averages", value=False, key=f"ma_{bundle.ticker}")
        st.plotly_chart(price_chart(history, TIMEFRAMES[timeframe], show_ma), width="stretch")
        with st.expander("View chart data as a table"):
            table = history[["Close"]].dropna().tail(90).copy()
            table.index = table.index.strftime("%Y-%m-%d")
            st.dataframe(table.style.format({"Close": "${:,.2f}"}), width="stretch")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Key numbers")
        rows = []
        if price:
            rows += [
                ("52-week range", f"{fmt_price(price.fifty_two_week_low)} - {fmt_price(price.fifty_two_week_high)}"),
                ("All-time high (observed)", f"{fmt_price(price.all_time_high)}"),
                ("All-time low (observed)", f"{fmt_price(price.all_time_low)}"),
                ("Momentum 3M / 1Y", f"{fmt_pct(price.momentum_3m_pct)} / {fmt_pct(price.momentum_1y_pct)}"),
            ]
        if fin:
            rows += [
                ("Revenue (TTM)", f"{fmt_big(fin.revenue_ttm)} ({fmt_pct(fin.revenue_growth_yoy_pct)} YoY)"),
                ("P/E (trailing / forward)",
                 f"{fin.pe_ratio:.1f} / {fin.forward_pe:.1f}" if fin.pe_ratio and fin.forward_pe else "n/a"),
                ("Free cash flow", fmt_big(fin.free_cash_flow)),
            ]
        if analyst:
            rows.append((
                "Analyst consensus",
                f"{analyst.recommendation_key or 'n/a'} ({analyst.num_analysts or '?'} analysts)",
            ))
        if insider:
            if insider.transactions:
                rows.append((
                    f"Insider activity ({insider.window_days}d)",
                    f"{insider.buy_count} buys / {insider.sell_count} sells",
                ))
            else:
                rows.append(("Insider activity", "No recent transactions found"))
        if rel_strength:
            peer_txt = (
                f"{fmt_pct(rel_strength.vs_peers_pp)} vs watchlist avg"
                if rel_strength.vs_peers_pp is not None else "n/a"
            )
            bench_txt = (
                f"{fmt_pct(rel_strength.vs_benchmark_pp)} vs S&P 500"
                if rel_strength.vs_benchmark_pp is not None else "n/a"
            )
            rows.append(("Relative strength (3M momentum)", f"{peer_txt} · {bench_txt}"))
        if options_snap:
            rows.append((
                "Options: Put/Call volume ratio",
                f"{options_snap.put_call_volume_ratio:.2f}" if options_snap.put_call_volume_ratio is not None else "n/a",
            ))
            if options_snap.atm_implied_vol_pct is not None and options_snap.realized_vol_30d_pct is not None:
                rows.append((
                    "Implied vs. 30d realized volatility",
                    f"{options_snap.atm_implied_vol_pct:.0f}% vs {options_snap.realized_vol_30d_pct:.0f}%",
                ))
        if earnings and earnings.next_earnings_date is not None:
            revision_label = {
                "up": "analysts raising estimates", "down": "analysts cutting estimates", "flat": "estimates flat",
            }.get(earnings.revision_direction, "n/a")
            days = earnings.days_until_earnings
            when = "today" if days == 0 else (f"in {days}d" if days and days > 0 else f"{abs(days)}d ago")
            rows.append(("Next earnings", f"{when} ({earnings.next_earnings_date.strftime('%b %d, %Y')}) — {revision_label}"))
        st.dataframe(
            pd.DataFrame(rows, columns=["Metric", "Value"]),
            hide_index=True,
            width="stretch",
        )

        st.subheader("Why this signal?")
        for line in signal.rationale:
            st.markdown(f"- {line}")

    with col_right:
        st.subheader("Recent news")
        if bundle.news:
            for item in bundle.news[:8]:
                date_str = item.published_at.strftime("%Y-%m-%d") if item.published_at else ""
                source = f" — {item.publisher}" if item.publisher else ""
                if item.link:
                    st.markdown(f"- [{item.title}]({item.link}) {source} {date_str}")
                else:
                    st.markdown(f"- {item.title}{source} {date_str}")
        else:
            st.caption("No recent news found.")

    if bundle.errors:
        with st.expander("Data gaps for this stock"):
            for err in bundle.errors:
                st.caption(f"- {err}")


def render_market_section(title: str, mapping: dict[str, str]):
    """A row of price/change cards for non-stock instruments, each
    expandable into a small trend-colored chart. No signal/analyst data --
    these aren't stocks."""
    st.subheader(title)
    tickers = tuple(mapping.keys())
    with st.spinner(f"Fetching {title.lower()}…"):
        snapshot = fetch_market_snapshot(tickers)

    for ticker, name in mapping.items():
        data = snapshot.get(ticker, {})
        price, change_pct, history = data.get("price"), data.get("change_pct"), data.get("history")
        tone = tone_of(change_pct)
        label = (
            f"{arrow(tone)} {name} ({ticker}) — {fmt_price(price)} "
            f"({fmt_pct(change_pct)})"
        )
        with st.expander(label):
            if history is not None and not history.empty:
                st.plotly_chart(price_chart(history, TIMEFRAMES["3M"], False), width="stretch",
                                 key=f"chart_{ticker}")
            else:
                st.caption("No price history available right now.")


def render_dashboard(watchlist: Watchlist, settings):
    st.sidebar.header("What to analyze")
    group = st.sidebar.radio(
        "Group",
        ["core", "emerging", "all", "commodities", "indices"],
        format_func={
            "core": "Core top 10", "emerging": "Emerging names", "all": "Everything",
            "commodities": "🪙 Commodities", "indices": "📊 Indices",
        }.get,
    )
    name_lookup = {**COMMODITIES, **INDICES}
    if group == "commodities":
        available = list(COMMODITIES.keys())
    elif group == "indices":
        available = list(INDICES.keys())
    else:
        available = watchlist.tickers(group)
    tickers = st.sidebar.multiselect(
        "Leave empty for the whole group", available,
        format_func=lambda t: f"{name_lookup[t]} ({t})" if t in name_lookup else t,
    )
    if not tickers:
        tickers = available

    want_ai = st.sidebar.toggle(
        "AI-written analyst note",
        value=False,
        help="Needs a Gemini API key in your .env file. Adds a short written "
             "research note per stock.",
        disabled=not settings.has_llm,
    )
    if not settings.has_llm:
        st.sidebar.caption("Add GEMINI_API_KEY to .env to unlock AI notes.")

    run = st.sidebar.button("Run analysis", type="primary", width="stretch")
    st.sidebar.caption("Data is cached for 15 minutes. Rerun after that for fresh numbers.")

    st.title("📈 Junior Trading Analyst")
    st.caption("AI infrastructure stock tracker — prices, news, analyst views, insider activity, and a plain-English signal. "
               "Also covers commodities and indices for broader market context.")
    if DEMO_MODE:
        st.warning("**Demo mode** — every number on this page is synthetic sample data, not real market data. "
                   "Launch without `JTA_DEMO=1` for live data.")

    market_col1, market_col2 = st.columns(2)
    with market_col1:
        render_market_section("🪙 Commodities", COMMODITIES)
    with market_col2:
        render_market_section("📊 Indices", INDICES)
    st.markdown("---")

    if not run and "last_run_tickers" not in st.session_state:
        st.info("👈 Pick a stock group in the sidebar and press **Run analysis** to get started.")
        st.markdown(DISCLAIMER)
        return

    if run:
        st.session_state["last_run_tickers"] = tickers
        st.session_state["want_ai"] = want_ai
    tickers = st.session_state["last_run_tickers"]
    want_ai = st.session_state.get("want_ai", False)

    results = []
    failures = []
    progress = st.progress(0.0, text="Fetching market data…")
    for i, ticker in enumerate(tickers):
        progress.progress((i + 1) / len(tickers), text=f"Fetching {ticker}…")
        try:
            bundle, signal, history = fetch_ticker_data(ticker)
            results.append((bundle, signal, history))
        except Exception as exc:
            failures.append(f"{ticker}: {exc}")
    progress.empty()

    if failures:
        st.warning(
            "Couldn't fetch data for: " + "; ".join(failures) +
            ". This usually means no internet access or the data source is rate-limiting — try again in a minute."
        )
    if not results:
        return

    try:
        benchmark_bundle, _, _ = fetch_ticker_data("^GSPC")
        benchmark_price = benchmark_bundle.price
    except Exception:
        benchmark_price = None
    peer_prices = [bundle.price for bundle, _, _ in results if bundle.price]

    macro_notes, macro_headlines = fetch_macro_notes()
    if macro_notes or macro_headlines:
        with st.expander("🌍 Macro backdrop (rates, inflation, sector headlines)"):
            for note in macro_notes:
                st.markdown(f"- {note}")
            for headline in macro_headlines:
                st.markdown(f"- {headline}")

    st.subheader("Watchlist at a glance")
    summary_rows = []
    row_html = []
    for bundle, signal, _ in results:
        price, analyst = bundle.price, bundle.analyst
        display_name = display_name_for(bundle.ticker, bundle.company_name)
        pos = None
        if price and price.current_price and price.fifty_two_week_high and price.fifty_two_week_low:
            span = price.fifty_two_week_high - price.fifty_two_week_low
            pos = (price.current_price - price.fifty_two_week_low) / span * 100 if span else None
        summary_rows.append({
            "Ticker": bundle.ticker,
            "Company": display_name,
            "Price": price.current_price if price else None,
            "Today": price.day_change_pct if price else None,
            "Signal": VERDICT_BADGES.get(signal.verdict, signal.verdict),
            "Score": signal.composite_score,
            "Analyst upside": analyst.upside_pct if analyst else None,
            "52w position": pos,
        })
        day_tone = tone_of(price.day_change_pct if price else None)
        signal_tone, signal_icon = VERDICT_TONE.get(signal.verdict, ("neutral", "⚫"))
        row_html.append(
            f'<div class="jta-row">'
            f'<div class="jta-row-left"><span class="jta-row-ticker">{html_escape(bundle.ticker)}</span>'
            f'<span class="jta-row-name">{html_escape(display_name)}</span></div>'
            f'<div class="jta-row-signal">{signal_icon} {signal.verdict}</div>'
            f'<div class="jta-row-right"><span class="jta-row-price">{fmt_price(price.current_price if price else None)}</span>'
            f'<span class="jta-row-delta {day_tone}">{arrow(day_tone)} {fmt_pct(price.day_change_pct if price else None)}</span></div>'
            f'</div>'
        )
    st.markdown("".join(row_html), unsafe_allow_html=True)

    summary = pd.DataFrame(summary_rows)
    with st.expander("View as sortable table"):
        st.dataframe(
            summary,
            width="stretch",
            hide_index=True,
            column_config={
                "Price": st.column_config.NumberColumn(format="$%.2f"),
                "Today": st.column_config.NumberColumn(format="%+.1f%%"),
                "Score": st.column_config.NumberColumn(format="%+.2f", help="-1 (very bearish) to +1 (very bullish)"),
                "Analyst upside": st.column_config.NumberColumn(format="%+.1f%%"),
                "52w position": st.column_config.ProgressColumn(
                    format="%.0f%%", min_value=0, max_value=100,
                    help="Where today's price sits in the 52-week range (100% = at the high)",
                ),
            },
        )

    st.subheader("Stock details")
    for bundle, signal, history in results:
        display_name = display_name_for(bundle.ticker, bundle.company_name)
        label = f"{VERDICT_BADGES.get(signal.verdict, signal.verdict)}  ·  {bundle.ticker}"
        if display_name:
            label += f" — {display_name}"
        with st.expander(label):
            render_ticker_details(bundle, signal, history, peer_prices=peer_prices, benchmark_price=benchmark_price)
            if want_ai and settings.has_llm:
                note_key = f"ai_note_{bundle.ticker}"
                if note_key not in st.session_state:
                    with st.spinner("Writing analyst note…"):
                        try:
                            st.session_state[note_key] = generate_narrative(
                                bundle, signal, None, settings.gemini_api_key,
                            )
                        except Exception as exc:
                            st.session_state[note_key] = f"_AI note failed: {exc}_"
                st.subheader("Analyst note (AI-written)")
                st.markdown(st.session_state[note_key])

    st.markdown("---")
    st.markdown(DISCLAIMER)


def render_ai_news(watchlist: Watchlist, settings):
    st.title("🗞️ AI News")
    st.caption(
        "Headlines about your tracked AI infrastructure stocks and the broader AI industry, "
        "with the original source and date on every item. Refreshes weekly — use the button "
        "below for an update sooner."
    )
    if DEMO_MODE:
        st.warning("**Demo mode** — these headlines are synthetic placeholders, not real news.")
    if not settings.has_newsapi:
        st.caption(
            "ℹ️ Add NEWSAPI_KEY to unlock broader industry headlines (deals, regulation, "
            "macro) beyond each company's own news feed. See the Help tab."
        )

    all_tickers = tuple(watchlist.all_tickers())
    if not all_tickers:
        st.info("Your watchlist is empty — add stocks in the Watchlist tab first.")
        return

    if st.button("🔄 Refresh now", key="refresh_ai_news"):
        fetch_weekly_ai_news.clear()

    with st.spinner("Gathering AI news…"):
        items, fetched_at = fetch_weekly_ai_news(all_tickers)

    st.caption(f"Last refreshed: {fetched_at.strftime('%b %d, %Y %H:%M UTC')} · auto-refreshes weekly")

    if not items:
        st.info("No news found right now — try refreshing in a bit.")
        return

    tags = ["AI Industry"] + list(all_tickers)
    picked = st.multiselect("Filter by stock", tags, default=[], placeholder="All stocks + AI industry")
    shown = [i for i in items if not picked or i["tag"] in picked]
    display_limit = 60

    st.caption(
        f"Showing {min(len(shown), display_limit)} of {len(shown)} matching headlines "
        f"({len(items)} total from the last refresh)."
    )
    for item in shown[:display_limit]:
        source = html_escape(item["publisher"] or "Unknown source")
        title = html_escape(item["title"])
        tag = html_escape(item["tag"])
        link = safe_href(item["link"])
        title_html = f'<a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>' if link else title
        st.markdown(
            f"""
            <div class="jta-news-row">
              <div class="jta-news-title">{title_html}</div>
              <div class="jta-news-meta">
                <span class="jta-news-tag">{tag}</span>
                <span>📰 {source}</span>
                <span>· {fmt_relative(item["published_at"])}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(DISCLAIMER)


CONDITION_LABELS = {
    "price_above": "Price rises above",
    "price_below": "Price falls below",
    "signal_bullish": "Signal turns Bullish",
    "signal_bearish": "Signal turns Bearish",
}


def render_alerts(watchlist: Watchlist, settings):
    st.title("🔔 Alerts")
    st.caption(
        "Set price or signal conditions on any tracked stock, commodity, or index. Status "
        "below reflects the most recently fetched data (cached up to 15 minutes)."
    )

    book = AlertBook.load(settings.alerts_path)
    all_tickers = watchlist.all_tickers() + list(COMMODITIES.keys()) + list(INDICES.keys())

    def ticker_label(t: str) -> str:
        name = display_name_for(t, None)
        return f"{name} ({t})" if name else t

    st.subheader("Add an alert")
    with st.form("add_alert_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([1.3, 1.3, 1])
        with col1:
            ticker = st.selectbox("Ticker", all_tickers, format_func=ticker_label)
        with col2:
            condition = st.selectbox("Condition", list(CONDITION_LABELS.keys()), format_func=CONDITION_LABELS.get)
        needs_threshold = condition in ("price_above", "price_below")
        with col3:
            threshold = st.number_input(
                "Price threshold ($)", min_value=0.0, value=100.0, disabled=not needs_threshold,
            )
        if st.form_submit_button("Add alert", type="primary"):
            rule = new_alert_rule(ticker, condition, threshold if needs_threshold else None)
            book.add(rule)
            book.save()
            st.success(f"Added: {rule.describe()}")
            st.rerun()

    st.markdown("---")
    st.subheader("Your alerts")
    if not book.rules:
        st.info("No alerts configured yet -- add one above.")
    else:
        if st.button("🔄 Check now (refresh data)"):
            fetch_ticker_data.clear()
            st.rerun()

        triggered_count = 0
        rows_html = []
        for rule in book.rules:
            try:
                bundle, signal, _ = fetch_ticker_data(rule.ticker)
                result = evaluate_rule(rule, bundle.price, signal)
            except Exception as exc:
                result = AlertResult(rule, False, "error", error=str(exc))
            if result.triggered:
                triggered_count += 1
            status_class = "triggered" if result.triggered else "ok"
            status_text = "🔴 TRIGGERED" if result.triggered else "🟢 OK"
            rows_html.append(
                f'<div class="jta-alert-row {status_class}">'
                f'<div>{html_escape(rule.describe())}</div>'
                '<div style="display:flex; align-items:center; gap:12px;">'
                f'<span>{html_escape(result.current_value)}</span>'
                f'<span class="jta-alert-status {status_class}">{status_text}</span>'
                '</div></div>'
            )

        if triggered_count:
            st.error(f"⚠️ {triggered_count} alert(s) triggered right now.")
        st.markdown("".join(rows_html), unsafe_allow_html=True)

        st.subheader("Remove an alert")
        with st.form("remove_alert_form", clear_on_submit=True):
            options = {r.id: r.describe() for r in book.rules}
            chosen_id = st.selectbox("Alert", list(options.keys()), format_func=lambda i: options[i])
            if st.form_submit_button("Remove"):
                if book.remove(chosen_id):
                    book.save()
                    st.success("Removed.")
                    st.rerun()

    st.markdown("---")
    if not settings.has_alert_webhook:
        st.caption(
            "ℹ️ Alerts here only update when you have this app open. For real background alerts "
            "(fired even when nobody's looking at the app), set the `ALERT_WEBHOOK_URL` repo "
            "secret and the scheduled GitHub Actions check picks them up -- see DEPLOY.md."
        )
    st.caption(
        "⚠️ On Streamlit Cloud, alerts added here reset when the app restarts (ephemeral "
        "filesystem, same as the Watchlist tab). For alerts to survive restarts and be seen by "
        "the scheduled background check, commit config/alerts.yaml to your repo directly."
    )


def render_watchlist_editor(watchlist: Watchlist):
    st.title("📋 Manage your watchlist")
    st.caption("These are the stocks the analyst tracks. Changes are saved to config/watchlist.yaml.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Core top 10")
        for ticker in watchlist.groups.get("core", []):
            st.markdown(f"- **{ticker}**")
    with col2:
        st.subheader("Emerging names")
        for ticker in watchlist.groups.get("emerging", []):
            st.markdown(f"- **{ticker}**")

    st.markdown("---")
    add_col, remove_col = st.columns(2)

    with add_col:
        st.subheader("Add a stock")
        with st.form("add_form", clear_on_submit=True):
            new_ticker = st.text_input("Ticker symbol (e.g. PLTR)")
            new_group = st.selectbox("Group", ["emerging", "core"])
            if st.form_submit_button("Add", type="primary"):
                symbol = new_ticker.strip().upper()
                if not symbol:
                    st.error("Please type a ticker symbol.")
                elif watchlist.add(symbol, new_group):
                    watchlist.save()
                    st.success(f"Added {symbol} to {new_group}.")
                    st.rerun()
                else:
                    st.info(f"{symbol} is already in the {new_group} list.")

    with remove_col:
        st.subheader("Remove a stock")
        with st.form("remove_form", clear_on_submit=True):
            target = st.selectbox("Ticker", watchlist.all_tickers())
            if st.form_submit_button("Remove"):
                if watchlist.remove(target):
                    watchlist.save()
                    st.success(f"Removed {target}.")
                    st.rerun()


def render_help(settings):
    st.title("ℹ️ How to read this dashboard")
    st.markdown(
        """
**The signal** blends four things into one score from **-1 (very bearish)** to **+1 (very bullish)**:

| Component | What it means | Weight |
|---|---|---|
| Analyst sentiment | What Wall Street analysts recommend (buy/hold/sell consensus) | 40% |
| Price momentum | How the stock has moved over the last 3-12 months | 30% |
| Trend | Whether the 50-day average price is above the 200-day average | 15% |
| Insider activity | Whether company executives are buying or selling their own stock | 15% |

**The timing view** is a plain-English note about *where* the price sits — for
example, a stock at its 52-week high with a bullish signal is still riskier to
buy today than the same signal after a pullback.

**The AI-written analyst note** (optional) is a short research memo written by
Google's Gemini from the same data shown on screen — it never invents numbers.

**The AI News tab** aggregates headlines across every stock on your watchlist,
plus broader AI-industry news if you've added a NewsAPI key. It refreshes
automatically about once a week (there's also a manual "Refresh now" button),
and every headline shows its original source and publish date so you can go
verify it yourself.

**"Signal track record"** (inside each stock's detail card) backtests the
**price-only** part of the signal (momentum + trend -- analyst ratings and
insider activity aren't available as history, only as a snapshot) against
that stock's own past: historically, when this said "Bullish," what actually
happened to the price over the following weeks? This is the one section that
validates whether the signal has any track record at all, rather than just
sounding plausible -- treat the rest of the score as informed opinion, not a
tested prediction, until you've checked this.

**Options flow, relative strength, and next earnings** are three extra chips
on each stock's card: options positioning (put/call ratio, implied vs.
realized volatility) reads what options traders are pricing in; relative
strength compares the stock's 3-month momentum to your whole watchlist and
to the S&P 500 (is it actually outperforming, or just riding a rising tide?);
and the earnings chip shows days until the next print plus whether analysts
have been raising or cutting estimates over the last 90 days.

**The Alerts tab** lets you set a price or signal condition on any tracked
ticker. Inside the app, status updates whenever you have it open (data is
cached up to 15 minutes). For alerts that fire even when nobody has the app
open, add an `ALERT_WEBHOOK_URL` secret (a Slack or Discord incoming webhook)
to your GitHub repo -- a scheduled GitHub Actions job
(`.github/workflows/alerts.yml`) checks your rules on its own and posts there.
Note: rules added through the *deployed* app don't persist across restarts --
commit `config/alerts.yaml` to your repo for them to stick.

---

### Your data connections
"""
    )
    checks = [
        ("Market data (prices, ratings, news)", True, "Built in — no key needed"),
        ("AI-written analyst notes", settings.has_llm, "Add GEMINI_API_KEY to .env"),
        ("Extra news & insider data (Finnhub)", settings.has_finnhub, "Add FINNHUB_API_KEY to .env"),
        ("Press & macro headline search (NewsAPI)", settings.has_newsapi, "Add NEWSAPI_KEY to .env"),
        ("Interest rates & inflation (FRED)", settings.has_fred, "Add FRED_API_KEY to .env"),
    ]
    for name, ok, hint in checks:
        st.markdown(f"- {'✅' if ok else '⬜'} **{name}**" + ("" if ok else f" — {hint}"))

    st.markdown("---")
    st.markdown(DISCLAIMER)


def main():
    inject_css()
    _apply_streamlit_secrets()
    settings = load_settings()
    watchlist = Watchlist.load(settings.watchlist_path)

    tab_dash, tab_news, tab_alerts, tab_watch, tab_help = st.tabs(
        ["📊 Dashboard", "🗞️ AI News", "🔔 Alerts", "📋 Watchlist", "ℹ️ Help"]
    )
    with tab_dash:
        render_dashboard(watchlist, settings)
    with tab_news:
        render_ai_news(watchlist, settings)
    with tab_alerts:
        render_alerts(watchlist, settings)
    with tab_watch:
        render_watchlist_editor(watchlist)
    with tab_help:
        render_help(settings)


main()
