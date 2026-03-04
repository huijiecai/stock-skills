#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同花顺概念数据采集脚本

遵循架构规范：所有数据操作通过后端 API 进行，不直接访问数据库

支持采集：
1. 概念列表 (concept_list)
2. 概念成分股 (members)
3. 概念日行情 (daily)
4. 个股热榜 (hot_rank)
5. 涨跌停榜单 (limit_list)
6. 全部数据 (all)

使用方法：
    python collect_ths_data.py --method concept_list
    python collect_ths_data.py --method members
    python collect_ths_data.py --method daily --start 2026-03-01 --end 2026-03-02
    python collect_ths_data.py --method hot_rank --start 2026-03-01 --end 2026-03-02
    python collect_ths_data.py --method hot_rank --is-new Y
    python collect_ths_data.py --method limit_list --start 2026-03-01 --end 2026-03-02
    python collect_ths_data.py --method limit_list --limit-type 连扳池
    python collect_ths_data.py --method all --days 60
"""

import argparse
import sys
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# 后端 API 地址
BACKEND_URL = "http://localhost:8000"

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加 tushare_client 模块路径
skills_path = project_root / 'skills' / 'dragon-stock-trading' / 'scripts'
sys.path.insert(0, str(skills_path))

from tushare_client import tushare_client


class THSDataCollector:
    """同花顺数据采集器 - 通过 API 写入数据"""
    
    def __init__(self, backend_url: str = BACKEND_URL):
        self.backend_url = backend_url
        self.tushare = tushare_client
        self._check_backend()
    
    def _check_backend(self):
        """检查后端是否可用"""
        try:
            resp = requests.get(f"{self.backend_url}/health", timeout=5)
            if resp.status_code != 200:
                print(f"❌ 后端服务异常: {resp.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"❌ 无法连接后端服务: {e}")
            print("   请确保后端服务已启动: ./start.sh")
            sys.exit(1)
    
    def _post_to_api(self, data: Dict) -> Dict:
        """通过 API 写入数据"""
        resp = requests.post(f"{self.backend_url}/api/ths/collect", json=data, timeout=30)
        return resp.json()
    
    def _date_to_tushare(self, date_str: str) -> str:
        return date_str.replace('-', '')
    
    def _tushare_to_date(self, ts_date: str) -> str:
        if len(ts_date) == 8:
            return f"{ts_date[:4]}-{ts_date[4:6]}-{ts_date[6:8]}"
        return ts_date
    
    def collect_concept_list(self) -> int:
        """采集概念列表"""
        print("📊 采集同花顺概念列表...")
        
        data = self.tushare.get_ths_concept_list()
        if not data or not data.get('items'):
            print("⚠️ 未获取到概念数据")
            return 0
        
        items = data['items']
        print(f"  获取到 {len(items)} 条概念数据")
        
        # 转换为 API 格式
        concepts = []
        for item in items:
            concepts.append({
                'ts_code': item[0],
                'name': item[1],
                'concept_type': item[2] if len(item) > 2 else None,
                'component_count': item[3] if len(item) > 3 else None,
                'list_date': self._tushare_to_date(item[4]) if len(item) > 4 and item[4] else None
            })
        
        # 通过 API 写入
        result = self._post_to_api({'concepts': concepts})
        count = result.get('saved', {}).get('concepts', 0)
        print(f"✅ 概念列表采集完成，写入 {count} 条")
        return count
    
    def collect_members(self) -> int:
        """采集概念成分股"""
        print("📊 采集概念成分股...")
        
        # 通过 API 获取概念列表
        resp = requests.get(f"{self.backend_url}/api/ths/concepts?limit=500")
        concepts = resp.json()
        
        if not concepts:
            print("⚠️ 请先采集概念列表")
            return 0
        
        print(f"  共 {len(concepts)} 个概念需要采集")
        
        total_count = 0
        for i, concept in enumerate(concepts):
            concept_code = concept['ts_code']
            concept_name = concept['name']
            print(f"  [{i+1}/{len(concepts)}] 采集 {concept_name}...", end='')
            
            data = self.tushare.get_ths_concept_member(concept_code)
            if not data or not data.get('items'):
                print(" 无数据")
                continue
            
            items = data['items']
            members = []
            for item in items:
                stock_code = item[1].replace('.SZ', '').replace('.SH', '').replace('.BJ', '') if len(item) > 1 else None
                stock_name = item[2] if len(item) > 2 else None
                if stock_code:
                    members.append({
                        'concept_code': concept_code,
                        'concept_name': concept_name,
                        'stock_code': stock_code,
                        'stock_name': stock_name
                    })
            
            if members:
                result = self._post_to_api({'members': members})
                count = result.get('saved', {}).get('members', 0)
                total_count += count
                print(f" {count} 只股票")
            else:
                print(" 无数据")
            
            time.sleep(0.1)
        
        print(f"✅ 成分股采集完成，写入 {total_count} 条")
        return total_count
    
    def collect_daily(self, start_date: str, end_date: str) -> int:
        """采集概念日行情"""
        print(f"📊 采集概念日行情 ({start_date} ~ {end_date})...")
        
        trading_dates = self.tushare.get_trade_calendar(
            self._date_to_tushare(start_date),
            self._date_to_tushare(end_date)
        )
        
        if not trading_dates:
            print("⚠️ 未获取到交易日历")
            return 0
        
        print(f"  共 {len(trading_dates)} 个交易日")
        
        total_count = 0
        for trade_date in trading_dates:
            print(f"  采集 {trade_date}...", end='')
            
            data = self.tushare.get_ths_concept_daily(trade_date=trade_date)
            if data and data.get('items'):
                items = data['items']
                daily_list = []
                for item in items:
                    daily_list.append({
                        'trade_date': self._tushare_to_date(item[1]),
                        'concept_code': item[0],
                        'pre_close': item[2] if len(item) > 2 else None,
                        'open': item[3] if len(item) > 3 else None,
                        'close': item[4] if len(item) > 4 else None,
                        'high': item[5] if len(item) > 5 else None,
                        'low': item[6] if len(item) > 6 else None,
                        'pct_change': item[7] if len(item) > 7 else None,
                        'vol': item[8] if len(item) > 8 else None,
                        'turnover_rate': item[9] if len(item) > 9 else None,
                        'total_mv': item[10] if len(item) > 10 else None,
                        'float_mv': item[11] if len(item) > 11 else None,
                    })
                
                result = self._post_to_api({'concept_daily': daily_list})
                count = result.get('saved', {}).get('concept_daily', 0)
                total_count += count
                print(f" {count} 条")
            else:
                print(" 无数据")
            
            time.sleep(0.1)
        
        print(f"✅ 概念日行情采集完成，写入 {total_count} 条")
        return total_count
    
    def collect_hot_rank(self, start_date: str = None, end_date: str = None,
                         is_new: str = 'N') -> int:
        """采集个股热榜"""
        print(f"📊 采集个股热榜 (is_new={is_new})...")
        
        total_count = 0
        
        if is_new == 'Y':
            print("  采集最新热榜数据...", end='')
            data = self.tushare.get_ths_hot_rank(is_new='Y')
            
            if data and data.get('items'):
                items = data['items']
                today = datetime.now().strftime('%Y-%m-%d')
                rank_time = datetime.now().strftime('%H:%M:%S')
                
                hot_list = []
                for item in items:
                    hot_list.append({
                        'trade_date': today,
                        'rank_time': rank_time,
                        'ts_code': item[1],
                        'ts_name': item[2] if len(item) > 2 else None,
                        'rank': item[3] if len(item) > 3 else None,
                        'hot': item[4] if len(item) > 4 else None,
                        'pct_change': item[5] if len(item) > 5 else None,
                        'current_price': item[6] if len(item) > 6 else None,
                        'concept': item[7] if len(item) > 7 else None,
                        'rank_reason': item[8] if len(item) > 8 else None,
                    })
                
                result = self._post_to_api({'hot_rank': hot_list})
                count = result.get('saved', {}).get('hot_rank', 0)
                total_count += count
                print(f" {count} 条")
            else:
                print(" 无数据")
        
        elif start_date and end_date:
            trading_dates = self.tushare.get_trade_calendar(
                self._date_to_tushare(start_date),
                self._date_to_tushare(end_date)
            )
            
            if not trading_dates:
                print("⚠️ 未获取到交易日历")
                return 0
            
            for trade_date in trading_dates:
                print(f"  采集 {trade_date}...", end='')
                
                data = self.tushare.get_ths_hot_rank(trade_date=trade_date)
                if data and data.get('items'):
                    items = data['items']
                    hot_list = []
                    for item in items:
                        hot_list.append({
                            'trade_date': self._tushare_to_date(item[0]),
                            'rank_time': "15:00:00",
                            'ts_code': item[1],
                            'ts_name': item[2] if len(item) > 2 else None,
                            'rank': item[3] if len(item) > 3 else None,
                            'hot': item[4] if len(item) > 4 else None,
                            'pct_change': item[5] if len(item) > 5 else None,
                            'current_price': item[6] if len(item) > 6 else None,
                            'concept': item[7] if len(item) > 7 else None,
                            'rank_reason': item[8] if len(item) > 8 else None,
                        })
                    
                    result = self._post_to_api({'hot_rank': hot_list})
                    count = result.get('saved', {}).get('hot_rank', 0)
                    total_count += count
                    print(f" {count} 条")
                else:
                    print(" 无数据")
                
                time.sleep(0.1)
        
        print(f"✅ 个股热榜采集完成，写入 {total_count} 条")
        return total_count
    
    def collect_limit_list(self, start_date: str, end_date: str,
                           limit_type: str = '涨停池') -> int:
        """采集涨跌停榜单"""
        print(f"📊 采集涨跌停榜单 ({limit_type})...")
        
        trading_dates = self.tushare.get_trade_calendar(
            self._date_to_tushare(start_date),
            self._date_to_tushare(end_date)
        )
        
        if not trading_dates:
            print("⚠️ 未获取到交易日历")
            return 0
        
        print(f"  共 {len(trading_dates)} 个交易日")
        
        total_count = 0
        for trade_date in trading_dates:
            print(f"  采集 {trade_date}...", end='')
            
            data = self.tushare.get_ths_limit_list(trade_date=trade_date, limit_type=limit_type)
            if data and data.get('items'):
                items = data['items']
                limit_list = []
                for item in items:
                    limit_list.append({
                        'trade_date': self._tushare_to_date(item[0]),
                        'ts_code': item[1],
                        'ts_name': item[2] if len(item) > 2 else None,
                        'price': item[3] if len(item) > 3 else None,
                        'pct_chg': item[4] if len(item) > 4 else None,
                        'limit_type': item[5] if len(item) > 5 else limit_type,
                        'tag': item[6] if len(item) > 6 else None,
                        'status': item[7] if len(item) > 7 else None,
                        'lu_desc': item[8] if len(item) > 8 else None,
                        'open_num': item[9] if len(item) > 9 else None,
                        'first_lu_time': item[10] if len(item) > 10 else None,
                        'last_lu_time': item[11] if len(item) > 11 else None,
                        'limit_order': item[12] if len(item) > 12 else None,
                        'limit_amount': item[13] if len(item) > 13 else None,
                        'lu_limit_order': item[14] if len(item) > 14 else None,
                        'turnover_rate': item[15] if len(item) > 15 else None,
                        'turnover': item[16] if len(item) > 16 else None,
                        'free_float': item[17] if len(item) > 17 else None,
                        'sum_float': item[18] if len(item) > 18 else None,
                        'limit_up_suc_rate': item[19] if len(item) > 19 else None,
                        'market_type': item[20] if len(item) > 20 else None,
                    })
                
                result = self._post_to_api({'limit_list': limit_list})
                count = result.get('saved', {}).get('limit_list', 0)
                total_count += count
                print(f" {count} 条")
            else:
                print(" 无数据")
            
            time.sleep(0.1)
        
        print(f"✅ 涨跌停榜单采集完成，写入 {total_count} 条")
        return total_count
    
    def collect_all(self, days: int = 60) -> Dict[str, int]:
        """采集全部数据"""
        print(f"🚀 开始采集全部数据（最近 {days} 天）...")
        
        results = {}
        
        results['concept_list'] = self.collect_concept_list()
        time.sleep(0.5)
        
        results['members'] = self.collect_members()
        time.sleep(0.5)
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        results['daily'] = self.collect_daily(start_date, end_date)
        time.sleep(0.5)
        
        results['hot_rank'] = self.collect_hot_rank(start_date, end_date)
        time.sleep(0.5)
        
        for lt in ['涨停池', '连扳池', '炸板池', '跌停池']:
            results[f'limit_list_{lt}'] = self.collect_limit_list(start_date, end_date, lt)
            time.sleep(0.5)
        
        print("\n📊 采集汇总：")
        for k, v in results.items():
            print(f"  - {k}: {v} 条")
        
        return results


def main():
    parser = argparse.ArgumentParser(description='同花顺概念数据采集工具')
    parser.add_argument('--method', type=str, required=True,
                        choices=['concept_list', 'members', 'daily', 'hot_rank', 'limit_list', 'all'],
                        help='采集方法')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=60, help='采集最近 N 天的数据')
    parser.add_argument('--is-new', type=str, default='N', choices=['Y', 'N'],
                        help='热榜专用：Y=最新数据，N=盘中数据')
    parser.add_argument('--limit-type', type=str, default='涨停池',
                        choices=['涨停池', '连扳池', '炸板池', '跌停池'],
                        help='板单类别')
    parser.add_argument('--backend-url', type=str, default=BACKEND_URL,
                        help='后端 API 地址')
    
    args = parser.parse_args()
    
    collector = THSDataCollector(backend_url=args.backend_url)
    
    if args.method == 'concept_list':
        collector.collect_concept_list()
    elif args.method == 'members':
        collector.collect_members()
    elif args.method == 'daily':
        if not args.start or not args.end:
            print("⚠️ 请指定 --start 和 --end 参数")
            sys.exit(1)
        collector.collect_daily(args.start, args.end)
    elif args.method == 'hot_rank':
        if args.is_new == 'Y':
            collector.collect_hot_rank(is_new='Y')
        elif args.start and args.end:
            collector.collect_hot_rank(args.start, args.end)
        else:
            print("⚠️ 请指定 --is-new Y 或 --start/--end 参数")
            sys.exit(1)
    elif args.method == 'limit_list':
        if not args.start or not args.end:
            print("⚠️ 请指定 --start 和 --end 参数")
            sys.exit(1)
        collector.collect_limit_list(args.start, args.end, args.limit_type)
    elif args.method == 'all':
        collector.collect_all(args.days)


if __name__ == '__main__':
    main()
