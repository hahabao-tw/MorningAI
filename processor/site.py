from __future__ import annotations

import html
import json
from pathlib import Path


STYLE = """
:root{color-scheme:light dark;--bg:#f5f7fb;--card:#fff;--text:#172033;--muted:#697386;--accent:#2457d6;--border:#dfe4ee}
@media(prefers-color-scheme:dark){:root{--bg:#10131a;--card:#191e28;--text:#edf1f7;--muted:#a5afc0;--accent:#85a8ff;--border:#303849}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.65 system-ui,-apple-system,sans-serif}
main{max-width:860px;margin:auto;padding:24px}.top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:clamp(18px,4vw,36px);box-shadow:0 10px 30px #0000000d}
button,.link{border:0;border-radius:10px;padding:11px 15px;background:var(--accent);color:white;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}
.secondary{background:transparent;color:var(--accent);border:1px solid var(--accent)}.actions{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}
pre{white-space:pre-wrap;word-break:break-word;font:15px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace}.muted{color:var(--muted)}
ul{padding-left:22px}a{color:var(--accent)}
"""


def _page(title: str, body: str, script: str = "") -> str:
    return f"""<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(title)}</title><style>{STYLE}</style></head><body><main>{body}</main><script>{script}</script></body></html>"""


def _report_page(markdown: str, date: str) -> str:
    markdown_json = json.dumps(markdown, ensure_ascii=False).replace("</", "<\\/")
    body = f"""<div class=\"top\"><div><h1>F1台股盤前戰情早報</h1><p class=\"muted\">{html.escape(date)}</p></div><a class=\"link secondary\" href=\"history/\">歷史晨報</a></div><section class=\"card\"><div class=\"actions\"><button data-copy=\"markdown\">複製 Markdown</button></div><pre>{html.escape(markdown)}</pre></section>"""
    script = f"""const markdown={markdown_json};const button=document.querySelector('[data-copy=\"markdown\"]');button.addEventListener('click',async()=>{{const old=button.textContent;try{{await navigator.clipboard.writeText(markdown);button.textContent='已複製';}}catch(e){{const area=document.createElement('textarea');area.value=markdown;document.body.append(area);area.select();document.execCommand('copy');area.remove();button.textContent='已複製';}}setTimeout(()=>button.textContent=old,1500);}});"""
    return _page("F1台股盤前戰情早報", body, script)


def build_site(report_dir: Path, docs_dir: Path, _prompt: str) -> None:
    docs_history = docs_dir / "history"
    docs_history.mkdir(parents=True, exist_ok=True)
    markdown = (report_dir / "today.md").read_text(encoding="utf-8")
    payload = json.loads((report_dir / "today.json").read_text(encoding="utf-8"))
    page = _report_page(markdown, payload["report_date"])
    (docs_dir / "index.html").write_text(page, encoding="utf-8")
    (docs_dir / "today.html").write_text(page, encoding="utf-8")
    links: list[str] = []
    for md_path in sorted((report_dir / "history").glob("*.md"), reverse=True):
        date = md_path.stem
        history_page = _report_page(md_path.read_text(encoding="utf-8"), date)
        (docs_history / f"{date}.html").write_text(history_page, encoding="utf-8")
        links.append(f'<li><a href="{html.escape(date)}.html">{html.escape(date)}</a></li>')
    history_body = '<div class="top"><h1>歷史晨報</h1><a class="link secondary" href="../">回到今日</a></div><section class="card"><ul>' + "".join(links) + "</ul></section>"
    (docs_history / "index.html").write_text(_page("MorningAI 歷史晨報", history_body), encoding="utf-8")
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")
