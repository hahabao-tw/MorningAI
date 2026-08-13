from __future__ import annotations

from .model import MorningReport


INDEX_ORDER = ("NASDAQ", "費城半導體", "S&P 500", "道瓊指數")
OTHER_GROUPS = (("adr", "ADR"), ("commodities", "黃金原油"), ("fx", "匯率"))


def _number(value: object, digits: int = 2) -> str:
    return "資料不足" if value is None else f"{float(value):,.{digits}f}"


def _signed(value: object, suffix: str = "") -> str:
    if value is None:
        return "資料不足"
    return f"{float(value):+,.2f}{suffix}"


def _market_line(item: dict[str, object]) -> str:
    return (
        f"- {item.get('label', item.get('symbol'))}：{_number(item.get('price'))}"
        f"（{_signed(item.get('change'))} / {_signed(item.get('change_percent'), '%')}）"
    )


def _briefing(report: MorningReport) -> list[str]:
    lines: list[str] = []
    indices = [item for item in report.markets if item.get("group") == "indices" and item.get("change_percent") is not None]
    if indices:
        best = max(indices, key=lambda item: float(item["change_percent"]))
        worst = min(indices, key=lambda item: float(item["change_percent"]))
        lines.append(f"美股指數強弱分歧，{best['label']} {_signed(best['change_percent'], '%')}，{worst['label']} {_signed(worst['change_percent'], '%')}。")
    adrs = [item for item in report.markets if item.get("group") == "adr" and item.get("change_percent") is not None]
    if adrs:
        leader = max(adrs, key=lambda item: float(item["change_percent"]))
        lines.append(f"台灣 ADR 以{leader['label']}表現最強，漲跌幅 {_signed(leader['change_percent'], '%')}。")
    if report.taiwan_market:
        market = report.taiwan_market[0]
        lines.append(f"台股最近交易日收 {_number(market.get('index'))} 點，漲跌 {_signed(market.get('change'))} 點。")
    preferred_news = [item for item in report.news if item.get("source") == "yahoo_news"]
    headlines = [item.get("title") for item in (preferred_news or report.news) if item.get("category") in {"international", "domestic"}]
    if headlines:
        lines.append("新聞焦點涵蓋：" + "；".join(str(title) for title in headlines[:2]) + "。")
    return lines or ["目前可用資料有限，請查看各區塊內容。"]


def _news_section(report: MorningReport, category: str, heading: str) -> list[str]:
    lines = ["", f"## {heading}", ""]
    items = [item for item in report.news if item.get("category") == category]
    preferred = [item for item in items if item.get("source") == "yahoo_news"]
    if preferred:
        items = preferred
    if not items and category == "international":
        items = [item for item in report.news if not item.get("category")]
    if not items:
        return lines + ["1. 資料不足"]
    for index, item in enumerate(items[:5], 1):
        title = str(item.get("title", "")).replace("[", "\\[").replace("]", "\\]")
        link = item.get("link")
        lines.append(f"{index}. [{title}]({link})" if link else f"{index}. {title}")
        if item.get("summary"):
            lines.append(f"   - {item['summary']}")
    return lines


def render_markdown(report: MorningReport, title: str) -> str:
    lines = [f"# {title}", "", f"日期：{report.report_date}", f"更新：{report.generated_at}", "", "## 盤前重點摘要", ""]
    lines.extend(f"- {item}" for item in _briefing(report))

    lines.extend(["", "## 美股指數", ""])
    indices = {str(item.get("label")): item for item in report.markets if item.get("group") == "indices"}
    for label in INDEX_ORDER:
        if label in indices:
            lines.append(_market_line(indices[label]))
    if not any(label in indices for label in INDEX_ORDER):
        lines.append("- 資料不足")

    for group_key, heading in OTHER_GROUPS:
        lines.extend(["", f"## {heading}", ""])
        items = [item for item in report.markets if item.get("group") == group_key]
        lines.extend(_market_line(item) for item in items)
        if not items:
            lines.append("- 資料不足")

    lines.extend(["", "## 台股昨日", ""])
    if report.taiwan_market:
        item = report.taiwan_market[0]
        turnover = item.get("turnover")
        lines.extend([
            f"- 加權指數：{_number(item.get('index'))}",
            f"- 漲跌：{_signed(item.get('change'))}",
            f"- 成交金額：{_number(None if turnover is None else float(turnover) / 100_000_000)} 億元",
        ])
    else:
        lines.append("- 資料不足")

    lines.extend(["", "## 台指期夜盤", ""])
    futures = [item for item in report.markets if item.get("group") == "taifex"]
    if futures:
        item = futures[0]
        lines.extend([
            f"- 最近月：{item.get('contract_month') or '資料不足'}",
            f"- 收盤：{_number(item.get('price'))}",
            f"- 漲跌：{_signed(item.get('change'))}（{_signed(item.get('change_percent'), '%')}）",
            f"- 成交量：{_number(item.get('volume'), 0)} 口",
        ])
    else:
        lines.append("- 資料不足")

    lines.extend(["", "## 法人買賣超", ""])
    institutions = (report.taiwan_market[0].get("institutional") or []) if report.taiwan_market else []
    if institutions:
        for institution in institutions:
            net = institution.get("net")
            lines.append(f"- {institution.get('name')}：{_signed(None if net is None else float(net) / 100_000_000)} 億元")
    else:
        lines.append("- 資料不足")

    lines.extend(_news_section(report, "international", "國際財經要聞（中文）"))
    lines.extend(_news_section(report, "domestic", "台股新聞"))
    lines.append("")
    return "\n".join(lines)
