from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .model import MorningReport


def _record_key(record: dict[str, Any]) -> tuple[str, ...]:
    if record.get("group") == "taiwan_indices":
        aliases = {
            "^TWII": "weighted", "TWSE.php": "weighted", "加權": "weighted", "台灣加權": "weighted",
            "^TWOII": "otc", "TWOTCI.php": "otc", "櫃買": "otc", "台灣櫃買": "otc",
        }
        index = aliases.get(str(record.get("symbol") or "")) or aliases.get(str(record.get("label") or ""))
        if index:
            return ("market", "taiwan_indices", index)
    source = str(record.get("source") or "")
    if record.get("symbol"):
        return (source, "symbol", str(record["symbol"]))
    if record.get("link"):
        return (source, "link", str(record["link"]))
    if record.get("title"):
        return (source, "title", str(record["title"]))
    return (
        source,
        str(record.get("kind") or ""),
        str(record.get("group") or ""),
        str(record.get("label") or ""),
        str(record.get("date") or ""),
    )


def _recency(record: dict[str, Any], report_date: str) -> float | None:
    market_time = record.get("market_time")
    if isinstance(market_time, (int, float)) and not isinstance(market_time, bool):
        return float(market_time)
    for field in ("published_at", "updated_at", "date"):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            continue
        normalized = value.replace("Z", "+00:00")
        try:
            if field != "date":
                return datetime.fromisoformat(normalized).timestamp()
            if len(value) == 5 and value[2] == "/":
                value = f"{report_date[:4]}/{value}"
            elif len(value) == 9 and value[3] == "/":
                year, rest = value.split("/", 1)
                value = f"{int(year) + 1911}/{rest}"
            return datetime.fromisoformat(value.replace("/", "-")).timestamp()
        except ValueError:
            continue
    return None


def merge_records(
    current: list[dict[str, Any]], previous: list[dict[str, Any]], report_date: str
) -> list[dict[str, Any]]:
    old_by_key = {_record_key(item): item for item in previous}
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for item in current:
        key = _record_key(item)
        seen.add(key)
        old = old_by_key.get(key)
        if old is None:
            merged.append(item)
            continue
        new_time = _recency(item, report_date)
        old_time = _recency(old, report_date)
        if new_time is not None and old_time is not None and new_time < old_time:
            merged.append(old)
            continue
        combined = dict(old)
        combined.update(value for value in item.items() if value[1] not in (None, "", [], {}))
        merged.append(combined)
    merged.extend(item for item in previous if _record_key(item) not in seen)
    return merged


def merge_same_day_report(report: MorningReport, previous_path: Path) -> None:
    if not previous_path.exists():
        return
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    if previous.get("report_date") != report.report_date:
        return
    for field in ("markets", "taiwan_market", "chips", "news"):
        old_records = previous.get(field, [])
        if isinstance(old_records, list):
            current = getattr(report, field)
            setattr(report, field, merge_records(current, old_records, report.report_date))
    report.news.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
