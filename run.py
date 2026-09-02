from __future__ import annotations

import argparse
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from crawler.base import Collector
from crawler.http import HttpClient
from crawler.mops import MopsCollector
from crawler.dashboard import MarketDashboardCollector
from crawler.news import RssCollector
from crawler.stockq import StockQCollector
from crawler.taifex import TaifexCollector
from crawler.twse import TwseCollector
from crawler.yahoo import YahooMarketCollector
from crawler.yahoo_news import YahooHeadlineCollector
from crawler.yahoo_future import YahooFutureCollector
from crawler.yahoo_tw_indices import YahooTwIndexCollector
from processor.export import write_report
from processor.markdown import render_markdown
from processor.model import MorningReport
from processor.merge import merge_same_day_report
from processor.normalize import build_report
from processor.site import build_site


ROOT = Path(__file__).resolve().parent
REQUIRED_MARKET_SYMBOLS = {"^TWII", "^TWOII", "WTX&", "WCDF&"}


def load_config(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def missing_required_data(report: MorningReport) -> list[str]:
    present_symbols = {str(item.get("symbol")) for item in report.markets}
    missing = sorted(REQUIRED_MARKET_SYMBOLS - present_symbols)
    if not report.chips:
        missing.append("期貨籌碼")
    institutions = (
        report.taiwan_market[0].get("institutional")
        if report.taiwan_market
        else None
    )
    if not institutions:
        missing.append("法人買賣動向")
    return missing


def collectors(config: dict, now: datetime) -> list[Collector]:
    network = config["network"]
    enabled = config["sources"]
    client = HttpClient(int(network["timeout_seconds"]), str(network["user_agent"]))
    items: list[Collector] = []
    if enabled.get("yahoo_enabled", False):
        items.append(YahooMarketCollector(client, config.get("symbols", {})))
    if enabled.get("twse_enabled", False):
        local_date = now.astimezone(ZoneInfo(config["report"]["timezone"])).date()
        items.append(TwseCollector(client, local_date))
    if enabled.get("rss_enabled", False):
        items.append(RssCollector(client, list(config["news"].get("feeds", [])), int(config["news"].get("max_items_per_feed", 5))))
    if enabled.get("yahoo_news_enabled", False):
        news = config["news"]
        items.append(YahooHeadlineCollector(
            client, str(news["international_url"]), str(news["domestic_url"]),
            int(news.get("international_items", 4)), int(news.get("domestic_items", 4)),
            bool(news.get("translate_international", True)),
        ))
    if enabled.get("taifex_enabled", False):
        items.append(TaifexCollector(client))
    if enabled.get("mops_enabled", False):
        items.append(MopsCollector())
    if enabled.get("stockq_enabled", False):
        local_now = now.astimezone(ZoneInfo(config["report"]["timezone"]))
        before_open = (local_now.hour, local_now.minute) < (8, 30)
        items.append(StockQCollector(client, local_now.date(), before_open))
    if enabled.get("yahoo_tw_indices_enabled", False):
        local_now = now.astimezone(ZoneInfo(config["report"]["timezone"]))
        items.append(YahooTwIndexCollector(client, local_now.date()))
    if enabled.get("yahoo_future_enabled", False):
        local_date = now.astimezone(ZoneInfo(config["report"]["timezone"])).date()
        items.append(YahooFutureCollector(client, local_date))
    if enabled.get("market_dashboard_enabled", False):
        items.append(MarketDashboardCollector(client))
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the MorningAI report and static site")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "config.toml")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        now = datetime.now(timezone.utc)
        results = [item.collect() for item in collectors(config, now)]
        report = build_report(results, now, config["report"]["timezone"])
        merge_same_day_report(report, ROOT / "report" / "today.json")
        missing = missing_required_data(report)
        if missing:
            failures = "; ".join(
                f"{result.source}: {result.error}"
                for result in results
                if result.error
            )
            raise ValueError(
                "required Taiwan market data missing: "
                + ", ".join(missing)
                + (f" ({failures})" if failures else "")
            )
        markdown = render_markdown(report, config["report"]["title"])
        write_report(report, markdown, ROOT / "report")
        build_site(ROOT / "report", ROOT / "docs", config["report"]["prompt"])
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"MorningAI failed: {exc}", file=sys.stderr)
        return 1
    print(f"Generated report for {report.report_date}: {len(report.markets)} markets, {len(report.news)} news")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
