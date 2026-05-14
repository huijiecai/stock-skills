"""
东方财富行情HTTP客户端
纯requests，零外部依赖，无Cookie/Token/签名
所有接口均为 secid 驱动的统一设计
"""
import json
import time
import requests
from typing import Optional


BASE_HIS = "http://push2his.eastmoney.com"
BASE_PUSH = "https://push2.eastmoney.com"

# 必需请求头：东方财富从 2026 年起要求 Referer，否则直接关闭连接
DEFAULT_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

# secid 前缀映射
def _secid(code: str, tp: str = "stock") -> str:
    """构建东方财富 secid
    - stock: 1.600519(沪) / 0.000001(深/北)
    - index: 1.000001(沪指) / 0.399001(深指)
    - concept: 90.BK0612
    """
    if tp == "concept":
        return f"90.{code}"
    if tp == "index":
        prefix = "1" if code.startswith("000") or code.startswith("688") else "0"
        return f"{prefix}.{code}"
    # stock
    prefix = "1" if code.startswith("6") else "0"
    return f"{prefix}.{code}"


class EastmoneyClient:
    """东方财富行情采集"""

    def __init__(self, retry: int = 3, delay: float = 0.3):
        self.retry = retry
        self.delay = delay  # 请求间隔，防止IP封禁

    def _get(self, url: str, params: dict, retry: int = None) -> dict:
        """带重试和速率控制的GET请求"""
        if retry is None:
            retry = self.retry
        # 请求前等待，控制速率
        time.sleep(self.delay)
        for i in range(retry):
            try:
                resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=15)
                if resp.status_code == 200:
                    return resp.json()
                # 非200状态码，等待后重试
                time.sleep(1.0 * (i + 1))
            except Exception:
                if i < retry - 1:
                    time.sleep(2.0 * (i + 1))  # 连接失败等更久
        return {}

    # ─── 日K (个股/指数/概念 统一) ───

    def get_daily_kline(self, code: str, tp: str = "stock",
                        days: int = 30) -> list[dict]:
        """
        获取日K线，返回近N天数据
        :param code: 股票/指数/概念代码
        :param tp: stock / index / concept
        :param days: 返回最近多少天
        :return: [{trade_date, open, high, low, close, pre_close,
                   change_pct, volume, amount, turnover}, ...]
        """
        sid = _secid(code, tp)
        # 指数/概念用不同的ut
        ut = "fa5fd1943c7b386f172d6893dbfba10b" if tp in ("index", "concept") \
            else "7eea3edcaed734bea9cbfc24409ed989"
        
        params = {
            "secid": sid,
            "klt": "101",  # 日K
            "fqt": "1",    # 前复权
            "beg": "19900101",
            "end": "20500101",
            "lmt": str(days + 10),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
            "ut": ut,
        }
        data = self._get(f"{BASE_HIS}/api/qt/stock/kline/get", params)
        if not data or not data.get("data"):
            return []
        
        klines = data["data"].get("klines", [])
        result = []
        for line in klines:
            parts = str(line).split(",")
            if len(parts) < 11:
                continue
            result.append({
                "trade_date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": int(float(parts[5])),
                "amount": float(parts[6]),
                "change_pct": float(parts[8]) if parts[8] else 0.0,
                "change": float(parts[9]) if parts[9] else 0.0,
                "turnover": float(parts[10]) if len(parts) > 10 and parts[10] else 0.0,
            })
        # 计算 pre_close
        for r in result:
            r["pre_close"] = round(r["close"] - r.get("change", 0), 2)
        
        # 只保留最近N天
        return result[-days:] if len(result) > days else result

    # ─── 分钟K / 当日分时 ───

    def get_minute_trends(self, code: str, tp: str = "stock") -> list[dict]:
        """
        获取当日分时数据 (1分钟粒度)
        :return: [{trade_time, price, open, high, low, volume, amount,
                   avg_price, change, change_pct, pre_close}, ...]
        """
        sid = _secid(code, tp)
        ut = "fa5fd1943c7b386f172d6893dbfba10b" if tp in ("index", "concept") \
            else "fa5fd1943c7b386f172d6893dbfba10b"

        params = {
            "secid": sid,
            "ndays": "1",
            "iscr": "1" if tp == "stock" else "0",
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "ut": ut,
        }
        data = self._get(f"{BASE_PUSH}/api/qt/stock/trends2/get", params)
        if not data or not data.get("data"):
            return []

        trends = data["data"].get("trends", [])
        pre_close = float(data["data"].get("preClose", 0))
        result = []
        for line in trends:
            parts = str(line).split(",")
            if len(parts) < 8:
                continue
            price = float(parts[2])
            result.append({
                "trade_time": parts[0],
                "open": float(parts[1]),
                "price": price,
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": int(float(parts[5])),
                "amount": float(parts[6]),
                "avg_price": float(parts[7]) if parts[7] else price,
                "change": round(price - pre_close, 2),
                "change_pct": round((price - pre_close) / pre_close * 100, 2) if pre_close else 0,
                "pre_close": pre_close,
            })
        return result

    # ─── 概念列表 ───

    def get_concept_list(self) -> list[dict]:
        """
        获取东方财富全部概念板块
        :return: [{code, name, stock_count}, ...]
        """
        all_data = []
        page = 1
        while page < 50:
            params = {
                "pn": str(page),
                "pz": "100",
                "po": "1",
                "np": "1",
                "fid": "f62",
                "fs": "m:90+t:3",
                "fields": "f12,f13,f14,f62",
            }
            data = self._get(f"{BASE_PUSH}/api/qt/clist/get", params, retry=2)
            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break
            for item in diff:
                all_data.append({
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "stock_count": item.get("f62", 0),
                })
            if len(diff) < 100:
                break
            page += 1
        return all_data

    # ─── 概念成分股 ───

    def get_concept_constituents(self, concept_code: str) -> list[dict]:
        """
        获取概念板块成分股
        :return: [{stock_code, stock_name}, ...]
        """
        all_data = []
        page = 1
        while page < 100:
            params = {
                "pn": str(page),
                "pz": "200",
                "fid": "f62",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fs": f"b:{concept_code}",
                "fields": "f12,f14",
            }
            data = self._get(f"{BASE_PUSH}/api/qt/clist/get", params, retry=2)
            diff = data.get("data", {}).get("diff", [])
            if not diff:
                break
            for item in diff:
                all_data.append({
                    "stock_code": item.get("f12", ""),
                    "stock_name": item.get("f14", ""),
                })
            if len(diff) < 200:
                break
            page += 1
        return all_data

    # ─── 股票列表 (全A股) ───

    def get_stock_list(self) -> list[dict]:
        """
        获取全部A股列表
        fs: m:0+t:6(深主板) + m:0+t:13(创业板) + m:1+t:2(沪主板)
            + m:1+t:23(科创板) + m:0+t:81(北交所)
        """
        markets = [
            ("m:0+t:6", "sz"),     # 深证主板
            ("m:0+t:13", "sz"),    # 创业板
            ("m:1+t:2", "sh"),     # 上证主板
            ("m:1+t:23", "sh"),    # 科创板
            ("m:0+t:81", "bj"),    # 北交所
        ]
        all_stocks = {}
        for fs, exchange in markets:
            page = 1
            while page < 100:
                params = {
                    "pn": str(page),
                    "pz": "500",
                    "po": "1",
                    "np": "1",
                    "fid": "f3",
                    "fs": fs,
                    "fields": "f12,f14",
                }
                data = self._get(f"{BASE_PUSH}/api/qt/clist/get", params, retry=2)
                diff = data.get("data", {}).get("diff", [])
                if not diff:
                    break
                for item in diff:
                    code = item.get("f12", "")
                    if code not in all_stocks:
                        all_stocks[code] = {
                            "code": code,
                            "name": item.get("f14", ""),
                            "exchange": exchange,
                        }
                if len(diff) < 500:
                    break
                page += 1
        return list(all_stocks.values())


if __name__ == "__main__":
    client = EastmoneyClient()
    # 测试个股日K
    daily = client.get_daily_kline("600519", "stock", 5)
    print(f"茅台日K: {len(daily)} 条")
    if daily:
        print(json.dumps(daily[-1], ensure_ascii=False, indent=2))

    # 测试分时
    trends = client.get_minute_trends("600519")
    print(f"\n茅台分时: {len(trends)} 条")
    
    # 测试概念列表
    concepts = client.get_concept_list()
    print(f"\n概念板块: {len(concepts)} 个")
