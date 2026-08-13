from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from crawler.base import CollectorResult
from crawler.twse import TwseCollector
from crawler.yahoo import YahooMarketCollector
from crawler.yahoo_news import YahooHeadlineCollector
from processor.export import write_report
from processor.markdown import render_markdown
from processor.normalize import build_report
from processor.site import build_site


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 12, 22, 30, tzinfo=timezone.utc)

    def test_partial_failure_still_builds_report(self) -> None:
        results = [
            CollectorResult("market", [{"kind": "market", "group": "indices", "label": "S&P 500", "price": 6000, "change": 10, "change_percent": 0.17}]),
            CollectorResult("news", error="timeout"),
        ]
        report = build_report(results, self.now, "Asia/Taipei")
        markdown = render_markdown(report, "MorningAI")
        self.assertEqual(report.report_date, "2026-08-13")
        self.assertIn("S&P 500", markdown)
        self.assertIn("資料缺漏", markdown)
        self.assertIn("timeout", markdown)

    def test_duplicate_news_is_removed(self) -> None:
        item = {"kind": "news", "title": "Same", "link": "https://example.com", "published_at": None}
        report = build_report([CollectorResult("a", [item]), CollectorResult("b", [item])], self.now, "Asia/Taipei")
        self.assertEqual(len(report.news), 1)

    def test_partial_source_failure_is_visible(self) -> None:
        result = CollectorResult("market", [{"kind": "market", "group": "indices", "label": "NASDAQ", "price": 1, "change": 0, "change_percent": 0}], "one symbol failed")
        markdown = render_markdown(build_report([result], self.now, "Asia/Taipei"), "MorningAI")
        self.assertIn("部分失敗", markdown)
        self.assertIn("one symbol failed", markdown)

    def test_roc_date_conversion_handles_year_boundary(self) -> None:
        self.assertEqual(TwseCollector._roc_date_to_stamp("115/01/02"), "20260102")

    def test_market_groups_are_stable(self) -> None:
        self.assertEqual(YahooMarketCollector._group("^GSPC"), "indices")
        self.assertEqual(YahooMarketCollector._group("TSM"), "adr")
        self.assertEqual(YahooMarketCollector._group("GC=F"), "commodities")
        self.assertEqual(YahooMarketCollector._group("TWD=X"), "fx")

    def test_yahoo_headline_parser_deduplicates_and_limits(self) -> None:
        page = """<article><h3><a href='/one'>First headline</a></h3></article>
        <article><h3><a href='/one-copy'>First headline</a></h3></article>
        <article><h3><a href='https://example.com/two'>Second headline</a></h3></article>"""
        self.assertEqual(YahooHeadlineCollector._headlines(page, "https://finance.yahoo.com/news/", 2), [
            ("First headline", "https://finance.yahoo.com/one"),
            ("Second headline", "https://example.com/two"),
        ])

    def test_yahoo_rss_parser_keeps_description_for_summary(self) -> None:
        feed = """<?xml version='1.0'?><rss><channel><item><title>台股焦點</title>
        <link>https://tw.stock.yahoo.com/a</link><description><![CDATA[<p>市場今日震盪。</p>]]></description>
        </item></channel></rss>"""
        self.assertEqual(YahooHeadlineCollector._rss_items(feed, 1), [
            ("台股焦點", "https://tw.stock.yahoo.com/a", "<p>市場今日震盪。</p>"),
        ])
        self.assertEqual(YahooHeadlineCollector._clean_description("<p>市場今日震盪。</p>"), "市場今日震盪。")

    def test_markdown_has_required_card_sections_and_summaries(self) -> None:
        records = [
            {"kind": "market", "group": "indices", "label": "NASDAQ", "price": 10, "change": 1, "change_percent": 2},
            {"kind": "market", "group": "adr", "label": "台積電 ADR", "price": 20, "change": 1, "change_percent": 3},
            {"kind": "market", "group": "commodities", "label": "黃金", "price": 30, "change": -1, "change_percent": -1},
            {"kind": "market", "group": "fx", "label": "USD/TWD", "price": 32, "change": 0.1, "change_percent": 0.3},
            {"kind": "news", "category": "international", "title": "中文國際標題", "summary": "重點：摘要。", "source": "yahoo_news"},
            {"kind": "news", "category": "domestic", "title": "台股標題", "summary": "重點：摘要。", "source": "yahoo_news"},
        ]
        markdown = render_markdown(build_report([CollectorResult("fixture", records)], self.now, "Asia/Taipei"), "MorningAI")
        for heading in ("## 盤前重點摘要", "### 指數", "### ADR", "### 黃金原油", "### 匯率", "## 國際財經要聞（中文）", "## 台股新聞"):
            self.assertIn(heading, markdown)
        self.assertIn("重點：摘要。", markdown)

    def test_international_filter_rejects_entertainment(self) -> None:
        self.assertTrue(YahooHeadlineCollector._financial_headline("輝達財報帶動晶片股上漲"))
        self.assertFalse(YahooHeadlineCollector._financial_headline("前女團成員分享整形心得"))

    def test_export_and_site_escape_untrusted_text(self) -> None:
        bad = "</script><script>alert(1)</script>"
        report = build_report([CollectorResult("x", [{"kind": "news", "title": bad, "link": "https://example.com"}])], self.now, "Asia/Taipei")
        markdown = render_markdown(report, "MorningAI")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_report(report, markdown, root / "report")
            build_site(root / "report", root / "docs", bad)
            page = (root / "docs" / "index.html").read_text(encoding="utf-8")
            payload = json.loads((root / "report" / "today.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertNotIn("</script><script>alert", page)
            self.assertTrue((root / "docs" / "history" / "2026-08-13.html").exists())


if __name__ == "__main__":
    unittest.main()
