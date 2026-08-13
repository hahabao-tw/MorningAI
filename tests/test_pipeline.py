from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from crawler.base import CollectorResult
from crawler.twse import TwseCollector
from processor.export import write_report
from processor.markdown import render_markdown
from processor.normalize import build_report
from processor.site import build_site


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 12, 22, 30, tzinfo=timezone.utc)

    def test_partial_failure_still_builds_report(self) -> None:
        results = [
            CollectorResult("market", [{"kind": "market", "label": "S&P 500", "price": 6000, "change": 10, "change_percent": 0.17}]),
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
        result = CollectorResult(
            "market",
            [{"kind": "market", "label": "NASDAQ", "price": 1, "change": 0, "change_percent": 0}],
            "one symbol failed",
        )
        report = build_report([result], self.now, "Asia/Taipei")
        markdown = render_markdown(report, "MorningAI")
        self.assertIn("部分失敗", markdown)
        self.assertIn("one symbol failed", markdown)

    def test_roc_date_conversion_handles_year_boundary(self) -> None:
        self.assertEqual(TwseCollector._roc_date_to_stamp("115/01/02"), "20260102")

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
