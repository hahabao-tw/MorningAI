from __future__ import annotations

import base64
import re
from datetime import date

from .base import Collector, CollectorResult
from .http import HttpClient


class StockQCollector(Collector):
    name = "stockq"
    url = "https://www.stockq.org/"
    targets = (("TWSE.php", "台灣加權"), ("TWOTCI.php", "台灣櫃買"))

    def __init__(self, client: HttpClient, today: date, before_open: bool = True) -> None:
        self.client = client
        self.today = today
        self.before_open = before_open

    def collect(self) -> CollectorResult:
        try:
            records = self._parse(self.client.get_text(self.url))
        except (OSError, ValueError) as exc:
            return CollectorResult(self.name, error=f"{type(exc).__name__}: StockQ 讀取失敗")
        current = self.today.strftime("%m/%d")
        records = [record for record in records if record.get("date") != current]
        if not self.before_open:
            records = []
        return CollectorResult(self.name, records) if len(records) == 2 else CollectorResult(self.name, records, "尚無前一交易日完整指數")

    @classmethod
    def _parse(cls, page: str) -> list[dict[str, object]]:
        rows = re.findall(r"<tr[^>]*>.*?</tr>", page, flags=re.IGNORECASE | re.DOTALL)
        records: list[dict[str, object]] = []
        for path, label in cls.targets:
            row = next((item for item in rows if path in item), "")
            payloads = re.findall(r"data-sq=[\"']([^\"']+)[\"']", row, flags=re.IGNORECASE)
            scripts = re.findall(r"<script[^>]*>(.*?)</script>", row, flags=re.IGNORECASE | re.DOTALL)
            if len(payloads) >= 3:
                values = [float(cls._decode_payload(payload)) for payload in payloads[:3]]
            elif len(scripts) >= 3:
                values = [float(cls._decode(script)) for script in scripts[:3]]
            else:
                continue
            dates = re.findall(r"\b\d{2}/\d{2}\b", row)
            records.append({
                "kind": "market", "group": "taiwan_indices", "symbol": path,
                "label": label, "price": values[0], "change": values[1],
                "change_percent": values[2], "source": cls.name,
                "date": dates[-1] if dates else None,
            })
        return records

    @staticmethod
    def _decode(script: str) -> str:
        match = re.search(r"var a=\[([^]]+)\],z=(\d+)", script)
        if not match:
            raise ValueError("unexpected StockQ value format")
        parts = re.findall(r"'([^']*)'", match.group(1))
        return StockQCollector._decode_parts(parts, int(match.group(2)))

    @staticmethod
    def _decode_payload(payload: str) -> str:
        try:
            fields = base64.b64decode(payload, validate=True).decode("ascii").split("|")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("unexpected StockQ data-sq format") from exc
        if len(fields) != 6 or not fields[0].isdigit():
            raise ValueError("unexpected StockQ data-sq format")
        return StockQCollector._decode_parts(fields[1:], int(fields[0]))

    @staticmethod
    def _decode_parts(encoded_parts: list[str], state: int) -> str:
        if len(encoded_parts) != 5:
            raise ValueError("unexpected StockQ value parts")
        parts = list(encoded_parts)

        def random_value() -> float:
            nonlocal state
            state = state * 48271 % 2147483647
            return state / 2147483647

        random_value(); random_value()
        order = [0, 1, 2]
        for index in range(2, 0, -1):
            swap = int(random_value() * (index + 1))
            order[index], order[swap] = order[swap], order[index]
        random_value(); first = int(random_value() * 4)
        random_value(); second = int(random_value() * 5)
        parts.pop(second); parts.pop(first)
        output = ["", "", ""]
        for index in range(3):
            output[order[index]] = parts[index]
        return "".join(output)
