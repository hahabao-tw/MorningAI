from __future__ import annotations

import json
from pathlib import Path

from .model import MorningReport


def write_report(report: MorningReport, markdown: str, report_dir: Path) -> None:
    history = report_dir / "history"
    history.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload.pop("source_status", None)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    log_lines = [f"generated_at={report.generated_at}"]
    for status in report.source_status:
        state = "ok" if status["ok"] else "partial" if status["records"] else "failed"
        detail = f" error={status['error']}" if status["error"] else ""
        log_lines.append(f"source={status['source']} status={state} records={status['records']}{detail}")
    (history / f"{report.report_date}.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    for path, content in (
        (report_dir / "today.md", markdown),
        (report_dir / "today.json", json_text),
        (history / f"{report.report_date}.md", markdown),
        (history / f"{report.report_date}.json", json_text),
    ):
        path.write_text(content, encoding="utf-8")
