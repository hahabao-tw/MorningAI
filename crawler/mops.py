from __future__ import annotations

from .base import Collector, CollectorResult


class MopsCollector(Collector):
    """Reserved adapter for MOPS announcements and investor conferences."""

    name = "mops"

    def collect(self) -> CollectorResult:
        return CollectorResult(self.name, error="尚未啟用：需確認公開資訊觀測站查詢範圍")

