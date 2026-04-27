#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘前分析一键数据采集

每日盘前分析前执行一次，一键拉取所有需要的数据：
1. 涨停数据 + 概念enrichment（最核心！）
2. 跌停数据 + 概念enrichment
3. 市场情绪指标（涨停/跌停/连板/封板率）
4. 概念板块涨跌幅排行
5. 盯盘股数据（日线+分时+资金流向）
6. 指数数据（日线+分时）
7. 指定个股分时数据（tushare 1min级别）

使用方法:
    # 采集昨日（最常用）
    python collect_premarket.py --date 2026-04-22

    # 采集昨日 + 指定盯盘股
    python collect_premarket.py --date 2026-04-22 --watchlist 002384 600487 600105

    # 采集昨日 + 指定个股1min分时
    python collect_premarket.py --date 2026-04-22 --intraday 600276 002384

    # 只跑涨跌停（最快）
    python collect_premarket.py --date 2026-04-22 --limit-only

    # 跳过概念enrichment（省时间）
    python collect_premarket.py --date 2026-04-22 --no-enrich

    # 全量采集（涨跌停+情绪+排行+盯盘股+指数+个股分时）
    python collect_premarket.py --date 2026-04-22 --watchlist 002384 600487 600105 --intraday 600276
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# 脚本目录
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))


def banner(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def step(num: int, total: int, title: str):
    print(f"\n📊 [{num}/{total}] {title}")
    print(f"{'-'*50}")


def collect_limit_up(date: str, no_enrich: bool = False) -> bool:
    """采集涨停数据 + 概念enrichment"""
    try:
        from fetch_tushare_data import fetch_limit_list, enrich_limit_concepts, save_data
        
        print("  🔴 采集涨停数据...")
        data = fetch_limit_list(date, 'U')
        if not data:
            print("  ⚠️ 无涨停数据（非交易日？）")
            return False
        
        # 保存原始涨停列表
        tag = f"limit-up-{date.replace('-', '')}"
        save_data(tag, 'limit_up', data, category='limit_list')
        print(f"  ✅ 涨停 {len(data)} 只")
        
        # 概念enrichment
        if not no_enrich:
            enriched = enrich_limit_concepts(data, date, 'U')
            if enriched:
                summary_file = f"limit-up-concepts-{date.replace('-', '')}"
                save_data(summary_file, 'concepts', enriched, category='limit_list')
                print(f"  ✅ 涨停概念enrichment完成")
        else:
            print("  ⏭️  跳过概念enrichment")
        
        return True
    except Exception as e:
        print(f"  ❌ 涨停采集失败: {e}")
        return False


def collect_limit_down(date: str, no_enrich: bool = False) -> bool:
    """采集跌停数据 + 概念enrichment"""
    try:
        from fetch_tushare_data import fetch_limit_list, enrich_limit_concepts, save_data
        
        print("  🟢 采集跌停数据...")
        data = fetch_limit_list(date, 'D')
        if not data:
            print("  ⚠️ 无跌停数据")
            return True  # 无跌停不算失败
        
        tag = f"limit-down-{date.replace('-', '')}"
        save_data(tag, 'limit_down', data, category='limit_list')
        print(f"  ✅ 跌停 {len(data)} 只")
        
        if not no_enrich and len(data) > 0:
            enriched = enrich_limit_concepts(data, date, 'D')
            if enriched:
                summary_file = f"limit-down-concepts-{date.replace('-', '')}"
                save_data(summary_file, 'concepts', enriched, category='limit_list')
                print(f"  ✅ 跌停概念enrichment完成")
        
        return True
    except Exception as e:
        print(f"  ❌ 跌停采集失败: {e}")
        return False


def collect_sentiment(date: str) -> bool:
    """采集市场情绪指标"""
    try:
        from fetch_market_sentiment import fetch_sentiment
        fetch_sentiment(date)
        return True
    except Exception as e:
        print(f"  ❌ 市场情绪采集失败: {e}")
        return False


def collect_concept_rank(top_n: int = 50) -> bool:
    """采集概念板块涨跌幅排行"""
    try:
        from fetch_concept_rank import fetch_concept_rank, save_concept_rank, print_rank_table
        
        print("  🔴 涨幅榜...")
        up = fetch_concept_rank(top_n, 'asc')
        if up:
            print_rank_table(up[:10])
            save_concept_rank(up, 'asc')
        
        time.sleep(1)
        
        print("  🟢 跌幅榜...")
        down = fetch_concept_rank(top_n, 'desc')
        if down:
            print_rank_table(down[:10])
            save_concept_rank(down, 'desc')
        
        return True
    except Exception as e:
        print(f"  ❌ 概念排行采集失败: {e}")
        return False


def collect_watchlist(codes: list) -> bool:
    """采集盯盘股全量数据（日线+分时+资金流向）"""
    try:
        from fetch_adata_data import fetch_watchlist
        fetch_watchlist(codes)
        return True
    except Exception as e:
        print(f"  ❌ 盯盘股采集失败: {e}")
        return False


def collect_indices(codes: list) -> bool:
    """采集指数数据"""
    try:
        from fetch_adata_data import fetch_indices
        fetch_indices(codes)
        return True
    except Exception as e:
        print(f"  ❌ 指数采集失败: {e}")
        return False


def collect_earnings(date: str, next_date: str) -> bool:
    """采集业绩公告披露日程 + 业绩快报
    
    自动拉取：
    1. date晚间实际披露的一季报/年报（昨晚已披露）
    2. next_date预约披露的一季报/年报（今日将披露）
    3. 已有的业绩快报数据（含营收/净利/同比）
    
    数据保存到 data/earnings/ 目录
    """
    try:
        from fetch_tushare_data import fetch_earnings_for_premarket, save_data
        
        print(f"  📋 采集业绩披露日程: {date}(昨晚) → {next_date}(今日)...")
        data = fetch_earnings_for_premarket(date, next_date)
        
        if data:
            tag = f"earnings-{next_date.replace('-', '')}"
            save_data(tag, 'earnings', data, category='earnings')
            
            # 汇总输出
            yesterday = len(data.get('disclosed_yesterday', []))
            today = len(data.get('scheduled_today', []))
            express = len(data.get('express_data', []))
            print(f"  ✅ 昨晚披露 {yesterday} 家 | 今日预约 {today} 家 | 快报 {express} 家")
            
            # 输出今日重点关注的预约披露
            scheduled = data.get('scheduled_today', [])
            if scheduled:
                print(f"  📌 今日将披露({len(scheduled)}家):")
                for item in scheduled[:20]:  # 最多显示20家
                    print(f"     {item['code']} | 预约{item['pre_date']}")
        
        return True
    except Exception as e:
        print(f"  ❌ 业绩公告采集失败: {e}")
        return False


def collect_intraday(codes: list, date: str) -> bool:
    """采集指定个股的1min分时数据（Tushare）"""
    try:
        from fetch_tushare_data import fetch_intraday, save_data
        
        for code in codes:
            print(f"  ⏱️  {code} 1min分时...")
            data = fetch_intraday(code, date, date, '1min')
            if data:
                save_data(code, 'intraday_1min', data)
                total = sum(len(v) for v in data.values())
                print(f"  ✅ {code}: {total} 条")
            else:
                print(f"  ⚠️ {code}: 无分时数据")
            time.sleep(0.5)
        
        return True
    except Exception as e:
        print(f"  ❌ 个股分时采集失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='盘前分析一键数据采集',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 最常用：采集某日全量数据
  python collect_premarket.py --date 2026-04-22

  # 指定盯盘股 + 个股分时
  python collect_premarket.py --date 2026-04-22 --watchlist 002384 600487 --intraday 600276

  # 只跑涨跌停（最快，约2分钟）
  python collect_premarket.py --date 2026-04-22 --limit-only

  # 跳过概念enrichment（省15分钟）
  python collect_premarket.py --date 2026-04-22 --no-enrich
        """
    )
    
    parser.add_argument('--date', type=str, required=True,
                        help='采集日期（YYYY-MM-DD），通常是昨日')
    parser.add_argument('--watchlist', type=str, nargs='+', default=[],
                        help='盯盘股代码列表（如 002384 600487 600105）')
    parser.add_argument('--intraday', type=str, nargs='+', default=[],
                        help='需要1min分时的个股代码（如 600276 002384）')
    parser.add_argument('--indices', type=str, nargs='+',
                        default=['000001', '399001', '399006'],
                        help='指数列表（默认：上证/深成/创业板）')
    parser.add_argument('--next-date', type=str, default=None,
                        help='下一个交易日（用于业绩披露日程，默认自动推算）')
    parser.add_argument('--no-earnings', action='store_true',
                        help='跳过业绩公告采集')
    parser.add_argument('--limit-only', action='store_true',
                        help='只采集涨跌停数据（最快）')
    parser.add_argument('--no-enrich', action='store_true',
                        help='跳过概念enrichment（省时间）')
    parser.add_argument('--no-sentiment', action='store_true',
                        help='跳过市场情绪')
    parser.add_argument('--no-rank', action='store_true',
                        help='跳过概念排行')
    parser.add_argument('--concept-top', type=int, default=50,
                        help='概念排行TopN（默认50）')
    
    args = parser.parse_args()
    
    # ─── 开始 ───
    start_time = time.time()
    
    banner(f"🚀 盘前分析数据采集 | {args.date}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  盯盘股: {args.watchlist or '无'}")
    print(f"  个股分时: {args.intraday or '无'}")
    print(f"  指数: {args.indices}")
    print(f"  选项: {'仅涨跌停' if args.limit_only else '全量'}"
          f"{'｜跳过enrichment' if args.no_enrich else ''}")
    
    results = {}
    
    # 推算next_date（如果未指定）
    if not args.next_date:
        from datetime import timedelta as td
        d = datetime.strptime(args.date, '%Y-%m-%d')
        # 简单推算：周五→下周一，其他→次日
        if d.weekday() == 4:  # 周五
            args.next_date = (d + td(days=3)).strftime('%Y-%m-%d')
        else:
            args.next_date = (d + td(days=1)).strftime('%Y-%m-%d')
    
    # 计算总步骤数
    if args.limit_only:
        total_steps = 2
    else:
        total_steps = 2  # 涨停+跌停
        if not args.no_earnings:
            total_steps += 1
        if not args.no_sentiment:
            total_steps += 1
        if not args.no_rank:
            total_steps += 1
        if args.watchlist:
            total_steps += 1
        total_steps += 1  # 指数
        if args.intraday:
            total_steps += 1
    
    current = 0
    
    # ─── 1. 涨停数据 ───
    current += 1
    step(current, total_steps, f"涨停数据 + 概念enrichment | {args.date}")
    results['涨停'] = collect_limit_up(args.date, args.no_enrich)
    
    # ─── 2. 跌停数据 ───
    current += 1
    step(current, total_steps, f"跌停数据 | {args.date}")
    results['跌停'] = collect_limit_down(args.date, args.no_enrich)
    
    if args.limit_only:
        # 提前结束
        pass
    else:
        # ─── 3. 业绩公告披露 ───
        if not args.no_earnings:
            current += 1
            step(current, total_steps, f"业绩公告披露日程 | {args.date} → {args.next_date}")
            results['业绩'] = collect_earnings(args.date, args.next_date)
        
        # ─── 4. 市场情绪 ───
        if not args.no_sentiment:
            current += 1
            step(current, total_steps, f"市场情绪指标 | {args.date}")
            results['情绪'] = collect_sentiment(args.date)
        
        # ─── 4. 概念排行 ───
        if not args.no_rank:
            current += 1
            step(current, total_steps, f"概念板块涨跌幅排行 Top{args.concept_top}")
            results['排行'] = collect_concept_rank(args.concept_top)
        
        # ─── 5. 盯盘股 ───
        if args.watchlist:
            current += 1
            step(current, total_steps, f"盯盘股数据 | {' '.join(args.watchlist)}")
            results['盯盘股'] = collect_watchlist(args.watchlist)
        
        # ─── 6. 指数 ───
        current += 1
        step(current, total_steps, f"指数数据 | {' '.join(args.indices)}")
        results['指数'] = collect_indices(args.indices)
        
        # ─── 7. 个股分时 ───
        if args.intraday:
            current += 1
            step(current, total_steps, f"个股1min分时 | {' '.join(args.intraday)}")
            results['分时'] = collect_intraday(args.intraday, args.date)
    
    # ─── 汇总 ───
    elapsed = time.time() - start_time
    
    banner(f"📋 采集完成 | 耗时 {elapsed:.0f}秒 ({elapsed/60:.1f}分钟)")
    
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
    
    success = sum(1 for v in results.values() if v)
    total = len(results)
    
    if success == total:
        print(f"\n🎉 全部成功！{success}/{total}")
    else:
        print(f"\n⚠️ 部分失败：{success}/{total} 成功")
    
    print(f"\n数据目录: {TOOLS_DIR.parent / 'data'}")
    print()


if __name__ == "__main__":
    main()
