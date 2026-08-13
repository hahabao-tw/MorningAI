from __future__ import annotations

from .model import MorningReport


GROUPS = (
    ("indices", "指數"),
    ("adr", "ADR"),
    ("commodities", "黃金原油"),
    ("fx", "匯率"),
)


def _number(value: object, digits: int = 2) -> str:
    return "資料缺漏" if value is None else f"{float(value):,.{digits}f}"


def _signed(value: object, suffix: str = "") -> str:
    if value is None:
        return "資料缺漏"
    number = float(value)
    return f"{number:+,.2f}{suffix}"


def _briefing(report: MorningReport) -> list[str]:
    lines: list[str] = []
    indices = [item for item in report.markets if item.get("group") == "indices" and item.get("change_percent") is not None]
    if indices:
        best = max(indices, key=lambda item: float(item["change_percent"]))
        worst = min(indices, key=lambda item: float(item["change_percent"]))
        lines.append(f"全球指數強弱分歧，{best['label']} {_signed(best['change_percent'], '%')}，{worst['label']} {_signed(worst['change_percent'], '%')}。")
    adrs = [item for item in report.markets if item.get("group") == "adr" and item.get("change_percent") is not None]
    if adrs:
        leader = max(adrs, key=lambda item: float(item["change_percent"]))
        lines.append(f"台灣 ADR 以{leader['label']}表現最強，漲跌幅 {_signed(leader['change_percent'], '%')}。")
    if report.taiwan_market:
        market = report.taiwan_market[0]
        lines.append(f"台股最近交易日收 {_number(market.get('index'))} 點，漲跌 {_signed(market.get('change'))} 點。")
    preferred_news = [item for item in report.news if item.get("source") == "yahoo_news"]
    news_pool = preferred_news or report.news
    headlines = [item.get("title") for item in news_pool if item.get("category") in {"international", "domestic"}]
    if headlines:
        lines.append("新聞焦點涵蓋：" + "；".join(str(title) for title in headlines[:2]) + "。")
    return lines or ["目前可用資料不足，請查看下方來源狀態。"]


def render_markdown(report: MorningReport, title: str) -> str:
    lines = [f"# {title}", "", f"日期：{report.report_date}", f"更新：{report.generated_at}", "", "## 盤前重點摘要", ""]
    lines.extend(f"- {item}" for item in _briefing(report))
    lines.extend(["", "## 全球市場", ""])
    for group_key, group_title in GROUPS:
        lines.extend([f"### {group_title}", ""])
        items = [item for item in report.markets if item.get("group") == group_key]
        if items:
            for item in items:
                lines.append(
                    f"- {item.get('label', item.get('symbol'))}：{_number(item.get('price'))}"
                    f"（{_signed(item.get('change'))} / {_signed(item.get('change_percent'), '%')}）"
                )
        else:
            lines.append("- 資料缺漏")
        lines.append("")
    lines.extend(["## 台股昨日", ""])
    if report.taiwan_market:
        item = report.taiwan_market[0]
        lines.extend([
            f"- 加權指數：{_number(item.get('index'))}",
            f"- 漲跌：{_signed(item.get('change'))}",
            f"- 成交金額：{_number(item.get('turnover'), 0)} 元",
        ])
        for institution in item.get("institutional") or []:
            lines.append(f"- {institution.get('name')}買賣超：{_number(institution.get('net'), 0)} 元")
    else:
        lines.append("- 資料缺漏")
    for category, heading in (("international", "國際財經要聞（中文）"), ("domestic", "台股新聞")):
        lines.extend(["", f"## {heading}", ""])
        items = [item for item in report.news if item.get("category") == category]
        preferred = [item for item in items if item.get("source") == "yahoo_news"]
        if preferred:
            items = preferred
        if not items and category == "international":
            items = [item for item in report.news if not item.get("category")]
        if items:
            for index, item in enumerate(items[:5], 1):
                title_text = str(item.get("title", "")).replace("[", "\\[").replace("]", "\\]")
                link = item.get("link")
                lines.append(f"{index}. [{title_text}]({link})" if link else f"{index}. {title_text}")
                if item.get("summary"):
                    lines.append(f"   - {item['summary']}")
                original = item.get("original_title")
                if original and original != item.get("title"):
                    lines.append(f"   - 原文：{original}")
        else:
            lines.append("1. 資料缺漏")
    lines.extend(["", "## 資料狀態", ""])
    for status in report.source_status:
        if status["ok"]:
            state = f"正常（{status['records']} 筆）"
        elif status["records"]:
            state = f"部分失敗（保留 {status['records']} 筆）：{status['error']}"
        else:
            state = f"失敗：{status['error']}"
        lines.append(f"- {status['source']}：{state}")
    lines.append("")
    return "\n".join(lines)
