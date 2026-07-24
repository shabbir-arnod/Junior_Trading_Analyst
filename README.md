# Junior Trading Analyst

An agent that tracks AI infrastructure stocks (chips, cloud, networking,
power, data-center supply chain) and produces a markdown research report
covering price/technicals, analyst ratings, insider activity, recent news,
company financials, and macro backdrop -- plus a heuristic Bullish/Bearish
signal and an optional AI-written narrative.

**This is not financial advice.** It's a research aid that aggregates
public data and heuristics; always do your own diligence.

## What it tracks

- **Watchlist** (`config/watchlist.yaml`): a `core` group of 10
  established AI infrastructure growth stocks and an `emerging` group of
  smaller/newer names. Edit it by hand or via the CLI.
- **Per stock**: current price, day change, 52-week high/low, observed
  all-time high/low, 50-day and 200-day moving averages, 1M/3M/6M/1Y
  momentum, market cap, analyst consensus rating and price targets,
  insider buy/sell activity, recent company news, and core financials
  (revenue growth, margins, EPS, P/E, free cash flow).
- **Macro/sector backdrop**: interest rates, inflation, and AI-infra-related
  macro headlines (needs optional API keys, see below).
- **Composite signal**: a -1..+1 score blending analyst sentiment, price
  momentum, trend (50d vs 200d SMA), and insider activity into a
  Bullish/Neutral/Bearish verdict, a confidence level, and a plain-English
  timing note (e.g. "near 52-week high, chasing here is risky" vs.
  "near 52-week low with positive analyst sentiment -- possible value
  entry").
- **AI-written analyst note** (optional, needs a free Gemini API key): a
  short research note synthesized from the structured data above --
  executive summary, key drivers, macro read-through, risks, and bottom
  line -- explicitly grounded in only the fetched data, with no invented
  numbers.

## Quick start (non-technical): the web dashboard

The easiest way to use the analyst is the point-and-click web dashboard:

- **Windows**: double-click `start_dashboard.bat`
- **Mac/Linux**: run `./start_dashboard.sh` in a terminal

The first run installs everything it needs (give it a minute), then your
browser opens the dashboard. Pick a stock group in the sidebar, press
**Run analysis**, and you get:

- a **watchlist summary table** with each stock's price, signal
  (🟢 Bullish / ⚪ Neutral / 🔴 Bearish), score, analyst upside, and where
  it sits in its 52-week range,
- expandable **per-stock detail** with a 2-year price chart (with 50-day
  and 200-day averages), key numbers, why-this-signal breakdown, recent
  news, insider activity, and an optional AI-written analyst note,
- a **Watchlist tab** to add/remove stocks with a form (no file editing),
- a **Help tab** explaining how to read everything, in plain English.

Want to try it without internet or any API keys? Launch in demo mode with
clearly-watermarked synthetic data: `JTA_DEMO=1 streamlit run app.py`
(Windows: `set JTA_DEMO=1 && python -m streamlit run app.py`).

You only need Python installed (python.org, version 3.10 or newer) —
everything else is automatic.

## Setup (manual / command-line)

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in whichever keys you have
streamlit run app.py   # web dashboard, or use the CLI below
```

The agent runs with **zero API keys** using [yfinance](https://github.com/ranaroussi/yfinance)
for prices, technicals, analyst ratings, insider transactions, and news.
Each optional key in `.env` unlocks more:

| Key | Unlocks | Free tier |
|---|---|---|
| `GEMINI_API_KEY` | AI-written narrative analyst note | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (free) |
| `FINNHUB_API_KEY` | Broader company news, sturdier insider-transaction data | [finnhub.io/register](https://finnhub.io/register) |
| `NEWSAPI_KEY` | Wider press/deal/macro headline search | [newsapi.org/register](https://newsapi.org/register) |
| `FRED_API_KEY` | Fed funds rate, CPI, 10-year Treasury yield | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |

## Usage

```bash
# Full report across the whole watchlist (core + emerging), printed to stdout
python -m analyst.cli report

# Just the core top-10, written to a file
python -m analyst.cli report --group core --out reports/latest.md

# Specific tickers, skip the AI narrative (faster, no LLM key needed)
python -m analyst.cli report --tickers NVDA,AMD,SMCI --no-llm

# Manage the watchlist
python -m analyst.cli watchlist
python -m analyst.cli add CRWV --group emerging
python -m analyst.cli remove APLD
```

### Scheduling

The CLI is a one-shot report generator by design. To "keep an eye" on the
watchlist continuously, wrap it in a scheduler, e.g. a daily cron job or a
GitHub Actions workflow that runs `python -m analyst.cli report --out
reports/$(date +%F).md` and commits/uploads the result -- the pipeline
itself doesn't need to change.

## Project layout

```
app.py                      web dashboard (streamlit run app.py)
start_dashboard.sh / .bat   one-click launchers (Mac/Linux and Windows)
analyst/
  cli.py                    entry point (report / watchlist / add / remove)
  universe.py                watchlist loading & comment-preserving edits
  config.py                   .env loading
  data_sources/
    base.py                    shared data models (PriceSnapshot, AnalystView, ...)
    market_data.py              yfinance provider (no key required)
    demo_data.py                offline synthetic data (JTA_DEMO=1)
    finnhub_provider.py         optional: news, insider data, rec. trends
    newsapi_provider.py         optional: broad news/press-release search
    fred_provider.py            optional: macro indicators
    aggregator.py                fans a ticker out to all configured providers
  analysis/
    technicals.py               52w/ATH-ATL, moving averages, momentum
    signal.py                   composite Bullish/Bearish scoring + timing note
    synthesizer.py              Claude-powered narrative (optional)
  report/
    builder.py                  assembles the final markdown report
config/watchlist.yaml         tracked tickers (core / emerging groups)
tests/                        pytest suite, fully mocked (no network needed)
```

## Testing

```bash
pytest
```

All tests use mocked/synthetic data and don't hit any network -- they
validate the technicals math, signal scoring, watchlist editing (including
that hand-written comments in `watchlist.yaml` survive `add`/`remove`),
and report assembly.

## Known limitations

- "All-time high/low" is the max/min observed over the fetched price
  history (yfinance's longest available range), not a verified exchange
  record for tickers with long histories predating that range.
- Data quality depends on yfinance's public, undocumented endpoints and
  can change without notice; optional providers add resilience but aren't
  required.
- The composite signal is a transparent heuristic (see `analysis/signal.py`),
  not a trained model -- treat it as one input among many, not a
  prediction guarantee.
