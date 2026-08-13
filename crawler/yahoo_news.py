from __future__ import annotations

import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from .base import Collector, CollectorResult
from .http import HttpClient


class _HeadlineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_article = 0
        self.heading_depth = 0
        self.link = ""
        self.text: list[str] = []
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "article":
            self.in_article += 1
        if self.in_article and tag in {"h2", "h3"}:
            self.heading_depth += 1
            self.text = []
        if self.heading_depth and tag == "a":
            self.link = attributes.get("href") or ""

    def handle_data(self, data: str) -> None:
        if self.heading_depth:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h2", "h3"} and self.heading_depth:
            title = " ".join("".join(self.text).split())
            if title and self.link:
                self.items.append((title, self.link))
            self.heading_depth -= 1
            self.text = []
            self.link = ""
        if tag == "article" and self.in_article:
            self.in_article -= 1


class YahooHeadlineCollector(Collector):
    name = "yahoo_news"

    def __init__(self, client: HttpClient, international_url: str, domestic_url: str,
                 international_items: int = 4, domestic_items: int = 4,
                 translate_international: bool = True) -> None:
        self.client = client
        self.sources = (("international", international_url, international_items),
                        ("domestic", domestic_url, domestic_items))
        self.translate_international = translate_international

    def collect(self) -> CollectorResult:
        records: list[dict[str, object]] = []
        errors: list[str] = []
        for category, url, limit in self.sources:
            try:
                page = self.client.get_text(url)
                items = self._rss_items(page, limit * 5) if "<rss" in page[:500].lower() else [(*item, "") for item in self._headlines(page, url, limit * 5)]
                if category == "international":
                    items = [item for item in items if self._financial_headline(item[0])]
                items = items[:limit]
                if not items:
                    raise ValueError("no headlines")
                for title, link, description in items:
                    original = title
                    should_translate = category == "international" and self.translate_international and self._mostly_english(title)
                    if should_translate:
                        title = self._translate(title)
                    summary_text = self._clean_description(description) or title
                    if should_translate and summary_text != title:
                        summary_text = self._translate(summary_text)
                    records.append({
                        "kind": "news", "category": category, "title": title,
                        "original_title": original if title != original else None,
                        "summary": self._summary(summary_text), "link": link,
                        "published_at": None, "source": self.name,
                    })
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
                errors.append(f"{category}: {type(exc).__name__}")
        return CollectorResult(self.name, records, "; ".join(errors) if errors else None)

    @staticmethod
    def _rss_items(page: str, limit: int) -> list[tuple[str, str, str]]:
        root = ET.fromstring(page)
        records: list[tuple[str, str, str]] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = item.findtext("description") or ""
            if title and link:
                records.append((title, link, description))
            if len(records) >= limit:
                break
        return records

    @staticmethod
    def _clean_description(value: str) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", html.unescape(value))
        return " ".join(without_tags.split())

    @staticmethod
    def _mostly_english(value: str) -> bool:
        letters = sum(character.isascii() and character.isalpha() for character in value)
        return letters >= max(8, len(value) // 2)

    @staticmethod
    def _financial_headline(value: str) -> bool:
        keywords = (
            "市場", "股", "債", "匯", "油價", "黃金", "經濟", "關稅", "聯準會", "央行",
            "通膨", "財報", "投資", "晶片", "科技", "美元", "比特幣", "特斯拉", "輝達",
            "銀行", "貿易", "market", "stock", "bond", "oil", "gold", "economy", "fed",
            "inflation", "earnings", "invest", "chip", "dollar", "bitcoin", "trade",
        )
        lowered = value.casefold()
        return any(keyword.casefold() in lowered for keyword in keywords)

    @staticmethod
    def _headlines(page: str, base_url: str, limit: int) -> list[tuple[str, str]]:
        parser = _HeadlineParser()
        parser.feed(page)
        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        for title, link in parser.items:
            normalized = html.unescape(title).strip()
            absolute = urllib.parse.urljoin(base_url, link)
            if normalized in seen or not absolute.startswith("https://"):
                continue
            seen.add(normalized)
            found.append((normalized, absolute))
            if len(found) >= limit:
                break
        return found

    def _translate(self, text: str) -> str:
        query = urllib.parse.urlencode({
            "client": "gtx", "sl": "en", "tl": "zh-TW", "dt": "t", "q": text,
        })
        try:
            payload = self.client.get_json("https://translate.googleapis.com/translate_a/single?" + query)
            translated = "".join(str(part[0]) for part in payload[0] if part and part[0]).strip()
            return translated or text
        except (OSError, TypeError, IndexError, KeyError, ValueError, json.JSONDecodeError):
            return text

    @staticmethod
    def _summary(title: str) -> str:
        clean = re.sub(r"\s+", " ", title).strip().rstrip("。.!！")
        if len(clean) > 72:
            clean = clean[:72].rstrip() + "…"
        return f"重點：{clean}。"
