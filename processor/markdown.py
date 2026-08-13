from __future__ import annotations

from .model import MorningReport


def _number(value: object, digits: int = 2) -> str:
    return "資料缺漏" if value is None else f"{float(value):,.{digits}f}"


def render_markdown(report: MorningReport, title: str) -> str:
    lines = [f"# {title}", "", f"日期：{report.report_date}", f"更新：{report.generated_at}", "", "## 全球市場", ""]
    if report.markets:
        for item in report.markets:
            change = _number(item.get("change"))
            percent = _number(item.get("change_percent"))
            lines.append(f"- {item.get('label', item.get('symbol'))}：{_number(item.get('price'))}（{change} / {percent}%）")
    else:
        lines.append("- 資料缺漏")
    lines.extend(["", "## 台股昨日", ""])
    if report.taiwan_market:
        item = report.taiwan_market[0]
        lines.extend([
            f"- 加權指數：{_number(item.get('index'))}",
            f"- 漲跌：{_number(item.get('change'))}",
            f"- 成交金額：{_number(item.get('turnover'), 0)} 元",
        ])
        institutions = item.get("institutional") or []
        for institution in institutions:
            lines.append(f"- {institution.get('name')}買賣超：{_number(institution.get('net'), 0)} 元")
    else:
        lines.append("- 資料缺漏")
    lines.extend(["", "## 國際新聞", ""])
    if report.news:
        for index, item in enumerate(report.news[:10], 1):
            title_text = str(item.get("title", "")).replace("[", "\\[").replace("]", "\\]")
            link = item.get("link")
            lines.append(f"{index}. [{title_text}]({link})" if link else f"{index}. {title_text}")
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
