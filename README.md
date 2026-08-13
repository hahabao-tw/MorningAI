# MorningAI

每天 06:30（台北時間）自動整理盤前資料，保留標準化 Markdown、JSON 歷史紀錄，並部署成適合手機使用的 GitHub Pages。網站提供「複製 Markdown」與「複製 ChatGPT Prompt」按鈕；內容仍由人工審核後再發送。

## 目前範圍

- Yahoo Finance：美股指數、期貨、ADR、匯率、原物料。
- TWSE 官方公開資料：最近交易日大盤摘要、三大法人買賣金額。
- RSS：設定檔中的國際新聞來源。
- TAIFEX、MOPS：已有一致的 Collector 介面，但預設停用，待確認官方資料欄位後實作。
- 任一來源失敗時仍會產生晨報，並在「資料狀態」清楚標示；不以猜測值補資料。

> Yahoo 與 RSS 網址屬外部服務，可能變更或限制存取。正式使用前應在 GitHub Actions 手動執行一次，確認所在地區與當日回應。

## Repo 結構

```text
MorningAI/
├─ .github/workflows/morning.yml  # 排程、測試、保存歷史、部署 Pages
├─ config/config.toml             # 資料來源、商品、Prompt 設定
├─ crawler/                       # 各資料來源介面與實作
├─ processor/                     # 正規化、Markdown/JSON、網站產生器
├─ report/                        # today 與日期化歷史資料（執行後產生）
├─ docs/                          # GitHub Pages 靜態網站（執行後產生）
├─ tests/                         # 無網路單元測試
└─ run.py                         # 單一執行入口
```

## 第一次設定

1. 建立 GitHub repository，將本資料夾內容推上去。
2. 修改 `config/config.toml`：至少把 `user_agent` 裡的 `OWNER` 換成 GitHub 帳號，檢查 symbols、RSS 與 Prompt。
3. Repository → **Settings → Pages → Build and deployment → Source** 選 **GitHub Actions**。
4. Repository → **Actions → MorningAI daily report → Run workflow** 手動試跑。
5. 全部通過後，Pages 網址會出現在 workflow 的 deployment 結果。

排程 `30 22 * * *` 是每日 UTC 22:30，對應台北時間隔日 06:30。台灣假日仍會執行，但 TWSE 會回溯最近 14 日尋找上一交易日，涵蓋一般連假。

若 workflow 無法保存歷史資料，至 Repository → **Settings → Actions → General → Workflow permissions** 選 **Read and write permissions**。

## 本機驗證（選用）

需要 Python 3.11 以上，不需安裝第三方套件。

```powershell
python -m unittest discover -s tests -v
python run.py
```

完成後開啟 `docs/index.html`。網路完全失敗時仍應產生頁面，來源狀態會顯示失敗。

## Collector 介面

新增資料來源時繼承 `crawler.base.Collector`，`collect()` 必須回傳 `CollectorResult`，不得讓單一來源例外中止整體流程。標準 record 以 `kind` 分流：

- `market`：全球市場、期貨、ADR、匯率、原物料。
- `twse_summary`：台股大盤摘要。
- `news`：標題、連結、發布時間。

新增實作後，在 `run.py` 的 `collectors()` 註冊，於 `config/config.toml` 加開關，並補上成功、空資料、逾時或格式改變的測試。

## JSON 穩定性

`report/today.json` 與 `report/history/YYYY-MM-DD.json` 含 `schema_version`。未來欄位若有不相容變更，須遞增版本，避免歷史分析靜默讀錯。
