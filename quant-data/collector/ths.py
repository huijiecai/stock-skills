"""
同花顺历史行情 v6 接口
接口: https://d.10jqka.com.cn/v6/line/hs_{code}/{period}/last.js
返回 JSONP: quotebridge_v6_line_hs_600519_01_last({...})

period 编码（v6 last.js，无需鉴权）:
    01 = 日K       11 = 周K       21 = 月K
分钟级别（5/15/30/60）需要 Cookie 认证（本模块未实现）
"""
import json
import re
import time
import requests
from typing import Optional


BASE = "https://d.10jqka.com.cn/v6/line"

PERIOD_MAP = {
    "1d": "01",
    "1w": "11",
    "1M": "21",
}

DEFAULT_HEADERS = {
    "Referer": "https://stockpage.10jqka.com.cn/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}


# 指数标准代码 → 同花顺 v6 内部编码
INDEX_THS_CODE = {
    "000001": "zs_1A0001",   # 上证指数
    "399001": "zs_399001",   # 深证成指
    "399006": "zs_399006",   # 创业板指
    "000688": "zs_1B0688",   # 科创50
}

# 同花顺概念名称 → 概念指数编码 (8xxxxx)
# 由 AData all_concept_code_ths() 一次性导出，储存在 data/ths_concept_map.json
def _load_concept_map() -> dict:
    from pathlib import Path
    map_file = Path(__file__).resolve().parent.parent / "data" / "ths_concept_map.json"
    if map_file.exists():
        return json.loads(map_file.read_text())
    return {}


class THSClient:
    """同花顺历史行情采集（免鉴权 v6 last.js）"""

    def __init__(self, retry: int = 3, delay: float = 0.5):
        self.retry = retry
        self.delay = delay

    def _get(self, url: str) -> Optional[dict]:
        time.sleep(self.delay)
        for i in range(self.retry):
            try:
                resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
                if resp.status_code != 200:
                    time.sleep(1.0 * (i + 1))
                    continue
                text = resp.text.strip()
                # 剥 JSONP 外壳: fn_xxx({...});
                m = re.search(r"\((\{.*\})\)\s*;?\s*$", text, re.DOTALL)
                if not m:
                    return None
                return json.loads(m.group(1))
            except Exception:
                if i < self.retry - 1:
                    time.sleep(2.0 * (i + 1))
        return None

    def _parse_raw(self, raw: str) -> list[dict]:
        """解析同花顺 data 字段: '日期,开,高,低,收,量,额,换手率;...'"""
        result = []
        for line in raw.split(";"):
            parts = line.split(",")
            if len(parts) < 7:
                continue
            try:
                dt_str = parts[0]
                if len(dt_str) == 8:
                    dt = f"{dt_str[0:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
                else:
                    continue
                result.append({
                    "trade_date": dt,
                    "open":   float(parts[1]),
                    "high":   float(parts[2]),
                    "low":    float(parts[3]),
                    "close":  float(parts[4]),
                    "volume": int(float(parts[5])),
                    "amount": float(parts[6]),
                    "turnover": float(parts[7]) if len(parts) > 7 and parts[7] else 0.0,
                })
            except (ValueError, IndexError):
                continue
        return result

    def get_history_kline(self, code: str, period: str = "1d") -> list[dict]:
        """
        获取个股历史 K 线（前复权），最长可达上市以来完整历史
        :param code: 6位代码（沪深，如 600519）
        :param period: 1d / 1w / 1M
        :return: [{trade_date, open, high, low, close, volume, amount, turnover}, ...]
        """
        pcode = PERIOD_MAP.get(period)
        if not pcode:
            return []
        url = f"{BASE}/hs_{code}/{pcode}/last.js"
        data = self._get(url)
        if not data:
            return []
        raw = data.get("data", "")
        return self._parse_raw(raw) if raw else []

    def get_index_kline(self, code: str, period: str = "1d") -> list[dict]:
        """
        获取指数日K（同花顺 zs_ 前缀免鉴权接口）
        :param code: 标准指数代码（如 000001）或同花顺内部编码（如 zs_1A0001）
        :param period: 1d / 1w / 1M
        """
        pcode = PERIOD_MAP.get(period)
        if not pcode:
            return []
        # 支持传入标准代码或内部编码
        ths_code = INDEX_THS_CODE.get(code, code)
        url = f"{BASE}/{ths_code}/{pcode}/last.js"
        data = self._get(url)
        if not data:
            return []
        raw = data.get("data", "")
        return self._parse_raw(raw) if raw else []

    def get_kline(self, code: str, tp: str = "stock", period: str = "1d") -> list[dict]:
        """
        统一入口: stock → get_history_kline, index → get_index_kline
        """
        if tp == "index":
            return self.get_index_kline(code, period)
        if tp == "concept":
            return self.get_concept_kline(code, period)
        return self.get_history_kline(code, period)

    def get_concept_kline(self, name_or_code: str, period: str = "1d") -> list[dict]:
        """
        获取同花顺概念板块日K
        URL: http://d.10jqka.com.cn/v6/line/48_{8xxxxx}/01/last1800.js
        :param name_or_code: 概念名称（如 "存储芯片"）或8开头的同花顺概念指数代码
        :param period: 1d / 1w / 1M
        """
        pcode = PERIOD_MAP.get(period)
        if not pcode:
            return []
        # 如果是8开头的数字，直接用作代码
        if name_or_code.isdigit() and name_or_code.startswith("8"):
            ths_code = name_or_code
        else:
            # 按名称查找
            cmap = _load_concept_map()
            ths_code = cmap.get(name_or_code)
            if not ths_code:
                return []
        url = f"{BASE}/48_{ths_code}/{pcode}/last1800.js"
        data = self._get(url)
        if not data:
            return []
        raw = data.get("data", "")
        return self._parse_raw(raw) if raw else []

    def get_concept_code_by_name(self, name: str) -> str:
        """根据名称查同花顺概念指数代码"""
        return _load_concept_map().get(name, "")


if __name__ == "__main__":
    client = THSClient()
    rows = client.get_history_kline("600519", "1d")
    print(f"茅台 日K: {len(rows)} 条")
    if rows:
        print("首条:", rows[0])
        print("末条:", rows[-1])
    # 测试指数
    idx = client.get_index_kline("000001")
    print(f"\n上证指数 日K: {len(idx)} 条, 末条: {idx[-1] if idx else 'N/A'}")
