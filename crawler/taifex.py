from __future__ import annotations

import csv
import io

from .base import Collector, CollectorResult
from .http import HttpClient


class TaifexCollector(Collector):
    """Latest TX after-hours data from the official TAIFEX open-data CSV."""

    name = "taifex"
    url = "https://www.taifex.com.tw/data_gov/taifex_open_data.asp?data_name=DailyMarketReportFut"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def collect(self) -> CollectorResult:
        try:
            records = self._parse(self.client.get_text(self.url))
        except (OSError, UnicodeError, csv.Error, ValueError) as exc:
            return CollectorResult(self.name, error=f"{type(exc).__name__}: 夜盤資料讀取失敗")
        return CollectorResult(self.name, records) if records else CollectorResult(self.name, error="查無台指期夜盤資料")

    @classmethod
    def _parse(cls, text: str) -> list[dict[str, object]]:
        rows = []
        for raw in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
            row = {str(key).strip(): str(value).strip() for key, value in raw.items() if key is not None}
            contract = cls._field(row, "契約代號", "契約", "Contract")
            session = cls._field(row, "交易時段", "Trading Session")
            month = cls._field(row, "到期月份(週別)", "到期月份（週別）", "Contract Month(Week)")
            if contract == "TX" and ("盤後" in session or "after" in session.lower()) and month.isdigit() and len(month) == 6:
                rows.append(row)
        if not rows:
            return []
        latest_date = max(cls._field(row, "日期", "Date") for row in rows)
        latest = [row for row in rows if cls._field(row, "日期", "Date") == latest_date]
        row = min(latest, key=lambda item: cls._field(item, "到期月份(週別)", "到期月份（週別）", "Contract Month(Week)"))
        return [{
            "kind": "market",
            "group": "taifex",
            "symbol": "TX",
            "label": "台指期夜盤",
            "price": cls._number(cls._field(row, "最後成交價", "Last")),
            "change": cls._number(cls._field(row, "漲跌價", "Change")),
            "change_percent": cls._number(cls._field(row, "漲跌%", "%")),
            "volume": cls._integer(cls._field(row, "合計成交量", "Volume")),
            "contract_month": cls._field(row, "到期月份(週別)", "到期月份（週別）", "Contract Month(Week)"),
            "date": latest_date,
            "source": cls.name,
        }]

    @staticmethod
    def _field(row: dict[str, str], *names: str) -> str:
        for name in names:
            if name in row:
                return row[name]
        return ""

    @staticmethod
    def _number(value: str) -> float | None:
        falling = "▼" in value
        cleaned = value.replace(",", "").replace("%", "").replace("▲", "").replace("▼", "").strip()
        if falling and cleaned and not cleaned.startswith("-"):
            cleaned = "-" + cleaned
        if cleaned in {"", "-", "--"}:
            return None
        return float(cleaned)

    @staticmethod
    def _integer(value: str) -> int | None:
        number = TaifexCollector._number(value)
        return None if number is None else int(number)
