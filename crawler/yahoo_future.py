from __future__ import annotations

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

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def collect(self) -> CollectorResult:
        try:
            record = self._parse(self.client.get_text(self.url))
        except (OSError, ValueError) as exc:
            return CollectorResult(self.name, error=f"{type(exc).__name__}: Yahoo 台指期讀取失敗")
        return CollectorResult(self.name, [record])

    @classmethod
    def _parse(cls, page: str) -> dict[str, object]:
        parser = _VisibleText()
        parser.feed(page)
        values = parser.values

        def after(label: str) -> str:
            start = values.index("台指期近一即時行情")
            index = values.index(label, start)
            return values[index + 1]

        price = cls._number(after("成交"))
        change = cls._number(after("漲跌"))
        percent = cls._number(after("漲跌幅").replace("%", ""))
        if price is None or change is None or percent is None:
            raise ValueError("missing Yahoo future quote")
        return {
            "kind": "market", "group": "taifex", "symbol": "WTX&",
            "label": "台指期夜盤", "price": price, "change": change,
            "change_percent": percent, "source": cls.name,
        }

    @staticmethod
    def _number(value: str) -> float | None:
        try:
            return float(value.replace(",", "").strip("()"))
        except ValueError:
            return None
