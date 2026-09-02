from __future__ import annotations

import json
import math
import urllib.parse
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


BASE_URL = (
    "https://tw.stock.yahoo.com/_td-stock/api/resource/"
    "FinanceChartService.ApacLibraCharts"
)
TAIPEI = ZoneInfo("Asia/Taipei")


def chart_url(symbol: str, period: str) -> str:
    symbols = urllib.parse.quote(json.dumps([symbol], separators=(",", ":")))
    return f"{BASE_URL};period={period};symbols={symbols}?region=TW&lang=zh-Hant-TW"


def chart_series(payload: Any, symbol: str) -> list[tuple[datetime, float]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list) or not data:
        raise ValueError(f"{symbol}: missing Yahoo chart data")
    item = next((entry for entry in data if entry.get("symbol") == symbol), data[0])
    chart = item.get("chart")
    if not isinstance(chart, dict):
        raise ValueError(f"{symbol}: missing Yahoo chart")
    timestamps = chart.get("timestamp")
    indicators = chart.get("indicators")
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    quote = quotes[0] if isinstance(quotes, list) and quotes else None
    closes = quote.get("close") if isinstance(quote, dict) else None
    if not isinstance(timestamps, list) or not isinstance(closes, list):
        raise ValueError(f"{symbol}: malformed Yahoo chart")
    if len(timestamps) != len(closes):
        raise ValueError(f"{symbol}: mismatched Yahoo chart")

    rows: list[tuple[datetime, float]] = []
    for timestamp, close in zip(timestamps, closes):
        if timestamp is None or close is None:
            continue
        value = float(close)
        if not math.isfinite(value):
            continue
        rows.append((datetime.fromtimestamp(float(timestamp), TAIPEI), value))
    if not rows:
        raise ValueError(f"{symbol}: empty Yahoo chart")
    return rows
