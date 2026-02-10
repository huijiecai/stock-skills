"""
回测引擎模块
负责获取历史数据并追踪股票后续表现
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, days: int = 30):
        """
        初始化回测引擎
        
        Args:
            days: 回测天数（默认30天）
        """
        self.days = days
        self.today = datetime.now()
        
    def get_trading_days(self, days: int) -> List[str]:
        """
        获取最近N个交易日
        
        Args:
            days: 天数
            
        Returns:
            List[str]: 交易日列表（YYYYMMDD格式）
        """
        print(f"📅 获取最近{days}个交易日...")
        
        # 从今天往前推days*2天（确保有足够的交易日）
        end_date = self.today.strftime("%Y%m%d")
        start_date = (self.today - timedelta(days=days*2)).strftime("%Y%m%d")
        
        try:
            # 获取A股交易日历
            df = ak.tool_trade_date_hist_sina()
            
            # 筛选日期范围内的交易日
            df['trade_date'] = pd.to_datetime(df['trade_date']).dt.strftime("%Y%m%d")
            trading_days = df[
                (df['trade_date'] >= start_date) & 
                (df['trade_date'] <= end_date)
            ]['trade_date'].tolist()
            
            # 取最近的days个交易日
            trading_days = trading_days[-days:]
            
            print(f"✅ 获取成功：{len(trading_days)} 个交易日")
            print(f"   起始日期：{trading_days[0]}")
            print(f"   结束日期：{trading_days[-1]}")
            
            return trading_days
            
        except Exception as e:
            print(f"⚠️  获取交易日历失败：{e}")
            print("使用简化方法：直接按自然日回溯...")
            
            # 降级方案：按自然日回溯
            trading_days = []
            current_date = self.today
            while len(trading_days) < days:
                date_str = current_date.strftime("%Y%m%d")
                # 跳过周末
                if current_date.weekday() < 5:
                    trading_days.insert(0, date_str)
                current_date -= timedelta(days=1)
            
            return trading_days
    
    def get_limit_up_stocks_batch(self, trading_days: List[str]) -> Dict[str, pd.DataFrame]:
        """
        批量获取多个交易日的涨停股票
        
        Args:
            trading_days: 交易日列表
            
        Returns:
            Dict[str, pd.DataFrame]: {日期: 涨停股票DataFrame}
        """
        print(f"\n📊 批量获取涨停股票数据...")
        
        result = {}
        total = len(trading_days)
        success_count = 0
        
        for i, date in enumerate(trading_days, 1):
            try:
                print(f"  [{i}/{total}] {date}...", end=" ")
                df = ak.stock_zt_pool_em(date=date)
                
                if df is not None and not df.empty:
                    result[date] = df
                    print(f"✓ {len(df)}只")
                    success_count += 1
                else:
                    print("无涨停")
                
                # 避免请求过快
                time.sleep(0.5)
                
            except Exception as e:
                print(f"✗ 失败: {e}")
                continue
        
        print(f"\n✅ 成功获取 {success_count}/{total} 个交易日的数据")
        return result
    
    def get_stock_future_performance(
        self, 
        stock_code: str, 
        start_date: str, 
        days: int = 3
    ) -> Dict[str, float]:
        """
        获取股票未来N天的表现
        
        Args:
            stock_code: 股票代码
            start_date: 起始日期（YYYYMMDD）
            days: 追踪天数（默认3天）
            
        Returns:
            Dict: {
                'T+1': 0.05,  # 次日收益率
                'T+2': 0.08,
                'T+3': 0.12,
                'max_gain': 0.15,  # 期间最大涨幅
                'max_loss': -0.03  # 期间最大跌幅
            }
        """
        try:
            # 计算结束日期（往后推10天，确保有足够交易日）
            start_dt = datetime.strptime(start_date, "%Y%m%d")
            end_dt = start_dt + timedelta(days=10)
            
            # 获取历史行情
            df = ak.stock_zh_a_hist(
                symbol=stock_code,
                start_date=start_date,
                end_date=end_dt.strftime("%Y%m%d"),
                adjust="qfq"  # 前复权
            )
            
            if df is None or df.empty or len(df) < 2:
                return None
            
            # 第一天的收盘价作为基准
            base_price = float(df.iloc[0]['收盘'])
            
            result = {}
            max_gain = 0
            max_loss = 0
            
            # 计算T+1, T+2, T+3的收益率
            for i in range(1, min(days + 1, len(df))):
                current_price = float(df.iloc[i]['收盘'])
                change_pct = (current_price - base_price) / base_price
                result[f'T+{i}'] = round(change_pct, 4)
                
                # 更新最大涨跌幅
                max_gain = max(max_gain, change_pct)
                max_loss = min(max_loss, change_pct)
            
            result['max_gain'] = round(max_gain, 4)
            result['max_loss'] = round(max_loss, 4)
            
            return result
            
        except Exception as e:
            # 静默失败（可能是退市、停牌等）
            return None
    
    def calculate_continuation_rate(
        self,
        limit_up_data: Dict[str, pd.DataFrame],
        sample_size: int = 100
    ) -> pd.DataFrame:
        """
        计算续板率（涨停后次日继续涨停的概率）
        
        Args:
            limit_up_data: 涨停数据字典 {日期: DataFrame}
            sample_size: 采样数量（避免计算过慢）
            
        Returns:
            pd.DataFrame: 包含股票及其后续表现的数据
        """
        print(f"\n🔍 分析续板率（采样{sample_size}只股票）...")
        
        results = []
        trading_days = sorted(limit_up_data.keys())
        sample_count = 0
        
        for date in trading_days[:-3]:  # 排除最近3天（没有足够的后续数据）
            df = limit_up_data[date]
            
            # 随机采样（避免计算过慢）
            if len(df) > sample_size // len(trading_days):
                df = df.sample(n=min(sample_size // len(trading_days), len(df)))
            
            for _, row in df.iterrows():
                if sample_count >= sample_size:
                    break
                
                code = str(row['代码']).zfill(6)
                name = row['名称']
                
                # 获取后续表现
                performance = self.get_stock_future_performance(code, date)
                
                if performance:
                    results.append({
                        '日期': date,
                        '代码': code,
                        '名称': name,
                        '首板时间': row.get('首次封板时间', ''),
                        '所属行业': row.get('所属行业', ''),
                        **performance
                    })
                    sample_count += 1
                
                # 避免请求过快
                time.sleep(0.3)
        
        print(f"✅ 分析完成：{len(results)} 只股票")
        return pd.DataFrame(results)


if __name__ == "__main__":
    # 测试代码
    engine = BacktestEngine(days=5)
    
    print("\n=== 测试1: 获取交易日 ===")
    trading_days = engine.get_trading_days(5)
    print(f"交易日: {trading_days}")
    
    print("\n=== 测试2: 获取涨停股票 ===")
    limit_up_data = engine.get_limit_up_stocks_batch(trading_days[-2:])
    
    print("\n=== 测试3: 获取后续表现 ===")
    if limit_up_data:
        date = list(limit_up_data.keys())[0]
        df = limit_up_data[date]
        if not df.empty:
            code = str(df.iloc[0]['代码']).zfill(6)
            name = df.iloc[0]['名称']
            print(f"测试股票: {name} ({code})")
            performance = engine.get_stock_future_performance(code, date)
            print(f"后续表现: {performance}")
