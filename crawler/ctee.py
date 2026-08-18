from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime

from .base import Collector, CollectorResult
from .http import HttpClient


class CteePremarketCollector(Collector):
    name = "ctee_google_news"

    def __init__(self, client: HttpClient, report_date: date, search_url: str) -> None:
        self.client = client
        self.report_date = report_date
        self.search_url = search_url

    def collect(self) -> CollectorResult:
        try:
            records = self._parse(self.client.get_bytes(self.search_url), self.report_date)
            return CollectorResult(self.name, records)
        except (ET.ParseError, OSError, TypeError, ValueError) as exc:
            return CollectorResult(self.name, error=type(exc).__name__)

    @classmethod
    def _parse(cls, payload: bytes, report_date: date) -> list[dict[str, object]]:
        root = ET.fromstring(payload)
        records: list[dict[str, object]] = []
        seen: set[str] = set()
        for item in root.findall("./channel/item"):
            raw_title = (item.findtext("title") or "").strip()
            match = re.match(r"^(\d{1,2})[／/](\d{1,2})盤前[｜|]", raw_title)
            if not match or (int(match.group(1)), int(match.group(2))) != (report_date.month, report_date.day):
                continue
            source = (item.findtext("source") or "").strip()
            if source and source != "工商時報":
                continue
            title = re.sub(r"\s*-\s*(?:證券\s*-\s*)?工商時報\s*$", "", raw_title).strip()
            link = (item.findtext("link") or "").strip()
            if not title or not link or title in seen:
                continue
            published = item.findtext("pubDate")
            published_at = parsedate_to_datetime(published).isoformat() if published else None
            records.append({
                "kind": "ctee_premarket",
                "title": title,
                "link": link,
                "published_at": published_at,
                "source": cls.name,
            })
            seen.add(title)
        records.sort(key=lambda record: str(record.get("published_at") or ""), reverse=True)
        return records


def google_news_search_url() -> str:
    query = urllib.parse.quote("site:ctee.com.tw/news 盤前")
    return f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
