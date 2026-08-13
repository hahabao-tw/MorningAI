from __future__ import annotations

from .base import Collector, CollectorResult


class TaifexCollector(Collector):
    """Reserved adapter for TAIFEX daily/night-session futures data."""

    name = "taifex"

    def collect(self) -> CollectorResult:
        return CollectorResult(self.name, error="尚未啟用：需確認 TAIFEX 官方資料欄位與交易日規則")

