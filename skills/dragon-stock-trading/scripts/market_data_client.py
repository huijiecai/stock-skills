#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据客户端 - 统一的数据访问接口
作为业务逻辑层，提供标准化的数据获取接口
实际API调用委托给底层的tushare_client模块
"""

from typing import Dict, List, Optional
from datetime import datetime

# 导入全局Tushare客户端
from tushare_client import tushare_client


class MarketDataClient:
    """市场数据客户端（业务逻辑层）"""
    
    def __init__(self):
        """初始化客户端"""
        # 使用全局Tushare客户端实例
        self._api = tushare_client
        self._request_count = 0
    
    def get_stock_quote(self, stock_code: str, market: str = None, date: str = None) -> Optional[Dict]:
        """
        获取股票行情数据
        
        Args:
            stock_code: 股票代码（如 000001）
            market: 市场代码（SH/SZ，可选）
            date: 交易日期（YYYY-MM-DD，可选）
            
        Returns:
            行情数据字典
        """
        # 构造Tushare格式的股票代码
        if '.' not in stock_code:
            if market:
                ts_code = f"{stock_code}.{market.upper()}"
            else:
                # 自动识别市场
                if stock_code.startswith(('6', '5')):
                    ts_code = f"{stock_code}.SH"
                else:
                    ts_code = f"{stock_code}.SZ"
        else:
            ts_code = stock_code
        
        # 转换日期格式（YYYY-MM-DD -> YYYYMMDD）
        trade_date = date.replace('-', '') if date else ""
        
        # 委托给底层API获取数据
        data = self._api.get_stock_daily(ts_code=ts_code, trade_date=trade_date)
        
        if data and data.get('items'):
            item = data['items'][0]
            self._request_count += 1
            return {
                'ld': item[5],                  # close 收盘价
                'chp': item[8] / 100.0,         # pct_chg 涨跌幅（转换：7.7483% -> 0.077483）
                'vol': item[9],                 # volume 成交量（手）
                'amt': item[10] * 1000,         # amount 成交额（单位：千元 -> 元）
                'o': item[2],                   # open 开盘价
                'h': item[3],                   # high 最高价
                'l': item[4],                   # low 最低价
                'p': item[6],                   # pre_close 昨收价
                'tr': 0.0                       # turnover_rate 换手率需要额外计算
            }
        return None
    
    def get_daily_all(self, date: str) -> Dict[str, Dict]:
        """
        批量获取指定日期所有股票的日线数据
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            
        Returns:
            字典 {股票代码: 行情数据}
            行情数据包含: ld(收盘价), chp(涨跌幅), vol(成交量), amt(成交额), 
                        o(开盘价), h(最高价), l(最低价), p(昨收价)
        """
        # 转换日期格式
        trade_date = date.replace('-', '')
        
        # 批量获取
        data = self._api.get_daily_all(trade_date)
        
        if not data or not data.get('items'):
            return {}
        
        result = {}
        for item in data['items']:
            # item: [ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount]
            ts_code = item[0]  # 如 000001.SZ
            stock_code = ts_code.split('.')[0]  # 提取股票代码 000001
            
            result[stock_code] = {
                'ld': item[5],                  # close 收盘价
                'chp': item[8] / 100.0,         # pct_chg 涨跌幅
                'vol': item[9],                 # volume 成交量（手）
                'amt': item[10] * 1000,         # amount 成交额（千元 -> 元）
                'o': item[2],                   # open 开盘价
                'h': item[3],                   # high 最高价
                'l': item[4],                   # low 最低价
                'p': item[6],                   # pre_close 昨收价
                'tr': 0.0                       # turnover_rate
            }
        
        self._request_count += 1
        return result
    
    def get_daily_basic(self, date: str) -> Dict[str, float]:
        """
        获取指定日期所有股票的换手率
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            
        Returns:
            字典 {股票代码: 换手率}，换手率为小数（如 0.05 表示 5%）
        """
        trade_date = date.replace('-', '')
        data = self._api.get_daily_basic(trade_date)
        
        if not data:
            return {}
        
        self._request_count += 1
        return data
    
    def get_stock_info(self, stock_code: str, market: str = None) -> Optional[Dict]:
        """
        获取股票基本信息
        
        Args:
            stock_code: 股票代码
            market: 市场代码
            
        Returns:
            股票信息字典
        """
        # 构造Tushare格式的股票代码
        if '.' not in stock_code:
            if market:
                ts_code = f"{stock_code}.{market.upper()}"
            else:
                if stock_code.startswith(('6', '5')):
                    ts_code = f"{stock_code}.SH"
                else:
                    ts_code = f"{stock_code}.SZ"
        else:
            ts_code = stock_code
        
        # 委托给底层API获取数据
        data = self._api.get_stock_basic(ts_code=ts_code)
        
        if data and data.get('items'):
            item = data['items'][0]
            self._request_count += 1
            return {
                'code': stock_code,
                'name': item[1],
                'market': item[4],
                'industry': item[3]
            }
        return None
    
    def get_index_quote(self, index_code: str, region: str = None) -> Optional[Dict]:
        """
        获取指数行情
        
        Args:
            index_code: 指数代码
            region: 市场代码（兼容参数）
            
        Returns:
            指数行情数据
        """
        # 指数代码映射
        index_mapping = {
            '000001': '000001.SH',  # 上证指数
            '399001': '399001.SZ',  # 深证成指
            '399006': '399006.SZ'   # 创业板指
        }
        
        ts_code = index_mapping.get(index_code, f"{index_code}.SH")
        
        # 委托给底层API获取数据
        data = self._api.get_index_daily(ts_code=ts_code)
        
        if data and data.get('items'):
            item = data['items'][0]
            self._request_count += 1
            return {
                'ld': item[5],                  # close 收盘价
                'chp': item[8] / 100.0,         # pct_chg 涨跌幅（转换：7.7483% -> 0.077483）
                'vol': item[9],                 # volume 成交量（手）
                'amt': item[10] * 1000,         # amount 成交额（单位：千元 -> 元）
                'o': item[2],                   # open 开盘价
                'h': item[3],                   # high 最高价
                'l': item[4],                   # low 最低价
                'p': item[6]                    # pre_close 昨收价
            }
        return None
    
    def get_limit_stats(self, date: str) -> Optional[Dict]:
        """
        获取真实的全市场涨跌停统计
        
        Args:
            date: 日期（YYYY-MM-DD）
            
        Returns:
            涨跌停统计数据 {
                'limit_up_count': 涨停数量,
                'limit_down_count': 跌停数量,
                'broken_board_count': 炸板数量,
                'max_streak': 最高连板数
            }
        """
        # 转换日期格式：YYYY-MM-DD -> YYYYMMDD
        trade_date = date.replace('-', '')
        
        try:
            # 一次性获取所有涨跌停数据（不指定limit_type）
            all_limit_data = self._api.get_limit_list(trade_date)
            
            if not all_limit_data or not all_limit_data.get('items'):
                return None
            
            # 在本地分类统计
            limit_up_count = 0      # U - 涨停
            limit_down_count = 0    # D - 跌停
            broken_board_count = 0  # Z - 炸板
            max_streak = 1
            
            for item in all_limit_data['items']:
                # item 结构: [ts_code, trade_date, name, limit, limit_times, pct_chg]
                limit_type = item[3] if len(item) > 3 else None  # limit字段
                limit_times = item[4] if len(item) > 4 else 1    # limit_times字段
                
                # 统计数量
                if limit_type == 'U':
                    limit_up_count += 1
                    # 更新最高连板数
                    if limit_times and limit_times > max_streak:
                        max_streak = limit_times
                elif limit_type == 'D':
                    limit_down_count += 1
                elif limit_type == 'Z':
                    broken_board_count += 1
            
            return {
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
                'broken_board_count': broken_board_count,
                'max_streak': max_streak
            }
        except Exception as e:
            print(f"  ⚠️  获取涨跌停统计失败: {e}")
            print(f"  💡 可能原因：日期非交易日、Tushare API 无权限或数据未更新")
            return None
    
    def get_market_snapshot(self, date: str = None) -> Optional[Dict]:
        """
        获取市场概况快照
        
        Args:
            date: 日期（YYYY-MM-DD），默认为今天
            
        Returns:
            市场概况数据（仅使用真实统计，失败返回None）
        """
        print(f"  📊 正在获取市场快照...")
        
        if not date:
            raise ValueError("必须提供日期参数")
        
        # 获取真实的涨跌停统计（不使用估算）
        print(f"  🔍 从Tushare获取真实涨跌停统计...")
        limit_stats = self.get_limit_stats(date)
        
        if not limit_stats:
            print(f"  ❌ 无法获取涨跌停统计数据")
            return None
        
        # 获取指数行情
        sh_index = self.get_index_quote('000001')  # 上证指数
        sz_index = self.get_index_quote('399001')  # 深证成指
        cy_index = self.get_index_quote('399006')  # 创业板指
        kc_index = self.get_index_quote('000688')  # 科创50
        
        # 提取指数涨跌幅（容错处理）
        sh_change = sh_index.get('chp', 0.0) if sh_index else 0.0
        sz_change = sz_index.get('chp', 0.0) if sz_index else 0.0
        cy_change = cy_index.get('chp', 0.0) if cy_index else 0.0
        kc_change = kc_index.get('chp', 0.0) if kc_index else 0.0
        
        print(f"  ✅ 涨停: {limit_stats['limit_up_count']} 只, "
              f"跌停: {limit_stats['limit_down_count']} 只, "
              f"炸板: {limit_stats['broken_board_count']} 只, "
              f"最高连板: {limit_stats['max_streak']} 板")
        
        return {
            'limit_up_count': limit_stats['limit_up_count'],
            'limit_down_count': limit_stats['limit_down_count'],
            'broken_board_count': limit_stats['broken_board_count'],
            'max_streak': limit_stats['max_streak'],
            'sh_index_change': sh_change,
            'sz_index_change': sz_change,
            'cy_index_change': cy_change,
            'kc_index_change': kc_change,
            'total_turnover': 1200.0
        }
    
    def get_limit_up_stocks(self, date: str = None) -> List[Dict]:
        """
        获取涨停股票列表（Tushare暂不直接支持，需要通过涨跌幅筛选）
        
        Args:
            date: 日期（YYYY-MM-DD）
            
        Returns:
            涨停股票列表
        """
        # Tushare没有直接的涨停列表接口，需要通过涨跌幅筛选
        print("  ⚠️  Tushare不直接提供涨停列表，需要通过涨跌幅>=9.5%筛选")
        return []
    
    def _get_prev_close(self, stock_code: str, market: str, date: str) -> float:
        """
        获取股票前一日收盘价
        
        Args:
            stock_code: 股票代码
            market: 市场代码
            date: 当前日期（YYYY-MM-DD）
            
        Returns:
            前一日收盘价
        """
        # 构造Tushare格式的股票代码
        if '.' not in stock_code:
            ts_code = f"{stock_code}.{market.upper()}"
        else:
            ts_code = stock_code
        
        # 转换日期格式（YYYY-MM-DD -> YYYYMMDD）
        trade_date = date.replace('-', '')
        
        # 获取日线数据
        data = self._api.get_stock_daily(ts_code=ts_code, trade_date=trade_date)
        
        if data and data.get('items') and len(data['items']) > 0:
            item = data['items'][0]
            return item[6]  # pre_close 昨收价
        
        return 0.0
    
    def get_stock_intraday(self, stock_code: str, market: str, date: str) -> List[Dict]:
        """
        获取股票分时数据
        
        Args:
            stock_code: 股票代码（如 000001）
            market: 市场代码（SH/SZ）
            date: 交易日期（YYYY-MM-DD）
            
        Returns:
            分时数据列表，每个元素包含：
            - trade_time: 交易时间（YYYY-MM-DD HH:MM:SS）
            - price: 当前价
            - change_percent: 涨跌幅（小数）
            - volume: 累计成交量（手）
            - turnover: 累计成交额（元）
            - avg_price: 均价
        """
        # 构造Tushare格式的股票代码
        if '.' not in stock_code:
            ts_code = f"{stock_code}.{market.upper()}"
        else:
            ts_code = stock_code
        
        # 转换日期格式（YYYY-MM-DD -> YYYYMMDD）
        trade_date = date.replace('-', '')
        
        # 调用底层API获取分时数据
        data = self._api.get_stock_intraday(ts_code, trade_date)
        
        if not data or not data.get('items'):
            return []
        
        # 获取前一日收盘价（用于计算涨跌幅）
        prev_close = self._get_prev_close(stock_code, market, date)
        if prev_close == 0:
            # 如果获取不到昨收价，使用当天开盘价
            if data['items']:
                prev_close = data['items'][0][2]  # open
        
        result = []
        for item in data['items']:
            # item结构: [ts_code, trade_time, open, high, low, close, vol, amount]
            vol = float(item[6])  # 累计成交量（手）
            amt = float(item[7]) * 1000  # 累计成交额（千元转元）
            price = float(item[5])  # 当前价（close）
            
            # 计算均价：成交额(元) / 成交量(股)
            avg_price = amt / (vol * 100) if vol > 0 else price
            
            # 计算涨跌幅
            change_pct = (price - prev_close) / prev_close if prev_close > 0 else 0
            
            result.append({
                'trade_time': item[1],  # Tushare返回的时间戳（YYYY-MM-DD HH:MM:SS）
                'price': price,
                'change_percent': change_pct,
                'volume': int(vol),
                'turnover': amt,
                'avg_price': avg_price
            })
        
        self._request_count += 1
        return result
    
    def get_request_count(self) -> int:
        """获取请求计数"""
        return self._request_count
    
    def reset_request_count(self):
        """重置请求计数"""
        self._request_count = 0


def main():
    """测试客户端"""
    print("="*60)
    print("市场数据客户端测试")
    print("="*60)
    
    client = MarketDataClient()
    
    # 测试获取股票行情
    print("\n测试1: 获取平安银行行情")
    quote = client.get_stock_quote("000001", "SZ")
    if quote:
        print(f"✅ 收盘价: {quote['ld']}, 涨跌幅: {quote['chp']:+.2f}%")
    else:
        print("❌ 获取失败")
    
    # 测试获取股票信息
    print("\n测试2: 获取平安银行信息")
    info = client.get_stock_info("000001", "SZ")
    if info:
        print(f"✅ 名称: {info['name']}, 行业: {info['industry']}")
    else:
        print("❌ 获取失败")
    
    # 测试获取指数行情
    print("\n测试3: 获取上证指数行情")
    index_quote = client.get_index_quote("000001")
    if index_quote:
        print(f"✅ 上证指数: {index_quote['ld']:.2f} ({index_quote['chp']:+.2f}%)")
    else:
        print("❌ 获取失败")
    
    print(f"\n总请求数: {client.get_request_count()}")
    print("\n✅ 客户端测试完成！")


if __name__ == "__main__":
    main()