from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from .base import Collector, CollectorResult
from .http import HttpClient


class RssCollector(Collector):
    name = "rss"

    def __init__(self, client: HttpClient, feeds: list[str], max_items: int = 5) -> None:
        self.client = client
        self.feeds = feeds
        self.max_items = max_items

    def collect(self) -> CollectorResult:
        records: list[dict[str, object]] = []
        failures = 0
        for feed in self.feeds:
            try:
                records.extend(self._parse(self.client.get_bytes(feed), feed)[: self.max_items])
            except (ET.ParseError, OSError, UnicodeError, ValueError):
                failures += 1
        error = "所有 RSS 來源皆無法讀取" if failures == len(self.feeds) and self.feeds else None
        return CollectorResult(self.name, records, error)

    def _parse(self, raw: bytes, feed: str) -> list[dict[str, object]]:
        root = ET.fromstring(raw)
        items = root.findall(".//item")
        records: list[dict[str, object]] = []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title:
                continue
            published = self._date(item.findtext("pubDate"))
            records.append({"kind": "news", "title": title, "link": link, "published_at": published, "feed": feed, "source": self.name})
        return records

    @staticmethod
    def _date(value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return None

