#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare Client - Tushare API客户端封装
专门负责与Tushare API的直接交互

注意：使用自定义API域名（高积分用户专用）
"""

import tushare as ts
import tushare.pro.client as client
from typing import Dict, Optional, List

# 【重要】全局设置自定义API域名（高积分用户专用，速度更快）
# 必须在创建任何 ts.pro_api() 实例之前设置
client.DataApi._DataApi__http_url = "http://tushare.xyz"


class TushareClient:
    """Tushare客户端（使用官方SDK）"""
    
    def __init__(self, token: str):
        """
        初始化API调用器
        
        Args:
            token: Tushare token
        """
        self.token = token
        self.base_url = "http://tushare.xyz"
        
        # 使用官方SDK（已配置自定义域名）
        self.pro = ts.pro_api(token)
        
        # 请求计数（用于统计）
        self._request_count = 0
    
    def get_stock_daily(self, ts_code: str, trade_date: str = "") -> Optional[Dict]:
        """
        获取股票日线数据（使用官方SDK）
        
        Args:
            ts_code: Tushare股票代码（如 000001.SZ）
            trade_date: 交易日期（格式：20260226，留空则获取最近一条）
            
        Returns:
            日线数据字典
        """
        try:
            # 如果没有指定日期，使用 start_date 限制只返回最近数据
            if trade_date:
                df = self.pro.daily(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            else:
                # 获取最近1条数据（避免返回全部历史数据导致超时）
                import datetime
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y%m%d')
                df = self.pro.daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            
            if df is None or df.empty:
                # 静默返回 None（由上层处理重试）
                return None
            
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            print(f"Tushare API错误: {e}")
            return None
    
    def get_index_daily(self, ts_code: str, trade_date: str = "") -> Optional[Dict]:
        """
        获取指数日线数据（使用官方SDK）
        
        Args:
            ts_code: Tushare指数代码（如 000001.SH）
            trade_date: 交易日期（格式：20260226，留空则获取最近一条）
            
        Returns:
            指数日线数据字典
        """
        try:
            # 如果没有指定日期，使用 start_date 限制只返回最近数据
            if trade_date:
                df = self.pro.index_daily(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            else:
                # 获取最近1条数据（避免返回全部历史数据导致超时）
                import datetime
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y%m%d')
                df = self.pro.index_daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            
            if df is None or df.empty:
                return None
            
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            print(f"Tushare API错误: {e}")
            return None
    
    def get_stock_basic(self, ts_code: str) -> Optional[Dict]:
        """
        获取股票基本信息（使用官方SDK）
        
        Args:
            ts_code: Tushare股票代码
            
        Returns:
            股票基本信息字典
        """
        try:
            df = self.pro.stock_basic(
                ts_code=ts_code,
                fields='ts_code,name,area,industry,market,list_date'
            )
            
            if df is None or df.empty:
                return None
            
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            print(f"Tushare API错误: {e}")
            return None


    def get_stock_intraday(self, ts_code: str, trade_date: str, freq: str = '1min') -> Optional[Dict]:
        """
        获取股票分时数据（使用官方SDK）
        
        Args:
            ts_code: Tushare股票代码（如 000001.SZ）
            trade_date: 交易日期（格式：20260226）
            freq: 数据频度（1min/5min/15min/30min/60min）
            
        Returns:
            分时数据字典 {'items': [[...], [...]], 'fields': [...]}
            
        注意：需要 5000 积分权限
        """
        try:
            # 转换日期格式：20260226 -> 2026-02-26 09:00:00
            from datetime import datetime
            date_obj = datetime.strptime(trade_date, '%Y%m%d')
            start_time = date_obj.strftime('%Y-%m-%d 09:00:00')
            end_time = date_obj.strftime('%Y-%m-%d 19:00:00')
            
            # 调用官方SDK的分钟线接口（使用start_date和end_date参数）
            df = self.pro.stk_mins(
                ts_code=ts_code,
                freq=freq,
                start_date=start_time,
                end_date=end_time,
                fields='ts_code,trade_time,open,high,low,close,vol,amount'
            )
            
            if df is None or df.empty:
                return None
            
            self._request_count += 1
            
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            # 权限不足或其他错误
            if '没有访问权限' in str(e) or 'Permission denied' in str(e):
                print(f"⚠️  分时接口需要5000积分权限: {e}")
            else:
                print(f"Tushare API错误: {e}")
            return None


    def get_trade_calendar(self, start_date: str, end_date: str, exchange: str = 'SSE') -> List[str]:
        """
        获取交易日历
        
        Args:
            start_date: 开始日期（格式：20260101 或 2026-01-01）
            end_date: 结束日期（格式：20260131 或 2026-01-31）
            exchange: 交易所代码（SSE=上交所, SZSE=深交所）
            
        Returns:
            交易日列表（格式：YYYY-MM-DD）
        """
        try:
            # 统一日期格式为 YYYYMMDD
            start = start_date.replace('-', '')
            end = end_date.replace('-', '')
            
            df = self.pro.trade_cal(
                exchange=exchange,
                start_date=start,
                end_date=end,
                is_open='1'  # 只返回开市日期
            )
            
            if df is None or df.empty:
                return []
            
            # 转换为 YYYY-MM-DD 格式
            dates = df['cal_date'].tolist()
            return [f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in dates]
            
        except Exception as e:
            print(f"Tushare API错误 (交易日历): {e}")
            return []


    def get_limit_list(self, trade_date: str, limit_type: str = None) -> Optional[Dict]:
        """
        获取涨跌停列表（使用官方SDK）
        
        Args:
            trade_date: 交易日期（格式：20260226）
            limit_type: 涨跌停类型（U=涨停, D=跌停, Z=炸板, None=全部）
            
        Returns:
            涨跌停数据字典 {'items': [[...], [...]], 'fields': [...]}
        """
        try:
            # 使用官方SDK调用（支持自定义域名）
            df = self.pro.limit_list_d(
                trade_date=trade_date,
                limit_type=limit_type,
                fields='ts_code,trade_date,name,limit,limit_times,pct_chg'
            )
            
            if df is None or df.empty:
                return None
            
            # 转换为与_post相同的格式
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            print(f"Tushare API错误: {e}")
            return None


# 模块级别初始化全局客户端实例
def _init_tushare_client() -> TushareClient:
    """初始化Tushare客户端"""
    from config_loader import ConfigLoader
    config = ConfigLoader()
    token = config.get_tushare_token()
    if not token:
        raise ValueError("未配置 Tushare Token，请在 config.yaml 中设置 tushare.token")
    return TushareClient(token)

# 全局客户端实例（直接导入使用）
tushare_client = _init_tushare_client()


def main():
    """测试Tushare客户端"""
    print("="*60)
    print("Tushare Client 测试")
    print("="*60)
    
    # 测试获取股票数据
    print("\n测试1: 获取股票日线数据")
    data = tushare_client.get_stock_daily("000001.SZ")
    if data and data.get('items'):
        item = data['items'][0]
        print(f"✅ 平安银行: 收盘价 {item[5]}, 涨跌幅 {item[8]:+.2f}%")
    else:
        print("❌ 获取失败")
    
    # 测试获取指数数据
    print("\n测试2: 获取指数日线数据")
    data = tushare_client.get_index_daily("000001.SH")
    if data and data.get('items'):
        item = data['items'][0]
        print(f"✅ 上证指数: {item[5]:.2f} ({item[8]:+.2f}%)")
    else:
        print("❌ 获取失败")
    
    # 测试获取涨跌停列表
    print("\n测试3: 获取涨跌停列表")
    import datetime
    # 使用昨天的日期（当天数据可能还未生成）
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y%m%d')
    data = tushare_client.get_limit_list(yesterday)
    if data and data.get('items'):
        items = data['items']
        # 统计各类型数量
        stats = {}
        for item in items:
            limit_type = item[3]
            stats[limit_type] = stats.get(limit_type, 0) + 1
        
        print(f"✅ 获取 {len(items)} 条记录（日期: {yesterday}）")
        print(f"   涨停(U): {stats.get('U', 0)} 只")
        print(f"   跌停(D): {stats.get('D', 0)} 只")
        print(f"   炸板(Z): {stats.get('Z', 0)} 只")
    else:
        print(f"❌ 获取失败（日期: {yesterday}）")
    
    print(f"\n总请求数: {tushare_client._request_count}")
    print("\n✅ Tushare客户端测试完成！")


if __name__ == "__main__":
    main()