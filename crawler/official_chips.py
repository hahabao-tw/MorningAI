from __future__ import annotations

import csv
import html
import io
import re
from datetime import date, timedelta

from .base import Collector, CollectorResult
from .http import HttpClient


class OfficialChipsCollector(Collector):
    """Taiwan futures positioning data from official TAIFEX and TWSE sources."""

    name = "official_chips"
    products = {
        "TX": "臺股期貨",
        "MTX": "小型臺指期貨",
        "TMF": "微型臺指期貨",
    }
    roles = ("自營商", "投信", "外資")
    lookback_days = 15

    def __init__(self, client: HttpClient, today: date) -> None:
        self.client = client
        self.today = today

    def collect(self) -> CollectorResult:
        try:
            trading_date, institutional = self._latest_institutional()
            totals = {
                code: self._market_open_interest(code, trading_date)
                for code in self.products
            }
            retail_ratios = self._retail_ratios(institutional, totals)
            pc_date, pc_ratio = self._pc_ratio(trading_date)
            if pc_date != trading_date.isoformat():
                raise ValueError("期交所 P/C 比與期貨籌碼日期不一致")
            impact = self._tsmc_impact(trading_date)
            tx = institutional["TX"]
            record = {
                "kind": "chips",
                "date": trading_date.isoformat(),
                "foreign_tx_net": tx["外資"]["net"],
                "trust_tx_net": tx["投信"]["net"],
                "mtx_retail_ratio": retail_ratios["MTX"],
                "tmf_retail_ratio": retail_ratios["TMF"],
                "options_pc_ratio": pc_ratio,
                "tsmc_impact": impact,
                "source": self.name,
            }
        except (csv.Error, KeyError, OSError, TypeError, UnicodeError, ValueError) as exc:
            return CollectorResult(self.name, error=f"{type(exc).__name__}: {exc}")
        return CollectorResult(self.name, [record])

    def _latest_institutional(self) -> tuple[date, dict[str, dict[str, dict[str, int]]]]:
        for offset in range(1, self.lookback_days + 1):
            candidate = self.today - timedelta(days=offset)
            if candidate.weekday() >= 5:
                continue
            rows = self._post_csv(
                "https://www.taifex.com.tw/cht/3/futContractsDateDown",
                {
                    "queryStartDate": candidate.strftime("%Y/%m/%d"),
                    "queryEndDate": candidate.strftime("%Y/%m/%d"),
                    "commodityId": "",
                },
                "https://www.taifex.com.tw/cht/3/futContractsDate",
            )
            parsed = self._parse_institutional(rows)
            day = self._normalize_institutional(parsed.get(candidate.isoformat(), {}))
            if day is not None and self._has_positions(day):
                return candidate, day
        raise ValueError(f"期交所近 {self.lookback_days} 日查無完整三大法人資料")

    @classmethod
    def _parse_institutional(cls, rows: list[list[str]]) -> dict[str, dict[str, dict[str, dict[str, int]]]]:
        if not rows:
            return {}
        header = rows[0]
        i_date = cls._column(header, "日期")
        i_product = cls._column(header, "商品名稱")
        i_role = cls._column(header, "身份別")
        if i_role is None:
            i_role = cls._column(header, "身分別")
        i_long = cls._column(header, "多方", "未平倉", "口數")
        i_short = cls._column(header, "空方", "未平倉", "口數")
        required = (i_date, i_product, i_role, i_long, i_short)
        if any(index is None for index in required):
            raise ValueError("期交所三大法人 CSV 表頭已變更")
        result: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
        last_index = max(index for index in required if index is not None)
        for row in rows[1:]:
            if len(row) <= last_index:
                continue
            long_value = cls._integer(row[i_long])
            short_value = cls._integer(row[i_short])
            if long_value is None or short_value is None:
                continue
            day = row[i_date].strip().replace("/", "-")
            product = row[i_product].strip()
            role = row[i_role].strip()
            result.setdefault(day, {}).setdefault(product, {})[role] = {
                "long": long_value,
                "short": short_value,
            }
        return result

    @classmethod
    def _normalize_institutional(
        cls, day: dict[str, dict[str, dict[str, int]]]
    ) -> dict[str, dict[str, dict[str, int]]] | None:
        normalized: dict[str, dict[str, dict[str, int]]] = {}
        for code, product_name in cls.products.items():
            source_roles = day.get(product_name, {})
            target_roles: dict[str, dict[str, int]] = {}
            for target in cls.roles:
                matches = [values for name, values in source_roles.items() if target in name]
                if not matches:
                    return None
                long_value = sum(values["long"] for values in matches)
                short_value = sum(values["short"] for values in matches)
                if long_value < 0 or short_value < 0:
                    return None
                target_roles[target] = {
                    "long": long_value,
                    "short": short_value,
                    "net": long_value - short_value,
                }
            normalized[code] = target_roles
        return normalized

    @staticmethod
    def _has_positions(day: dict[str, dict[str, dict[str, int]]]) -> bool:
        return any(
            values[side]
            for roles in day.values()
            for values in roles.values()
            for side in ("long", "short")
        )

    def _market_open_interest(self, code: str, trading_date: date) -> int:
        rows = self._post_csv(
            "https://www.taifex.com.tw/cht/3/futDataDown",
            {
                "down_type": "1",
                "commodity_id": code,
                "queryStartDate": trading_date.strftime("%Y/%m/%d"),
                "queryEndDate": trading_date.strftime("%Y/%m/%d"),
            },
            "https://www.taifex.com.tw/cht/3/futDailyMarketReport",
        )
        total = self._parse_market_open_interest(rows, trading_date.isoformat())
        if total <= 0:
            raise ValueError(f"期交所 {code} 全市場未平倉資料不足")
        return total

    @classmethod
    def _parse_market_open_interest(cls, rows: list[list[str]], target_date: str) -> int:
        if not rows:
            return 0
        header = rows[0]
        i_date = cls._column(header, "交易日期")
        i_month = cls._column(header, "到期月份")
        i_oi = cls._column(header, "未沖銷契約")
        i_session = cls._column(header, "交易時段")
        if any(index is None for index in (i_date, i_month, i_oi)):
            raise ValueError("期交所每日行情 CSV 表頭已變更")
        total = 0
        for row in rows[1:]:
            if len(row) <= i_oi:
                continue
            day = row[i_date].strip().replace("/", "-")
            month = row[i_month].strip()
            if day != target_date or "/" in month:
                continue
            if i_session is not None and len(row) > i_session and "一般" not in row[i_session]:
                continue
            value = cls._integer(row[i_oi])
            if value is not None:
                total += value
        return total

    @classmethod
    def _retail_ratios(
        cls,
        institutional: dict[str, dict[str, dict[str, int]]],
        totals: dict[str, int],
    ) -> dict[str, float]:
        result: dict[str, float] = {}
        for code in cls.products:
            total = totals[code]
            institutional_long = sum(values["long"] for values in institutional[code].values())
            institutional_short = sum(values["short"] for values in institutional[code].values())
            if institutional_long > total or institutional_short > total:
                raise ValueError(f"期交所 {code} 法人未平倉合計超過全市場")
            retail_long = total - institutional_long
            retail_short = total - institutional_short
            result[code] = round((retail_long - retail_short) / total * 100, 2)
        return result

    def _pc_ratio(self, trading_date: date) -> tuple[str, float]:
        rows = self._post_csv(
            "https://www.taifex.com.tw/cht/3/pcRatioDown",
            {
                "queryStartDate": (trading_date - timedelta(days=10)).strftime("%Y/%m/%d"),
                "queryEndDate": trading_date.strftime("%Y/%m/%d"),
            },
            "https://www.taifex.com.tw/cht/3/pcRatio",
        )
        if not rows:
            raise ValueError("期交所 P/C 比查無資料")
        header = rows[0]
        i_date = self._column(header, "日期")
        i_ratio = self._column(header, "買賣權未平倉量比率")
        if i_ratio is None:
            i_ratio = self._column(header, "未平倉量比率")
        if i_date is None or i_ratio is None:
            raise ValueError("期交所 P/C 比 CSV 表頭已變更")
        valid: list[tuple[str, float]] = []
        for row in rows[1:]:
            if len(row) <= i_ratio:
                continue
            value = self._number(row[i_ratio])
            if value is not None:
                valid.append((row[i_date].strip().replace("/", "-"), value))
        if not valid:
            raise ValueError("期交所 P/C 比無有效數值")
        return max(valid, key=lambda item: item[0])

    def _tsmc_impact(self, trading_date: date) -> float:
        stamp = trading_date.strftime("%Y%m%d")
        index_payload = self.client.get_json(
            f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={stamp}&response=json"
        )
        stock_payload = self.client.get_json(
            f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&stockNo=2330&date={stamp}"
        )
        index_close = self._twse_value(index_payload, trading_date, 4)
        tsmc_close = self._twse_value(stock_payload, trading_date, 6)
        weight = self._tsmc_weight(
            self.client.get_text("https://www.taifex.com.tw/cht/2/weightedPropertion")
        )
        if index_close is None or tsmc_close is None or tsmc_close <= 0 or weight is None:
            raise ValueError("台積電大盤影響點數所需官方資料不足")
        return round(index_close * (weight / 100) / tsmc_close, 3)

    @classmethod
    def _twse_value(cls, payload: object, trading_date: date, value_index: int) -> float | None:
        if not isinstance(payload, dict):
            return None
        target = trading_date.isoformat()
        for row in payload.get("data") or []:
            if not isinstance(row, list) or len(row) <= value_index:
                continue
            try:
                year, month, day = (int(part) for part in str(row[0]).split("/"))
            except ValueError:
                continue
            if f"{year + 1911:04d}-{month:02d}-{day:02d}" == target:
                return cls._number(row[value_index])
        return None

    @staticmethod
    def _tsmc_weight(page: str) -> float | None:
        text = html.unescape(re.sub(r"<[^>]+>", " ", page))
        text = re.sub(r"\s+", " ", text)
        for pattern in (
            r"2330\s*台積電\s*([0-9]+(?:\.[0-9]+)?)\s*%",
            r"台積電\s*([0-9]+(?:\.[0-9]+)?)\s*%",
            r"2330\D{0,30}?([0-9]+(?:\.[0-9]+)?)\s*%",
        ):
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        return None

    def _post_csv(self, url: str, fields: dict[str, str], referer: str) -> list[list[str]]:
        raw = self.client.post_form_bytes(url, fields, referer)
        for encoding in ("utf-8-sig", "big5", "cp950", "utf-8"):
            try:
                return list(csv.reader(io.StringIO(raw.decode(encoding))))
            except UnicodeDecodeError:
                continue
        raise UnicodeError("期交所 CSV 編碼無法辨識")

    @staticmethod
    def _column(header: list[str], *keywords: str) -> int | None:
        for index, value in enumerate(header):
            compact = (value or "").replace(" ", "")
            if all(keyword in compact for keyword in keywords):
                return index
        return None

    @staticmethod
    def _number(value: object) -> float | None:
        cleaned = str(value).replace(",", "").replace("%", "").replace(" ", "").strip()
        if cleaned in {"", "-", "--"}:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @classmethod
    def _integer(cls, value: object) -> int | None:
        number = cls._number(value)
        return None if number is None else int(number)
