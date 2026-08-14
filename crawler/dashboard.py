from __future__ import annotations

from .base import Collector, CollectorResult
from .http import HttpClient


class MarketDashboardCollector(Collector):
    name = "market_dashboard"
    base = "https://hahabao-tw.github.io/tw-market-dashboard/data"

    def __init__(self, client: HttpClient) -> None:
        self.client = client

    def collect(self) -> CollectorResult:
        try:
            futures = self.client.get_json(f"{self.base}/futures.json")
            options = self.client.get_json(f"{self.base}/options.json")
            taiex = self.client.get_json(f"{self.base}/taiex.json")
            tx = futures["history"]["TX"][-1]
            mtx = futures["history"]["MTX"][-1]
            tmf = futures["history"]["TMF"][-1]
            record = {
                "kind": "chips",
                "date": tx["date"],
                "foreign_tx_net": tx["inst"]["外資"]["net"],
                "trust_tx_net": tx["inst"]["投信"]["net"],
                "mtx_retail_ratio": mtx["retail"]["ratio"],
                "tmf_retail_ratio": tmf["retail"]["ratio"],
                "options_pc_ratio": options["pc_ratio"]["value"],
                "tsmc_impact": taiex["impact"],
                "source": self.name,
            }
        except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
            return CollectorResult(self.name, error=f"{type(exc).__name__}: 籌碼資料讀取失敗")
        return CollectorResult(self.name, [record])
