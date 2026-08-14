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
        link = item.get("link") if category != "international" else None
        lines.append(f"{index}. [{title}]({link})" if link else f"{index}. {title}")
        if item.get("summary"):
            lines.append(f"   - {item['summary']}")
    return lines


def render_markdown(report: MorningReport, title: str) -> str:
    lines = [f"# {title}", "", f"日期：{report.report_date}", "", "## 盤前重點摘要", ""]

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
    taiwan_indices = [item for item in report.markets if item.get("group") == "taiwan_indices"]
    if taiwan_indices:
        for item in taiwan_indices:
            lines.append(
                f"- {item.get('label')}：指數 {_number(item.get('price'))}｜"
                f"漲跌 {_signed(item.get('change'))}｜比例 {_signed(item.get('change_percent'), '%')}"
            )
    else:
        lines.append("- 資料不足")

    lines.extend(["", "## 台指期夜盤", ""])
    futures = [item for item in report.markets if item.get("group") == "taifex" and item.get("source") == "yahoo_future"]
    if futures:
        item = futures[0]
        lines.extend([
            f"- 收盤：{_number(item.get('price'))}",
            f"- 漲跌：{_signed(item.get('change'))}（{_signed(item.get('change_percent'), '%')}）",
        ])
    else:
        lines.append("- 資料不足")

    lines.extend(["", "## 臺股期貨籌碼", ""])
    if report.chips:
        chip = report.chips[0]
        lines.extend([
            f"- 外資大台淨OI(口)：{_signed(chip.get('foreign_tx_net')).replace('.00', '')}",
            f"- 投信大台淨OI(口)：{_signed(chip.get('trust_tx_net')).replace('.00', '')}",
            f"- 小台散戶多空比：{_signed(chip.get('mtx_retail_ratio'), '%')}",
            f"- 微台散戶多空比：{_signed(chip.get('tmf_retail_ratio'), '%')}",
            f"- 淨臺指選擇權 P/C 比：{_number(chip.get('options_pc_ratio'))}%",
        ])
    else:
        lines.append("- 資料不足")

    lines.extend(["", "## 台積電大盤影響點數", ""])
    if report.chips:
        lines.append(f"- 台積電每跳 1 元：約影響 {_number(report.chips[0].get('tsmc_impact'), 3)} 點")
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
