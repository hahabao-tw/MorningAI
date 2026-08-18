from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .merge import merge_records
from .site import _page


def update_ctee_report(
    report_dir: Path,
    report_date: str,
    generated_at: str,
    timezone_name: str,
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    today_path = report_dir / "today.json"
    if today_path.exists():
        previous = json.loads(today_path.read_text(encoding="utf-8"))
        if previous.get("report_date") == report_date and isinstance(previous.get("articles"), list):
            articles = merge_records(articles, previous["articles"], report_date)
    payload = {
        "schema_version": 1,
        "report_date": report_date,
        "generated_at": generated_at,
        "timezone": timezone_name,
        "articles": articles,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    history = report_dir / "history"
    history.mkdir(parents=True, exist_ok=True)
    today_path.write_text(text, encoding="utf-8")
    (history / f"{report_date}.json").write_text(text, encoding="utf-8")
    return payload


def build_ctee_site(payload: dict[str, Any], docs_dir: Path) -> None:
    output = docs_dir / "ctee"
    output.mkdir(parents=True, exist_ok=True)
    articles = payload.get("articles", [])
    if articles:
        rows = "".join(
            f'<article><h2>{html.escape(str(item.get("title") or ""))}</h2>'
            f'<p class="muted">發布：{html.escape(str(item.get("published_at") or "時間未提供"))}</p>'
            f'<a class="link" href="{html.escape(str(item.get("link") or ""), quote=True)}" '
            'target="_blank" rel="noopener noreferrer">開啟工商原文</a></article>'
            for item in articles
        )
    else:
        rows = '<p>尚未取得今日工商盤前資料；排程會於 08:00 再次補抓。</p>'
    body = (
        '<div class="top"><div><h1>工商時報盤前</h1>'
        f'<p class="muted">{html.escape(str(payload["report_date"]))}</p></div>'
        '<a class="link secondary" href="../">回到晨報</a></div>'
        f'<section class="card">{rows}</section>'
        '<p class="muted">資料由 Google News 的工商時報公開索引取得；內容與連結以原站為準。</p>'
    )
    (output / "index.html").write_text(_page("工商時報盤前", body), encoding="utf-8")
