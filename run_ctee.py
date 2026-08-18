from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from crawler.ctee import CteePremarketCollector, google_news_search_url
from crawler.http import HttpClient
from processor.ctee import build_ctee_site, update_ctee_report
from run import ROOT, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the independent CTEE premarket page")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "config.toml")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        timezone_name = str(config["report"]["timezone"])
        now = datetime.now(timezone.utc)
        local_now = now.astimezone(ZoneInfo(timezone_name))
        network = config["network"]
        client = HttpClient(int(network["timeout_seconds"]), str(network["user_agent"]))
        result = CteePremarketCollector(client, local_now.date(), google_news_search_url()).collect()
        payload = update_ctee_report(
            ROOT / "report" / "ctee",
            local_now.date().isoformat(),
            local_now.isoformat(timespec="seconds"),
            timezone_name,
            result.records,
        )
        build_ctee_site(payload, ROOT / "docs")
        if result.error:
            print(f"CTEE source unavailable: {result.error}; retained any same-day data", file=sys.stderr)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print(f"CTEE report failed: {exc}", file=sys.stderr)
        return 1
    print(f"Generated CTEE page for {payload['report_date']}: {len(payload['articles'])} articles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
