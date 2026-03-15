#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时数据获取模块
为 investment-analysis skill 提供股票实时行情和财务数据
使用 Tushare API，专注于单个股票的深度分析数据
"""

import tushare as ts
import tushare.pro.client as client
from typing import Dict, Optional, List
from datetime import datetime, timedelta

# 兼容直接运行和模块导入
try:
    from .config_loader import config
except ImportError:
    from config_loader import config

# 全局设置自定义API域名（高积分用户专用，速度更快）
client.DataApi._DataApi__http_url = "http://tushare.xyz"


class RealtimeDataClient:
    """实时数据客户端"""
    
    def __init__(self):
        """初始化客户端"""
        self.token = config.get_tushare_token()
        if not self.token:
            raise ValueError("未找到Tushare Token，请配置环境变量TUSHARE_TOKEN或~/.tushare_token文件")
        
        self.pro = ts.pro_api(self.token)
    
    def get_stock_basic_info(self, code: str) -> Optional[Dict]:
        """
        获取股票基本信息
        
        Args:
            code: 6位股票代码（如 600519）
            
        Returns:
            基本信息字典
        """
        try:
            # 转换为Tushare代码格式
            ts_code = self._convert_to_ts_code(code)
            
            # 获取股票基本信息
            df = self.pro.stock_basic(ts_code=ts_code, fields='ts_code,symbol,name,area,industry,market,list_date')
            
            if df is None or df.empty:
                return None
            
            info = df.iloc[0]
            return {
                'ts_code': info['ts_code'],
                'code': info['symbol'],
                'name': info['name'],
                'area': info['area'],
                'industry': info['industry'],
                'market': info['market'],
                'list_date': info['list_date']
            }
        except Exception as e:
            print(f"获取基本信息失败: {e}")
            return None
    
    def get_stock_daily(self, code: str, days: int = 30) -> Optional[List[Dict]]:
        """
        获取股票日线数据
        
        Args:
            code: 6位股票代码
            days: 获取最近N天数据（默认30天）
            
        Returns:
            日线数据列表
        """
        try:
            ts_code = self._convert_to_ts_code(code)
            
            # 计算日期范围
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            # 获取日线数据
            df = self.pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields='trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
            )
            
            if df is None or df.empty:
                return None
            
            # 转换为字典列表（按日期降序）
            return df.to_dict('records')
        except Exception as e:
            print(f"获取日线数据失败: {e}")
            return None
    
    def get_stock_financial(self, code: str, period: str = None) -> Optional[Dict]:
        """
        获取股票财务数据
        
        Args:
            code: 6位股票代码
            period: 报告期（格式：20231231），不指定则获取最新
            
        Returns:
            财务数据字典
        """
        try:
            ts_code = self._convert_to_ts_code(code)
            
            # 获取利润表
            income_params = {'ts_code': ts_code}
            if period:
                income_params['period'] = period
            
            income_df = self.pro.income(
                **income_params,
                fields='end_date,total_revenue,revenue,operate_profit,total_profit,n_income,n_income_attr_p'
            )
            
            # 获取资产负债表
            balance_df = self.pro.balancesheet(
                **income_params,
                fields='end_date,total_assets,total_liab,total_hldr_eqy_inc_min_int'
            )
            
            # 获取现金流量表
            cashflow_df = self.pro.cashflow(
                **income_params,
                fields='end_date,n_cashflow_act,n_cashflow_inv_act,n_cash_flows_fnc_act'
            )
            
            if income_df is None or income_df.empty:
                return None
            
            # 获取最新一期数据
            income = income_df.iloc[0]
            balance = balance_df.iloc[0] if not balance_df.empty else None
            cashflow = cashflow_df.iloc[0] if not cashflow_df.empty else None
            
            result = {
                'period': income['end_date'],
                'revenue': income.get('total_revenue'),  # 营业总收入
                'operate_profit': income.get('operate_profit'),  # 营业利润
                'net_profit': income.get('n_income_attr_p'),  # 归母净利润
            }
            
            if balance is not None:
                result['total_assets'] = balance.get('total_assets')  # 总资产
                result['total_liab'] = balance.get('total_liab')  # 总负债
                result['equity'] = balance.get('total_hldr_eqy_inc_min_int')  # 股东权益
            
            if cashflow is not None:
                result['cashflow_operating'] = cashflow.get('n_cashflow_act')  # 经营现金流
            
            return result
        except Exception as e:
            print(f"获取财务数据失败: {e}")
            return None
    
    def get_stock_valuation(self, code: str) -> Optional[Dict]:
        """
        获取股票估值数据（PE/PB等）
        
        Args:
            code: 6位股票代码
            
        Returns:
            估值数据字典
        """
        try:
            ts_code = self._convert_to_ts_code(code)
            
            # 获取最近一个交易日的估值数据
            trade_date = datetime.now().strftime('%Y%m%d')
            
            df = self.pro.daily_basic(
                ts_code=ts_code,
                trade_date=trade_date,
                fields='trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,total_share,float_share,total_mv,circ_mv'
            )
            
            if df is None or df.empty:
                # 如果当天没有数据，尝试获取最近几天的
                for i in range(1, 10):
                    trade_date = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
                    df = self.pro.daily_basic(
                        ts_code=ts_code,
                        start_date=trade_date,
                        end_date=trade_date,
                        fields='trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,total_share,float_share,total_mv,circ_mv'
                    )
                    if df is not None and not df.empty:
                        break
            
            if df is None or df.empty:
                return None
            
            data = df.iloc[0]
            return {
                'trade_date': data['trade_date'],
                'close': data['close'],
                'pe': data.get('pe'),  # 市盈率（静态）
                'pe_ttm': data.get('pe_ttm'),  # 市盈率（TTM）
                'pb': data.get('pb'),  # 市净率
                'ps': data.get('ps'),  # 市销率（静态）
                'ps_ttm': data.get('ps_ttm'),  # 市销率（TTM）
                'total_share': data.get('total_share'),  # 总股本（万股）
                'float_share': data.get('float_share'),  # 流通股本（万股）
                'total_mv': data.get('total_mv'),  # 总市值（万元）
                'circ_mv': data.get('circ_mv'),  # 流通市值（万元）
            }
        except Exception as e:
            print(f"获取估值数据失败: {e}")
            return None
    
    def _convert_to_ts_code(self, code: str) -> str:
        """
        将6位股票代码转换为Tushare代码格式
        
        Args:
            code: 6位股票代码（如 600519）
            
        Returns:
            Tushare代码（如 600519.SH）
        """
        if '.' in code:
            return code
        
        # 根据代码判断交易所
        if code.startswith('6'):
            return f"{code}.SH"  # 上海
        elif code.startswith('0') or code.startswith('3'):
            return f"{code}.SZ"  # 深圳
        elif code.startswith('8') or code.startswith('4'):
            return f"{code}.BJ"  # 北京
        else:
            return f"{code}.SH"  # 默认上海


# 全局客户端实例
_client = None


def get_stock_realtime_data(code: str) -> Optional[Dict]:
    """
    获取股票实时综合数据（简化接口）
    
    Args:
        code: 6位股票代码
        
    Returns:
        包含基本信息、最新行情、估值数据的字典
    """
    global _client
    if _client is None:
        _client = RealtimeDataClient()
    
    # 获取基本信息
    basic = _client.get_stock_basic_info(code)
    if not basic:
        return None
    
    # 获取最新行情（最近1天）
    daily = _client.get_stock_daily(code, days=1)
    latest_price = daily[0] if daily else None
    
    # 获取估值数据
    valuation = _client.get_stock_valuation(code)
    
    # 合并数据
    result = {**basic}
    
    if latest_price:
        result.update({
            'trade_date': latest_price['trade_date'],
            'close': latest_price['close'],
            'change': latest_price['change'],
            'pct_chg': latest_price['pct_chg'],
            'volume': latest_price['vol'],
            'amount': latest_price['amount'],
        })
    
    if valuation:
        result.update({
            'pe_ttm': valuation['pe_ttm'],
            'pb': valuation['pb'],
            'ps_ttm': valuation['ps_ttm'],
            'total_mv': valuation['total_mv'],
            'circ_mv': valuation['circ_mv'],
        })
    
    return result


def get_stock_financial_data(code: str, period: str = None) -> Optional[Dict]:
    """
    获取股票财务数据（简化接口）
    
    Args:
        code: 6位股票代码
        period: 报告期（格式：20231231），不指定则获取最新
        
    Returns:
        财务数据字典
    """
    global _client
    if _client is None:
        _client = RealtimeDataClient()
    
    return _client.get_stock_financial(code, period)


def main():
    """测试数据获取"""
    print("=" * 60)
    print("实时数据获取测试")
    print("=" * 60)
    
    # 测试贵州茅台
    code = '600519'
    print(f"\n正在获取 {code} 的数据...")
    
    # 获取实时数据
    data = get_stock_realtime_data(code)
    if data:
        print(f"\n✅ 基本信息:")
        print(f"  股票名称: {data['name']}")
        print(f"  所属行业: {data['industry']}")
        print(f"  最新价格: {data.get('close', 'N/A')}")
        print(f"  涨跌幅: {data.get('pct_chg', 'N/A')}%")
        print(f"  PE(TTM): {data.get('pe_ttm', 'N/A')}")
        print(f"  PB: {data.get('pb', 'N/A')}")
        print(f"  总市值: {data.get('total_mv', 'N/A')}万元")
    else:
        print("❌ 获取实时数据失败")
    
    # 获取财务数据
    financial = get_stock_financial_data(code)
    if financial:
        print(f"\n✅ 财务数据 ({financial['period']}):")
        print(f"  营业收入: {financial.get('revenue', 'N/A')}元")
        print(f"  净利润: {financial.get('net_profit', 'N/A')}元")
        print(f"  总资产: {financial.get('total_assets', 'N/A')}元")
    else:
        print("❌ 获取财务数据失败")


if __name__ == "__main__":
    main()
