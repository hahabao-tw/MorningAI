from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from crawler.base import CollectorResult
from crawler.dashboard import MarketDashboardCollector
from crawler.stockq import StockQCollector
from crawler.taifex import TaifexCollector
from crawler.twse import TwseCollector
from crawler.yahoo import YahooMarketCollector
from crawler.yahoo_news import YahooHeadlineCollector
from crawler.yahoo_future import YahooFutureCollector
from processor.export import write_report
from processor.markdown import render_markdown
from processor.normalize import build_report
from processor.site import build_site
from run import reuse_same_day_market_snapshots


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 12, 22, 30, tzinfo=timezone.utc)

    def test_partial_failure_still_builds_report(self) -> None:
        results = [
            CollectorResult("market", [{"kind": "market", "group": "indices", "label": "S&P 500", "price": 6000, "change": 10, "change_percent": 0.17}]),
            CollectorResult("news", error="timeout"),
        ]
        report = build_report(results, self.now, "Asia/Taipei")
        markdown = render_markdown(report, "F1台股盤前戰情早報")
        self.assertEqual(report.report_date, "2026-08-13")
        self.assertIn("S&P 500", markdown)
        self.assertIn("資料不足", markdown)
        self.assertNotIn("timeout", markdown)

    def test_duplicate_news_is_removed(self) -> None:
        item = {"kind": "news", "title": "Same", "link": "https://example.com", "published_at": None}
        report = build_report([CollectorResult("a", [item]), CollectorResult("b", [item])], self.now, "Asia/Taipei")
        self.assertEqual(len(report.news), 1)

    def test_partial_source_failure_is_kept_out_of_markdown(self) -> None:
        result = CollectorResult("market", [{"kind": "market", "group": "indices", "label": "NASDAQ", "price": 1, "change": 0, "change_percent": 0}], "one symbol failed")
        markdown = render_markdown(build_report([result], self.now, "Asia/Taipei"), "F1台股盤前戰情早報")
        self.assertNotIn("資料狀態", markdown)
        self.assertNotIn("one symbol failed", markdown)

    def test_roc_date_conversion_handles_year_boundary(self) -> None:
        self.assertEqual(TwseCollector._roc_date_to_stamp("115/01/02"), "20260102")

    def test_market_groups_are_stable(self) -> None:
        self.assertEqual(YahooMarketCollector._group("^GSPC"), "indices")
        self.assertEqual(YahooMarketCollector._group("TSM"), "adr")
        self.assertEqual(YahooMarketCollector._group("GC=F"), "commodities")
        self.assertEqual(YahooMarketCollector._group("TWD=X"), "fx")

    def test_yahoo_market_uses_single_day_previous_close(self) -> None:
        class Client:
            requested_url = ""

            def get_json(self, url: str) -> dict:
                self.requested_url = url
                return {"chart": {"result": [{"meta": {
                    "regularMarketPrice": 110,
                    "chartPreviousClose": 100,
                    "currency": "USD",
                    "regularMarketTime": 1,
                }}]}}

        client = Client()
        result = YahooMarketCollector(client, {"^IXIC": "NASDAQ"}).collect()
        self.assertIn("range=1d", client.requested_url)
        self.assertEqual(result.records[0]["change"], 10)
        self.assertEqual(result.records[0]["change_percent"], 10)

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

    def test_markdown_has_requested_sections_and_format(self) -> None:
        records = [
            {"kind": "market", "group": "indices", "label": "S&P 500", "price": 10, "change": 1, "change_percent": 2},
            {"kind": "market", "group": "indices", "label": "NASDAQ", "price": 11, "change": 1, "change_percent": 2},
            {"kind": "market", "group": "indices", "label": "費城半導體", "price": 12, "change": 1, "change_percent": 2},
            {"kind": "market", "group": "indices", "label": "道瓊指數", "price": 13, "change": 1, "change_percent": 2},
            {"kind": "market", "group": "indices", "label": "那斯達克期貨", "price": 14, "change": 1, "change_percent": 2},
            {"kind": "market", "group": "adr", "label": "台積電 ADR", "price": 20, "change": 1, "change_percent": 3},
            {"kind": "market", "group": "commodities", "label": "黃金", "price": 30, "change": -1, "change_percent": -1},
            {"kind": "market", "group": "fx", "label": "USD/TWD", "price": 32, "change": 0.1, "change_percent": 0.3},
            {"kind": "market", "group": "taiwan_indices", "label": "台灣加權", "price": 46021.48, "change": 503.41, "change_percent": 1.11},
            {"kind": "market", "group": "taiwan_indices", "label": "台灣櫃買", "price": 406.12, "change": 4.10, "change_percent": 1.02},
            {"kind": "market", "group": "taifex", "label": "台指期夜盤", "price": 46389, "change": 364, "change_percent": 0.79, "source": "yahoo_future"},
            {"kind": "market", "group": "taifex", "symbol": "WCDF&", "label": "台積電期貨夜盤", "price": 2428, "change": 18, "change_percent": 0.75, "source": "yahoo_future"},
            {"kind": "twse_summary", "index": 45000, "change": 100, "turnover": 858_700_000_000, "institutional": [{"name": "外資", "net": 11_020_000_000}]},
            {"kind": "chips", "foreign_tx_net": -86249, "trust_tx_net": 82327, "mtx_retail_ratio": 22.9, "tmf_retail_ratio": 15.58, "options_pc_ratio": 112.03, "tsmc_impact": 8.463},
            {"kind": "news", "category": "international", "title": "國際財經標題", "summary": "重點：國際摘要。", "link": "https://example.com/international", "source": "yahoo_news"},
            {"kind": "news", "category": "domestic", "title": "台股標題", "summary": "重點：台股摘要。", "link": "https://example.com/domestic", "source": "yahoo_news"},
        ]
        markdown = render_markdown(build_report([CollectorResult("fixture", records)], self.now, "Asia/Taipei"), "F1台股盤前戰情早報")
        for heading in ("## 盤前重點摘要", "## 美股指數", "## ADR", "## 黃金原油", "## 匯率", "## 台股昨日", "## 台指期夜盤", "## 台積電期貨夜盤", "## 台股期貨籌碼變化", "## 台積電大盤影響點數", "## 台股法人買賣動向", "## 華南期貨 F1極速 團隊，帶您 快速 掌握市場動向 !"):
            self.assertIn(heading, markdown)
        self.assertIn("本團隊已力求數據與資訊正確，如有錯誤，請以官方數據為主", markdown)
        self.assertLess(markdown.index("## 台股法人買賣動向"), markdown.index("## 華南期貨 F1極速 團隊，帶您 快速 掌握市場動向 !"))
        self.assertNotIn("## 國際財經要聞（中文）", markdown)
        self.assertNotIn("## 台股新聞", markdown)
        self.assertNotIn("國際財經標題", markdown)
        self.assertNotIn("台股標題", markdown)
        taiwan_yesterday = markdown.split("## 台股昨日", 1)[1].split("## 台指期夜盤", 1)[0]
        self.assertIn("### 台灣加權", taiwan_yesterday)
        self.assertIn("收盤：46,021.48", taiwan_yesterday)
        self.assertIn("漲跌：+503.41（+1.11%）", taiwan_yesterday)
        self.assertIn("### 台灣櫃買", taiwan_yesterday)
        self.assertIn("收盤：406.12", taiwan_yesterday)
        self.assertIn("漲跌：+4.10（+1.02%）", taiwan_yesterday)
        self.assertIn("收盤：46,389", markdown)
        self.assertIn("漲跌：+364（+0.79%）", markdown)
        self.assertNotIn("收盤：46,389.00", markdown)
        tsmc_night = markdown.split("## 台積電期貨夜盤", 1)[1].split("## 台股期貨籌碼變化", 1)[0]
        self.assertIn("收盤：2,428", tsmc_night)
        self.assertIn("漲跌：+18（+0.75%）", tsmc_night)
        self.assertNotIn("漲跌點數：", tsmc_night)
        self.assertNotIn("成交量：", markdown)
        self.assertIn("外資大台淨OI：-86,249 口", markdown)
        self.assertIn("投信大台淨OI：+82,327 口", markdown)
        self.assertIn("小台散戶多空比：22.90%", markdown)
        self.assertIn("微台散戶多空比：15.58%", markdown)
        self.assertIn("臺指選擇權 P/C 比：112.03%", markdown)
        self.assertIn("台積電每跳 1 元：約影響 8.463 點", markdown)
        self.assertNotIn("更新：", markdown)
        self.assertNotIn("[國際財經標題]", markdown)
        self.assertNotIn("[台股標題]", markdown)
        self.assertNotIn("https://example.com", markdown)
        self.assertEqual(markdown.split("## 盤前重點摘要\n", 1)[1].split("## 美股指數", 1)[0].strip(), "")
        self.assertNotIn("那斯達克期貨：", markdown)
        self.assertIn("**NASDAQ**：11.00（+1.00 / +2.00%）", markdown)
        positions = [markdown.index(f"**{name}**：") for name in ("NASDAQ", "費城半導體", "S&P 500", "道瓊指數")]
        self.assertEqual(positions, sorted(positions))

    def test_taifex_parser_selects_nearest_tx_after_hours_contract(self) -> None:
        csv_text = "日期,契約代號,到期月份(週別),最後成交價,漲跌價,漲跌%,合計成交量,交易時段\n20260813,TX,202609,46100,▲100,0.22%,2000,盤後\n20260813,TX,202608,46000,▼-50,-0.11%,10000,盤後\n20260813,TX,202608,45900,-100,-0.22%,9999,一般\n"
        records = TaifexCollector._parse(csv_text)
        self.assertEqual(records[0]["contract_month"], "202608")
        self.assertEqual(records[0]["price"], 46000)
        self.assertEqual(records[0]["change"], -50)

    def test_stockq_parser_decodes_both_taiwan_indices(self) -> None:
        def cell(parts: str, seed: int) -> str:
            return f"<td><script>(function(){{var a=[{parts}],z={seed};var r=function(){{z=z*48271%2147483647;return z/2147483647}};r();r();var o=[0,1,2];for(var i=2;i>0;i--){{var j=Math.floor(r()*(i+1));var t=o[i];o[i]=o[j];o[j]=t}}r();var f1=Math.floor(r()*4);r();var f2=Math.floor(r()*5);a.splice(f2,1);a.splice(f1,1);}})();</script></td>"
        page = "<table><tr><td>TWSE.php</td>" + cell("'4','46021.','8','959','561'", 601254252) * 3 + "</tr><tr><td>TWOTCI.php</td>" + cell("'40','323','6','.12','49'", 176717741) * 3 + "</tr></table>"
        records = StockQCollector._parse(page)
        self.assertEqual([item["label"] for item in records], ["台灣加權", "台灣櫃買"])
        self.assertEqual(records[0]["price"], 46021.48)
        self.assertEqual(records[1]["price"], 406.12)

    def test_stockq_collector_rejects_current_day_intraday_rows(self) -> None:
        class Client:
            def get_text(self, url: str) -> str:
                return "<table><tr><td>TWSE.php</td><td>08/14</td></tr></table>"

        collector = StockQCollector(Client(), date(2026, 8, 14), before_open=False)
        records = collector._parse = lambda page: [
            {"kind": "market", "group": "taiwan_indices", "label": "台灣加權", "date": "08/14"},
            {"kind": "market", "group": "taiwan_indices", "label": "台灣櫃買", "date": "08/14"},
        ]
        result = collector.collect()
        self.assertEqual(result.records, [])
        self.assertIsNotNone(result.error)

    def test_yahoo_future_parser_reads_visible_quote(self) -> None:
        page = "<div>收盤 | 2026/08/14 04:59 更新</div><h2>台指期近一即時行情</h2><div>成交</div><div>46,389.00</div><div>昨收</div><div>46,025.00</div><div>漲跌幅</div><div>0.79%</div><div>漲跌</div><div>364.00</div>"
        record = YahooFutureCollector._parse(page)
        self.assertEqual((record["price"], record["change"], record["change_percent"]), (46389, 364, 0.79))

    def test_yahoo_future_parser_derives_negative_direction_from_previous_close(self) -> None:
        page = "<div>收盤 | 2026/08/15 04:59 更新</div><h2>台指期近一即時行情</h2><div>成交</div><div>45,727.00</div><div>昨收</div><div>45,812.00</div><div>漲跌幅</div><div>0.19%</div><div>漲跌</div><div>85.00</div>"
        record = YahooFutureCollector._parse(page)
        self.assertEqual((record["price"], record["change"], record["change_percent"]), (45727, -85, -0.19))

    def test_yahoo_future_parser_rejects_regular_session_quote(self) -> None:
        page = "<div>盤中 | 2026/08/14 08:46 更新</div><h2>台指期近一即時行情</h2><div>成交</div><div>46,442.00</div><div>漲跌幅</div><div>0.91%</div><div>漲跌</div><div>417.00</div>"
        with self.assertRaisesRegex(ValueError, "not closed"):
            YahooFutureCollector._parse(page)

    def test_yahoo_future_parser_rejects_active_night_session_quote(self) -> None:
        page = "<div>收盤 | 2026/08/14 17:30 更新</div><h2>台指期近一即時行情</h2><div>成交</div><div>45,794.00</div><div>漲跌幅</div><div>0.04%</div><div>漲跌</div><div>18.00</div>"
        with self.assertRaisesRegex(ValueError, "outside the completed night session"):
            YahooFutureCollector._parse(page)

    def test_yahoo_future_parser_reads_tsmc_night_quote(self) -> None:
        page = "<div>收盤 | 2026/08/14 04:59 更新</div><h2>台積電期貨近一即時行情</h2><div>成交</div><div>2,428</div><div>昨收</div><div>2,410</div><div>漲跌幅</div><div>0.75%</div><div>漲跌</div><div>18.00</div>"
        record = YahooFutureCollector._parse(page, "台積電期貨近一即時行情", "WCDF&", "台積電期貨夜盤")
        self.assertEqual(record["symbol"], "WCDF&")
        self.assertEqual(record["price"], 2428)

    def test_same_day_rerun_reuses_saved_market_snapshots(self) -> None:
        report = build_report([], self.now, "Asia/Taipei")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {"report_date": "2026-08-13", "markets": [
                {"group": "taifex", "source": "yahoo_future", "symbol": "WTX&", "price": 46389},
                {"group": "taifex", "source": "yahoo_future", "symbol": "WCDF&", "price": 2428},
                {"group": "taiwan_indices", "source": "stockq", "label": "台灣加權", "price": 46021.48},
                {"group": "taiwan_indices", "source": "stockq", "label": "台灣櫃買", "price": 406.12},
            ]}
            (root / "today.json").write_text(json.dumps(payload), encoding="utf-8")
            reuse_same_day_market_snapshots(report, root)
        self.assertEqual(report.markets[0]["price"], 46389)
        self.assertEqual(report.markets[1]["price"], 2428)
        self.assertEqual([item["price"] for item in report.markets[2:]], [46021.48, 406.12])

    def test_cross_day_rerun_does_not_reuse_stale_night_quote(self) -> None:
        report = build_report([], self.now, "Asia/Taipei")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = {"report_date": "2026-08-12", "markets": [{"group": "taifex", "source": "yahoo_future", "price": 45000}]}
            (root / "today.json").write_text(json.dumps(payload), encoding="utf-8")
            reuse_same_day_market_snapshots(report, root)
        self.assertEqual(report.markets, [])

    def test_dashboard_collector_maps_requested_chip_fields(self) -> None:
        class Client:
            def get_json(self, url: str) -> dict:
                if url.endswith("futures.json"):
                    return {"history": {
                        "TX": [{"date": "2026-08-13", "inst": {"外資": {"net": -86249}, "投信": {"net": 82327}}}],
                        "MTX": [{"retail": {"ratio": 22.9}}],
                        "TMF": [{"retail": {"ratio": 15.58}}],
                    }}
                if url.endswith("options.json"):
                    return {"pc_ratio": {"value": 112.03}}
                return {"impact": 8.463}

        result = MarketDashboardCollector(Client()).collect()
        self.assertTrue(result.ok)
        self.assertEqual(result.records[0]["foreign_tx_net"], -86249)
        self.assertEqual(result.records[0]["tsmc_impact"], 8.463)

    def test_international_filter_rejects_entertainment(self) -> None:
        self.assertTrue(YahooHeadlineCollector._financial_headline("輝達財報帶動晶片股上漲"))
        self.assertFalse(YahooHeadlineCollector._financial_headline("前女團成員分享整形心得"))

    def test_export_logs_status_but_omits_it_from_public_json(self) -> None:
        bad = "</script><script>alert(1)</script>"
        report = build_report([CollectorResult("x", [{"kind": "news", "title": bad, "link": "https://example.com"}])], self.now, "Asia/Taipei")
        markdown = render_markdown(report, "F1台股盤前戰情早報")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_report(report, markdown, root / "report")
            build_site(root / "report", root / "docs", bad)
            page = (root / "docs" / "index.html").read_text(encoding="utf-8")
            payload = json.loads((root / "report" / "today.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertNotIn("source_status", payload)
            self.assertNotIn("</script><script>alert", page)
            self.assertTrue((root / "docs" / "history" / "2026-08-13.html").exists())
            self.assertIn("複製完整 Markdown", page)
            self.assertIn("id=\"summary-input\"", page)
            self.assertIn("自動加入下方 Markdown", page)
            self.assertIn("input.addEventListener('input',refreshPreview)", page)
            self.assertIn("const separator=String.fromCharCode(10,10)", page)
            self.assertNotIn("const body=summary?`\n\n${summary}\n\n`:'\n\n'", page)
            self.assertIn("重新整理頁面後會自動清除", page)
            self.assertIn("preview.textContent=currentMarkdown", page)
            self.assertNotIn("localStorage", page)
            self.assertNotIn("sessionStorage", page)
            self.assertNotIn("ChatGPT Prompt", page)
            self.assertNotIn("dialog.showModal()", page)
            self.assertNotIn("2026-08-13T06:30", page)
            log = (root / "report" / "history" / "2026-08-13.log").read_text(encoding="utf-8")
            self.assertIn("source=x status=ok records=1", log)


if __name__ == "__main__":
    unittest.main()
