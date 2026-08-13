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
from crawler.news import RssCollector
from crawler.taifex import TaifexCollector
from crawler.twse import TwseCollector
from crawler.yahoo import YahooMarketCollector
from processor.export import write_report
from processor.markdown import render_markdown
from processor.normalize import build_report
from processor.site import build_site


ROOT = Path(__file__).resolve().parent


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
    if enabled.get("taifex_enabled", False):
        items.append(TaifexCollector())
    if enabled.get("mops_enabled", False):
        items.append(MopsCollector())
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
