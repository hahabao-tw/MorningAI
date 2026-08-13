from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CollectorResult:
    source: str
    records: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Collector(ABC):
    name: str

    @abstractmethod
    def collect(self) -> CollectorResult:
        """Return normalized records; report failures instead of raising."""
        raise NotImplementedError

