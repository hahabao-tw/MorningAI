from __future__ import annotations

from datetime import date, timedelta

from .base import Collector, CollectorResult
from .http import HttpClient


class TwseCollector(Collector):
    """TWSE public open-data collector for index and institutional totals."""

    name = "twse"

    def __init__(self, client: HttpClient, today: date) -> None:
        self.client = client
        self.today = today

    def collect(self) -> CollectorResult:
        for offset in range(1, 15):
            target = self.today - timedelta(days=offset)
            try:
                record = self._fetch_day(target)
                if record:
                    try:
                        stamp = self._roc_date_to_stamp(str(record["date"]))
                        record["institutional"] = self._fetch_institutional(stamp)
                        return CollectorResult(self.name, [record])
                    except (KeyError, IndexError, TypeError, ValueError, OSError):
                        record["institutional"] = []
                        return CollectorResult(self.name, [record], "法人資料無法讀取")
            except (KeyError, IndexError, TypeError, ValueError, OSError):
                continue
        return CollectorResult(self.name, error="近 14 日無可用交易資料")

    def _fetch_day(self, target: date) -> dict[str, object] | None:
        stamp = target.strftime("%Y%m%d")
        url = f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={stamp}&response=json"
        payload = self.client.get_json(url)
        rows = payload.get("data") or []
        if not rows:
            return None
        row = rows[-1]
        return {
            "kind": "twse_summary",
            "date": row[0],
            "volume": self._integer(row[1]),
            "turnover": self._integer(row[2]),
            "transactions": self._integer(row[3]),
            "index": self._float(row[4]),
            "change": self._signed_float(row[5]),
            "source": self.name,
        }

    def _fetch_institutional(self, stamp: str) -> list[dict[str, object]]:
        url = f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?date={stamp}&response=json"
        payload = self.client.get_json(url)
        records: list[dict[str, object]] = []
        for row in payload.get("data") or []:
            if len(row) < 4:
                continue
            records.append({"name": str(row[0]), "buy": self._integer(row[1]), "sell": self._integer(row[2]), "net": self._integer(row[3])})
        if not records:
            raise ValueError("empty institutional data")
        return records

    @staticmethod
    def _roc_date_to_stamp(value: str) -> str:
        parts = value.strip().split("/")
        if len(parts) != 3:
            raise ValueError("unexpected ROC date")
        year, month, day = (int(part) for part in parts)
        return f"{year + 1911:04d}{month:02d}{day:02d}"

    @staticmethod
    def _integer(value: object) -> int | None:
        try:
            return int(str(value).replace(",", ""))
        except ValueError:
            return None

    @staticmethod
    def _float(value: object) -> float | None:
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            return None

    @classmethod
    def _signed_float(cls, value: object) -> float | None:
        cleaned = str(value).replace("X", "").replace(" ", "")
        return cls._float(cleaned)
