from __future__ import annotations

import math
import urllib.parse

from .base import Collector, CollectorResult
from .http import HttpClient


class YahooMarketCollector(Collector):
    name = "yahoo"

    def __init__(self, client: HttpClient, symbols: dict[str, str]) -> None:
        self.client = client
        self.symbols = symbols

    def collect(self) -> CollectorResult:
        records: list[dict[str, object]] = []
        errors: list[str] = []
        for symbol, label in self.symbols.items():
            try:
                encoded = urllib.parse.quote(symbol, safe="")
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=1d&interval=1d"
                payload = self.client.get_json(url)
                result = payload["chart"]["result"][0]
                meta = result["meta"]
                price = self._number(meta.get("regularMarketPrice"))
                previous = self._number(meta.get("chartPreviousClose") or meta.get("previousClose"))
                change = None if price is None or previous in (None, 0) else price - previous
                percent = None if change is None or previous is None else change / previous * 100
                records.append({
                    "kind": "market",
                    "group": self._group(symbol),
                    "symbol": symbol,
                    "label": label,
                    "price": price,
                    "change": change,
                    "change_percent": percent,
                    "currency": meta.get("currency"),
                    "market_time": meta.get("regularMarketTime"),
                    "source": self.name,
                })
            except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
                errors.append(f"{symbol}: {type(exc).__name__}")
        error = "; ".join(errors) if errors else None
        return CollectorResult(self.name, records, error)

    @staticmethod
    def _group(symbol: str) -> str:
        if symbol.startswith("^") or symbol in {"NQ=F", "ES=F"}:
            return "indices"
        if symbol in {"TSM", "UMC", "ASX"}:
            return "adr"
        if symbol in {"GC=F", "CL=F", "BZ=F"}:
            return "commodities"
        return "fx"

    @staticmethod
    def _number(value: object) -> float | None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
