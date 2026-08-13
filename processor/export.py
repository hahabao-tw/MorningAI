from __future__ import annotations

import json
from pathlib import Path

from .model import MorningReport


def write_report(report: MorningReport, markdown: str, report_dir: Path) -> None:
    history = report_dir / "history"
    history.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n"
    for path, content in (
        (report_dir / "today.md", markdown),
        (report_dir / "today.json", json_text),
        (history / f"{report.report_date}.md", markdown),
        (history / f"{report.report_date}.json", json_text),
    ):
        path.write_text(content, encoding="utf-8")

