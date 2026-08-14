from __future__ import annotations

import argparse
import json
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
from processor.export import write_report
from processor.markdown import render_markdown
from processor.model import MorningReport
from processor.normalize import build_report
from processor.site import build_site


ROOT = Path(__file__).resolve().parent


def reuse_same_day_market_snapshots(report: MorningReport, report_dir: Path) -> None:
    previous_path = report_dir / "today.json"
    if not previous_path.exists():
        return
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    if previous.get("report_date") != report.report_date:
        return
    previous_markets = previous.get("markets", [])
    for symbol in ("WTX&", "WCDF&"):
        if not any(item.get("source") == "yahoo_future" and item.get("symbol") == symbol for item in report.markets):
            quote = next((item for item in previous_markets if item.get("source") == "yahoo_future" and item.get("symbol") == symbol), None)
            if quote:
                report.markets.append(quote)
    if not any(item.get("group") == "taiwan_indices" for item in report.markets):
        report.markets.extend(item for item in previous_markets if item.get("group") == "taiwan_indices")


def load_config(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


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
    if enabled.get("yahoo_future_enabled", False):
        items.append(YahooFutureCollector(client))
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
        reuse_same_day_market_snapshots(report, ROOT / "report")
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
