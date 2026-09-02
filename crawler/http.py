from __future__ import annotations

import json
import time
import urllib.error
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
        last_error: OSError | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                if exc.code not in {408, 429} and exc.code < 500:
                    raise
                last_error = exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (2 ** attempt))
        if last_error is None:
            raise OSError("HTTP request failed without an error")
        raise last_error

    def get_text(self, url: str) -> str:
        raw = self.get_bytes(url)
        return raw.decode("utf-8", errors="replace")

    def get_json(self, url: str) -> Any:
        return json.loads(self.get_bytes(url).decode("utf-8"))
