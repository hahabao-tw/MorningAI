from __future__ import annotations

import math
import re
import urllib.parse
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .base import Collector, CollectorResult
from .http import HttpClient


class YahooTwIndexCollector(Collector):
    name = "yahoo_tw_indices"
    base_url = "https://tw.stock.yahoo.com/quote/"
    targets = (("^TWII", "加權"), ("^TWOII", "櫃買"))

    def __init__(self, client: HttpClient, today: date, before_open: bool = True) -> None:
        self.client = client
        self.today = today
        self.before_open = before_open

    def collect(self) -> CollectorResult:
        if not self.before_open:
            return CollectorResult(self.name, error="台股開盤後不更新昨日指數")
        records: list[dict[str, object]] = []
        errors: list[str] = []
        current = self.today.strftime("%m/%d")
        for symbol, label in self.targets:
            try:
                url = self.base_url + urllib.parse.quote(symbol, safe="")
                record = self._parse(self.client.get_text(url), symbol, label)
                if record["date"] == current:
                    raise ValueError("current trading day quote")
                records.append(record)
            except (OSError, TypeError, ValueError) as exc:
                errors.append(f"{symbol}: {type(exc).__name__}")
        error = "; ".join(errors) if errors else None
        if len(records) != len(self.targets) and error is None:
            error = "Yahoo 台股指數資料不完整"
        return CollectorResult(self.name, records, error)

    @classmethod
    def _parse(cls, page: str, symbol: str, label: str) -> dict[str, object]:
        marker = f'"symbol":"{symbol}"'
        quote_pattern = re.compile(
            r'"price":\{"raw":"(?P<price>[^"}]*)".*?'
            r'"regularMarketPreviousClose":\{"raw":"(?P<previous>[^"}]*)".*?'
            r'"regularMarketTime":"(?P<market_time>[^"]+)"',
            flags=re.DOTALL,
        )
        for occurrence in re.finditer(re.escape(marker), page):
            window = page[max(0, occurrence.start() - 2_000):occurrence.end()]
            matches = list(quote_pattern.finditer(window))
            if not matches:
                continue
            match = matches[-1]
            price = cls._number(match.group("price"))
            previous = cls._number(match.group("previous"))
            if previous == 0:
                raise ValueError("zero previous close")
            timestamp = datetime.fromisoformat(match.group("market_time").replace("Z", "+00:00"))
            change = price - previous
            return {
                "kind": "market",
                "group": "taiwan_indices",
                "symbol": symbol,
                "label": label,
                "price": price,
                "change": change,
                "change_percent": change / previous * 100,
                "currency": "TWD",
                "market_time": int(timestamp.timestamp()),
                "date": timestamp.astimezone(ZoneInfo("Asia/Taipei")).strftime("%m/%d"),
                "source": cls.name,
            }
        raise ValueError("unexpected Yahoo Taiwan index format")

    @staticmethod
    def _number(value: str) -> float:
        number = float(value.replace(",", ""))
        if not math.isfinite(number):
            raise ValueError("non-finite Yahoo Taiwan index value")
        return number
