"""Command-line entry point.

Usage:
    python -m analyst.cli report [--group core|emerging|all] [--tickers NVDA,AMD] [--out FILE] [--no-llm]
    python -m analyst.cli watchlist
    python -m analyst.cli add TICKER --group core|emerging
    python -m analyst.cli remove TICKER
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from analyst.config import load_settings
from analyst.data_sources.market_data import MarketDataProvider
from analyst.report.builder import build_report
from analyst.universe import Watchlist


def cmd_report(args: argparse.Namespace) -> int:
    settings = load_settings()
    watchlist = Watchlist.load(settings.watchlist_path)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        tickers = watchlist.tickers(args.group)

    if not tickers:
        print("No tickers to report on.", file=sys.stderr)
        return 1

    if not settings.has_llm and not args.no_llm:
        print(
            "Note: GEMINI_API_KEY not set -- generating data-only report "
            "(no AI narrative). See .env.example.",
            file=sys.stderr,
        )

    print(f"Fetching data for {len(tickers)} ticker(s): {', '.join(tickers)}", file=sys.stderr)
    report_md = build_report(
        tickers,
        settings,
        include_llm=not args.no_llm,
        market=MarketDataProvider(),
    )

    if args.out:
        Path(args.out).write_text(report_md, encoding="utf-8")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(report_md)
    return 0


def cmd_watchlist(args: argparse.Namespace) -> int:
    settings = load_settings()
    watchlist = Watchlist.load(settings.watchlist_path)
    for group, tickers in watchlist.groups.items():
        print(f"{group}: {', '.join(tickers) if tickers else '(empty)'}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    settings = load_settings()
    watchlist = Watchlist.load(settings.watchlist_path)
    added = watchlist.add(args.ticker, args.group)
    if added:
        watchlist.save()
        print(f"Added {args.ticker.upper()} to '{args.group}'.")
    else:
        print(f"{args.ticker.upper()} is already in '{args.group}'.")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    settings = load_settings()
    watchlist = Watchlist.load(settings.watchlist_path)
    removed = watchlist.remove(args.ticker)
    if removed:
        watchlist.save()
        print(f"Removed {args.ticker.upper()} from the watchlist.")
    else:
        print(f"{args.ticker.upper()} was not found in the watchlist.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="analyst", description="AI infrastructure stock analyst agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser("report", help="Generate a markdown analysis report")
    report_parser.add_argument("--group", choices=["core", "emerging", "all"], default="all")
    report_parser.add_argument("--tickers", help="Comma-separated ticker override, e.g. NVDA,AMD")
    report_parser.add_argument("--out", help="Write report to this file instead of stdout")
    report_parser.add_argument("--no-llm", action="store_true", help="Skip AI narrative synthesis")
    report_parser.set_defaults(func=cmd_report)

    watchlist_parser = subparsers.add_parser("watchlist", help="List tracked tickers")
    watchlist_parser.set_defaults(func=cmd_watchlist)

    add_parser = subparsers.add_parser("add", help="Add a ticker to the watchlist")
    add_parser.add_argument("ticker")
    add_parser.add_argument("--group", choices=["core", "emerging"], default="emerging")
    add_parser.set_defaults(func=cmd_add)

    remove_parser = subparsers.add_parser("remove", help="Remove a ticker from the watchlist")
    remove_parser.add_argument("ticker")
    remove_parser.set_defaults(func=cmd_remove)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
