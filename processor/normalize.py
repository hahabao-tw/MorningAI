from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from crawler.base import CollectorResult

from .model import MorningReport


def build_report(results: list[CollectorResult], now: datetime, timezone_name: str) -> MorningReport:
    local_now = now.astimezone(ZoneInfo(timezone_name))
    report = MorningReport(1, local_now.date().isoformat(), local_now.isoformat(timespec="seconds"), timezone_name)
    seen_news: set[tuple[str, str]] = set()
    for result in results:
        report.source_status.append({"source": result.source, "ok": result.ok, "records": len(result.records), "error": result.error})
        for record in result.records:
            kind = record.get("kind")
            if kind == "market":
                report.markets.append(record)
            elif kind == "twse_summary":
                report.taiwan_market.append(record)
            elif kind == "chips":
                report.chips.append(record)
            elif kind == "news":
                key = (str(record.get("title", "")), str(record.get("link", "")))
                if key not in seen_news:
                    seen_news.add(key)
                    report.news.append(record)
    report.news.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    return report
