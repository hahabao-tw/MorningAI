from __future__ import annotations

import re
from html.parser import HTMLParser

from .base import Collector, CollectorResult
from .http import HttpClient


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden = 0
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not self.hidden and value:
            self.values.append(value)


class YahooFutureCollector(Collector):
    name = "yahoo_future"
    url = "https://tw.stock.yahoo.com/quote/WTX%26"
    quotes = (
        ("https://tw.stock.yahoo.com/quote/WTX%26", "台指期近一即時行情", "WTX&", "台指期夜盤"),
        ("https://tw.stock.yahoo.com/quote/WCDF%26", "台積電期貨近一即時行情", "WCDF&", "台積電期貨夜盤"),
    )

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def collect(self) -> CollectorResult:
        records: list[dict[str, object]] = []
        errors: list[str] = []
        for url, title, symbol, label in self.quotes:
            try:
                records.append(self._parse(self.client.get_text(url), title, symbol, label))
            except (OSError, ValueError) as exc:
                errors.append(f"{symbol}: {type(exc).__name__}")
        return CollectorResult(self.name, records, "; ".join(errors) or None)

    @classmethod
    def _parse(
        cls,
        page: str,
        title: str = "台指期近一即時行情",
        symbol: str = "WTX&",
        label: str = "台指期夜盤",
    ) -> dict[str, object]:
        parser = _VisibleText()
        parser.feed(page)
        values = parser.values
        update = next((value for value in values if re.search(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2} 更新", value)), "")
        if update and not update.startswith("收盤"):
            raise ValueError("Yahoo quote is not closed")
        time_match = re.search(r" (\d{2}):(\d{2}) 更新", update)
        if time_match and 5 <= int(time_match.group(1)) < 15:
            raise ValueError("Yahoo quote has entered the regular session")

        def after(label: str) -> str:
            start = values.index(title)
            index = values.index(label, start)
            return values[index + 1]

        price = cls._number(after("成交"))
        change = cls._number(after("漲跌"))
        percent = cls._number(after("漲跌幅").replace("%", ""))
        if price is None or change is None or percent is None:
            raise ValueError("missing Yahoo future quote")
        return {
            "kind": "market", "group": "taifex", "symbol": symbol,
            "label": label, "price": price, "change": change,
            "change_percent": percent, "source": cls.name,
        }

    @staticmethod
    def _number(value: str) -> float | None:
        try:
            return float(value.replace(",", "").strip("()"))
        except ValueError:
            return None
