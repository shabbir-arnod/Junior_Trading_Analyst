"""Turns structured data (StockBundle + StockSignal) into a written
narrative using the Claude API. Optional: if no ANTHROPIC_API_KEY is
configured, callers should skip this and the report simply omits the
narrative section.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from analyst.analysis.signal import StockSignal
from analyst.data_sources.base import MacroSnapshot, StockBundle

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """\
You are a meticulous equity research analyst covering AI infrastructure \
stocks (chips, cloud, networking, power, and data-center supply chain). \
You are given structured data already fetched from market/news sources -- \
prices, technicals, analyst ratings, insider activity, recent news, and \
macro headlines -- for one ticker.

Write a concise research note using ONLY the given data:
1. One-paragraph executive summary (thesis in plain English).
2. Key drivers: 3-5 bullets tying specific news/deals/earnings items to \
the stock's likely trajectory.
3. Macro/micro read-through: how the given macro headlines and sector \
context affect this name specifically.
4. Risks: 2-3 bullets on what would invalidate the bullish or bearish case.
5. Bottom line: one sentence restating the signal verdict and timing note \
in your own words, explicitly flagged as analysis, not a directive to buy \
or sell.

Rules:
- Never invent data not present in the input (no fabricated numbers, \
dates, or quotes).
- If a section has no supporting data, say so briefly instead of padding.
- Keep the whole note under 350 words.
- Do not give unqualified "buy" or "sell" instructions -- frame everything \
as analysis of an existing signal, and end with a one-line reminder that \
this is not financial advice.
"""


def _bundle_to_json(bundle: StockBundle, signal: StockSignal, macro: MacroSnapshot | None) -> str:
    def default(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)

    payload = {
        "bundle": asdict(bundle),
        "signal": asdict(signal),
        "macro": asdict(macro) if macro else None,
    }
    return json.dumps(payload, default=default, indent=2)


def generate_narrative(
    bundle: StockBundle,
    signal: StockSignal,
    macro: MacroSnapshot | None,
    api_key: str,
) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    data_json = _bundle_to_json(bundle, signal, macro)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Ticker: {bundle.ticker}\n\nStructured data:\n{data_json}",
            }
        ],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
