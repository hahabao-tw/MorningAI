from __future__ import annotations

import json
import urllib.request
from typing import Any


class HttpClient:
    def __init__(self, timeout: int, user_agent: str) -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def get_bytes(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept": "application/json,text/xml,application/rss+xml,*/*"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def get_text(self, url: str) -> str:
        raw = self.get_bytes(url)
        return raw.decode("utf-8", errors="replace")

    def get_json(self, url: str) -> Any:
        return json.loads(self.get_bytes(url).decode("utf-8"))
