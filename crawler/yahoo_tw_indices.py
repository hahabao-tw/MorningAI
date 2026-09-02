from __future__ import annotations

import re
import urllib.parse
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .base import Collector, CollectorResult
from .http import HttpClient
from .yahoo_chart import chart_series, chart_url


class YahooTwIndexCollector(Collector):
    name = "yahoo_tw_indices"
    base_url = "https://tw.stock.yahoo.com/quote/"
    targets = (("^TWII", "加權"), ("^TWOII", "櫃買"))

    def __init__(self, client: HttpClient, today: date) -> None:
        self.client = client
        self.today = today

    def collect(self) -> CollectorResult:
        records: list[dict[str, object]] = []
        errors: list[str] = []
        current = self.today.strftime("%m/%d")
        for symbol, label in self.targets:
            try:
                record = self._parse_chart(
                    self.client.get_json(chart_url(symbol, "d")), symbol, label, self.today
                )
                records.append(record)
            except (OSError, TypeError, ValueError) as exc:
                try:
                    url = self.base_url + urllib.parse.quote(symbol, safe="")
                    record = self._parse_page(self.client.get_text(url), symbol, label)
                    if record["date"] == current:
                        raise ValueError("current trading day quote")
                    records.append(record)
                except (OSError, TypeError, ValueError) as fallback_exc:
                    errors.append(
                        f"{symbol}: chart={type(exc).__name__}, page={type(fallback_exc).__name__}"
                    )
        error = "; ".join(errors) if errors else None
        if len(records) != len(self.targets) and error is None:
            error = "Yahoo 台股指數資料不完整"
        return CollectorResult(self.name, records, error)

    @classmethod
    def _parse_chart(
        cls, payload: object, symbol: str, label: str, today: date
    ) -> dict[str, object]:
        completed = [(stamp, close) for stamp, close in chart_series(payload, symbol) if stamp.date() < today]
        if len(completed) < 2:
            raise ValueError("Yahoo chart has fewer than two completed trading days")
        timestamp, price = completed[-1]
        previous = completed[-2][1]
        if previous == 0:
            raise ValueError("zero previous close")
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
            "date": timestamp.strftime("%m/%d"),
            "source": cls.name,
        }

    @classmethod
    def _parse_page(cls, page: str, symbol: str, label: str) -> dict[str, object]:
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
        return float(value.replace(",", ""))
