"""Junior Trading Analyst - web dashboard.

Run with:  streamlit run app.py
Then open the browser tab it launches (usually http://localhost:8501).
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analyst.analysis.signal import StockSignal, compute_signal
from analyst.analysis.synthesizer import generate_narrative
from analyst.config import load_settings
from analyst.data_sources.aggregator import build_bundle, build_macro_snapshot
from analyst.data_sources.base import StockBundle
from analyst.data_sources.market_data import MarketDataProvider
from analyst.report.builder import DISCLAIMER
from analyst.universe import Watchlist

st.set_page_config(page_title="Junior Trading Analyst", page_icon="📈", layout="wide")

# Chart colors: fixed categorical assignment (see dataviz palette reference).
COLOR_CLOSE = "#2a78d6"   # blue   - price
COLOR_SMA50 = "#1baf7a"   # aqua   - 50-day average
COLOR_SMA200 = "#eda100"  # yellow - 200-day average
COLOR_GRID = "#e1e0d9"

VERDICT_BADGES = {
    "Strongly Bullish": "🟢 Strongly Bullish",
    "Bullish": "🟢 Bullish",
    "Neutral": "⚪ Neutral",
    "Bearish": "🔴 Bearish",
    "Strongly Bearish": "🔴 Strongly Bearish",
    "Unrated": "⚫ Unrated",
}

CACHE_TTL_SECONDS = 15 * 60
DEMO_MODE = os.environ.get("JTA_DEMO", "").strip() in ("1", "true", "yes")


def _make_provider():
    if DEMO_MODE:
        from analyst.data_sources.demo_data import DemoMarketDataProvider

        return DemoMarketDataProvider()
    return MarketDataProvider()


def fmt_price(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "n/a"


def fmt_pct(value: float | None) -> str:
    return f"{value:+.1f}%" if value is not None else "n/a"


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
def fetch_macro_notes() -> tuple[list[str], list[str]]:
    settings = load_settings()
    macro = build_macro_snapshot(settings)
    headlines = [
        f"{item.title}" + (f" ({item.publisher})" if item.publisher else "")
        for item in macro.headlines[:8]
    ]
    return macro.notes, headlines


def price_chart(ticker: str, history: pd.DataFrame) -> go.Figure:
    closes = history["Close"].dropna()
    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=closes.index, y=closes, name="Close",
                             line=dict(color=COLOR_CLOSE, width=2), hovertemplate="%{y:$,.2f}<extra>Close</extra>"))
    fig.add_trace(go.Scatter(x=sma50.index, y=sma50, name="50-day avg",
                             line=dict(color=COLOR_SMA50, width=2), hovertemplate="%{y:$,.2f}<extra>50-day avg</extra>"))
    fig.add_trace(go.Scatter(x=sma200.index, y=sma200, name="200-day avg",
                             line=dict(color=COLOR_SMA200, width=2), hovertemplate="%{y:$,.2f}<extra>200-day avg</extra>"))
    fig.update_layout(
        height=380,
        margin=dict(l=10, r=10, t=30, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        yaxis=dict(title=None, gridcolor=COLOR_GRID, tickprefix="$"),
        xaxis=dict(title=None, showgrid=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render_ticker_details(bundle: StockBundle, signal: StockSignal, history: pd.DataFrame | None):
    price, analyst, insider, fin = bundle.price, bundle.analyst, bundle.insider, bundle.financials

    top = st.columns(4)
    top[0].metric(
        "Price",
        fmt_price(price.current_price if price else None),
        fmt_pct(price.day_change_pct if price else None),
    )
    top[1].metric("Signal", signal.verdict,
                  f"score {signal.composite_score:+.2f}" if signal.composite_score is not None else None,
                  delta_color="off")
    top[2].metric("Analyst target", fmt_price(analyst.target_mean if analyst else None),
                  fmt_pct(analyst.upside_pct if analyst else None))
    top[3].metric("Market cap", fmt_big(price.market_cap if price else None))

    st.info(f"**Timing view:** {signal.timing_note}")

    if history is not None and not history.empty:
        st.plotly_chart(price_chart(bundle.ticker, history), width="stretch")
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


def render_dashboard(watchlist: Watchlist, settings):
    st.sidebar.header("What to analyze")
    group = st.sidebar.radio(
        "Stock group",
        ["core", "emerging", "all"],
        format_func={"core": "Core top 10", "emerging": "Emerging names", "all": "Everything"}.get,
    )
    available = watchlist.tickers(group)
    tickers = st.sidebar.multiselect("Stocks (leave empty for the whole group)", available)
    if not tickers:
        tickers = available

    want_ai = st.sidebar.toggle(
        "AI-written analyst note",
        value=False,
        help="Needs an Anthropic API key in your .env file. Adds a short written "
             "research note per stock.",
        disabled=not settings.has_llm,
    )
    if not settings.has_llm:
        st.sidebar.caption("Add ANTHROPIC_API_KEY to .env to unlock AI notes.")

    run = st.sidebar.button("Run analysis", type="primary", width="stretch")
    st.sidebar.caption("Data is cached for 15 minutes. Rerun after that for fresh numbers.")

    st.title("📈 Junior Trading Analyst")
    st.caption("AI infrastructure stock tracker — prices, news, analyst views, insider activity, and a plain-English signal.")
    if DEMO_MODE:
        st.warning("**Demo mode** — every number on this page is synthetic sample data, not real market data. "
                   "Launch without `JTA_DEMO=1` for live data.")

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

    macro_notes, macro_headlines = fetch_macro_notes()
    if macro_notes or macro_headlines:
        with st.expander("🌍 Macro backdrop (rates, inflation, sector headlines)"):
            for note in macro_notes:
                st.markdown(f"- {note}")
            for headline in macro_headlines:
                st.markdown(f"- {headline}")

    st.subheader("Watchlist at a glance")
    summary_rows = []
    for bundle, signal, _ in results:
        price, analyst = bundle.price, bundle.analyst
        pos = None
        if price and price.current_price and price.fifty_two_week_high and price.fifty_two_week_low:
            span = price.fifty_two_week_high - price.fifty_two_week_low
            pos = (price.current_price - price.fifty_two_week_low) / span * 100 if span else None
        summary_rows.append({
            "Ticker": bundle.ticker,
            "Company": bundle.company_name or "",
            "Price": price.current_price if price else None,
            "Today": price.day_change_pct if price else None,
            "Signal": VERDICT_BADGES.get(signal.verdict, signal.verdict),
            "Score": signal.composite_score,
            "Analyst upside": analyst.upside_pct if analyst else None,
            "52w position": pos,
        })
    summary = pd.DataFrame(summary_rows)
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
        label = f"{VERDICT_BADGES.get(signal.verdict, signal.verdict)}  ·  {bundle.ticker}"
        if bundle.company_name:
            label += f" — {bundle.company_name}"
        with st.expander(label):
            render_ticker_details(bundle, signal, history)
            if want_ai and settings.has_llm:
                note_key = f"ai_note_{bundle.ticker}"
                if note_key not in st.session_state:
                    with st.spinner("Writing analyst note…"):
                        try:
                            st.session_state[note_key] = generate_narrative(
                                bundle, signal, None, settings.anthropic_api_key,
                            )
                        except Exception as exc:
                            st.session_state[note_key] = f"_AI note failed: {exc}_"
                st.subheader("Analyst note (AI-written)")
                st.markdown(st.session_state[note_key])

    st.markdown("---")
    st.markdown(DISCLAIMER)


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
Claude from the same data shown on screen — it never invents numbers.

---

### Your data connections
"""
    )
    checks = [
        ("Market data (prices, ratings, news)", True, "Built in — no key needed"),
        ("AI-written analyst notes", settings.has_llm, "Add ANTHROPIC_API_KEY to .env"),
        ("Extra news & insider data (Finnhub)", settings.has_finnhub, "Add FINNHUB_API_KEY to .env"),
        ("Press & macro headline search (NewsAPI)", settings.has_newsapi, "Add NEWSAPI_KEY to .env"),
        ("Interest rates & inflation (FRED)", settings.has_fred, "Add FRED_API_KEY to .env"),
    ]
    for name, ok, hint in checks:
        st.markdown(f"- {'✅' if ok else '⬜'} **{name}**" + ("" if ok else f" — {hint}"))

    st.markdown("---")
    st.markdown(DISCLAIMER)


def main():
    settings = load_settings()
    watchlist = Watchlist.load(settings.watchlist_path)

    tab_dash, tab_watch, tab_help = st.tabs(["📊 Dashboard", "📋 Watchlist", "ℹ️ Help"])
    with tab_dash:
        render_dashboard(watchlist, settings)
    with tab_watch:
        render_watchlist_editor(watchlist)
    with tab_help:
        render_help(settings)


main()
