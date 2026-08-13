from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MorningReport:
    schema_version: int
    report_date: str
    generated_at: str
    timezone: str
    markets: list[dict[str, Any]] = field(default_factory=list)
    taiwan_market: list[dict[str, Any]] = field(default_factory=list)
    news: list[dict[str, Any]] = field(default_factory=list)
    source_status: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

