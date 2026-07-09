"""Loads and edits the tracked-stock watchlist (config/watchlist.yaml)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VALID_GROUPS = ("core", "emerging")

_GROUP_HEADER_RE = re.compile(r"^([A-Za-z_]+):\s*$")
_TICKER_LINE_RE = re.compile(r"^\s*-\s*([A-Za-z][A-Za-z0-9.\-]*)\s*(#.*)?$")


@dataclass
class Watchlist:
    path: Path
    groups: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Watchlist":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        groups = {g: [t.upper() for t in raw.get(g, [])] for g in VALID_GROUPS}
        return cls(path=path, groups=groups)

    def save(self) -> None:
        """Rewrites only the ticker lines that changed, so hand-written
        comments and formatting on every untouched line survive."""
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        header_idx: dict[str, int] = {}
        order: list[str] = []
        for i, line in enumerate(lines):
            m = _GROUP_HEADER_RE.match(line)
            if m and m.group(1) in VALID_GROUPS:
                header_idx[m.group(1)] = i
                order.append(m.group(1))

        # Process bottom-to-top so earlier edits don't shift later offsets.
        for group in sorted(order, key=lambda g: header_idx[g], reverse=True):
            start = header_idx[group]
            idx = order.index(group)
            end = header_idx[order[idx + 1]] if idx + 1 < len(order) else len(lines)
            desired = self.groups.get(group, [])

            kept = []
            existing = []
            for line in lines[start + 1 : end]:
                m = _TICKER_LINE_RE.match(line)
                if m:
                    ticker = m.group(1).upper()
                    if ticker in desired:
                        kept.append(line)
                        existing.append(ticker)
                    # else: ticker was removed -> drop the line
                else:
                    kept.append(line)  # comment/blank line, keep as-is

            for ticker in desired:
                if ticker not in existing:
                    kept.append(f"  - {ticker}\n")

            lines[start + 1 : end] = kept

        with open(self.path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def all_tickers(self) -> list[str]:
        seen: list[str] = []
        for group in VALID_GROUPS:
            for ticker in self.groups.get(group, []):
                if ticker not in seen:
                    seen.append(ticker)
        return seen

    def tickers(self, group: str | None) -> list[str]:
        if group is None or group == "all":
            return self.all_tickers()
        if group not in VALID_GROUPS:
            raise ValueError(f"Unknown group '{group}', expected one of {VALID_GROUPS}")
        return list(self.groups.get(group, []))

    def group_of(self, ticker: str) -> str | None:
        ticker = ticker.upper()
        for group in VALID_GROUPS:
            if ticker in self.groups.get(group, []):
                return group
        return None

    def add(self, ticker: str, group: str) -> bool:
        ticker = ticker.upper()
        if group not in VALID_GROUPS:
            raise ValueError(f"Unknown group '{group}', expected one of {VALID_GROUPS}")
        self.groups.setdefault(group, [])
        if ticker in self.groups[group]:
            return False
        self.groups[group].append(ticker)
        return True

    def remove(self, ticker: str) -> bool:
        ticker = ticker.upper()
        removed = False
        for group in VALID_GROUPS:
            if ticker in self.groups.get(group, []):
                self.groups[group].remove(ticker)
                removed = True
        return removed
