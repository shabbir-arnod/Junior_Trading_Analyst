"""Turns structured data (StockBundle + StockSignal) into a written
narrative using the Gemini API. Optional: if no GEMINI_API_KEY is
configured, callers should skip this and the report simply omits the
narrative section.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from analyst.analysis.signal import StockSignal
from analyst.data_sources.base import MacroSnapshot, StockBundle

# "-latest" alias so this keeps working as Google rolls out newer Flash
# versions, instead of pinning to a dated model ID that gets deprecated.
MODEL = "gemini-flash-latest"

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
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    data_json = _bundle_to_json(bundle, signal, macro)

    response = client.models.generate_content(
        model=MODEL,
        contents=f"Ticker: {bundle.ticker}\n\nStructured data:\n{data_json}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1024,
        ),
    )
    return (response.text or "").strip()
