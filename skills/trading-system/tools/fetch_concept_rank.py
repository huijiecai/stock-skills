#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
概念板块涨幅排行采集工具

采集当日概念板块涨幅排行，用于全市场催化扫描和主线发现。
数据源：东方财富概念板块行情

依赖：adata（pip install adata）

使用方法：
    # 获取概念板块涨幅排行Top50
    python fetch_concept_rank.py --top 50
    
    # 获取概念板块跌幅排行Bottom50
    python fetch_concept_rank.py --top 50 --order desc
    
    # 保存排行数据
    python fetch_concept_rank.py --top 50 --save
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import adata
    import pandas as pd
except ImportError:
    print("❌ 需要安装 adata: pip install adata")
    sys.exit(1)


# ─── 配置 ─────────────────────────────────────────────────────────────

# 数据保存根目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "concept_rank"


def fetch_concept_rank(top_n: int = 50, order: str = 'asc') -> list:
    """
    获取概念板块涨幅排行
    
    Args:
        top_n: 获取前N个板块
        order: 'asc'=涨幅升序(涨幅榜), 'desc'=跌幅降序(跌幅榜)
    
    Returns: [
        {
            rank: 1,
            code: "BK0612",
            name: "创新药",
            change_pct: 5.2,
            limit_up_count: 15,
            total_amount: 520,  # 亿
            leader_stock: "凯莱英",  # 领涨股
            leader_change: 10.0
        },
        ...
    ]
    """
    print(f"📊 获取概念板块{('涨幅' if order == 'asc' else '跌幅')}排行Top{top_n}")
    
    try:
        # 获取概念板块列表（优先东方财富，失败则用同花顺）
        print("  1️⃣ 获取概念板块列表...")
        try:
            concept_list_df = adata.stock.info.all_concept_code_east()
        except Exception:
            print("  ⚠️ 东方财富接口失败，使用同花顺接口...")
            concept_list_df = adata.stock.info.all_concept_code_ths()
        
        if concept_list_df is None or concept_list_df.empty:
            print("  ❌ 概念板块列表获取失败")
            return []
        
        print(f"  ✅ 共 {len(concept_list_df)} 个概念板块")
        
        # 批量获取概念板块当日行情
        print(f"  2️⃣ 获取概念板块当日行情...")
        concept_ranks = []
        
        for idx, row in concept_list_df.iterrows():
            index_code = str(row.get('index_code', ''))
            name = str(row.get('name', ''))
            
            if not index_code:
                continue
            
            try:
                # 获取概念板块实时行情
                current_df = adata.stock.market.get_market_concept_current_east(index_code=index_code)
                
                if current_df is not None and not current_df.empty:
                    current = current_df.iloc[0]
                    
                    change_pct = float(current.get('pct_chg', 0))
                    amount = float(current.get('amount', 0)) / 1e8  # 转为亿
                    
                    concept_ranks.append({
                        'code': index_code,
                        'name': name,
                        'change_pct': round(change_pct, 2),
                        'total_amount': round(amount, 2),
                        'close': float(current.get('close', 0)),
                        'volume': float(current.get('volume', 0)),
                    })
                    
            except Exception as e:
                # 单个板块获取失败不影响整体
                continue
            
            # 每10个板块打印一次进度
            if (idx + 1) % 10 == 0:
                print(f"     进度: {idx + 1}/{len(concept_list_df)}")
        
        print(f"  ✅ 成功获取 {len(concept_ranks)} 个概念板块行情")
        
        # 排序
        reverse = (order == 'desc')  # 跌幅榜需要降序
        concept_ranks.sort(key=lambda x: x['change_pct'], reverse=reverse)
        
        # 取TopN
        top_concepts = concept_ranks[:top_n]
        
        # 添加排名
        for i, concept in enumerate(top_concepts):
            concept['rank'] = i + 1
        
        # 添加领涨股信息(简化版,实际需要从成分股中找涨幅最大的)
        for concept in top_concepts:
            concept['leader_stock'] = ''  # 需要额外查询成分股
            concept['leader_change'] = 0
            concept['limit_up_count'] = 0  # 需要额外查询涨停数据
        
        return top_concepts
        
    except Exception as e:
        print(f"  ❌ 获取概念板块排行失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def save_concept_rank(concepts: list, order: str = 'asc'):
    """保存概念板块排行数据"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.now().strftime('%Y-%m-%d')
    tag = 'up' if order == 'asc' else 'down'
    
    # 保存单日数据
    filepath = DATA_DIR / f"{date_str}_{tag}.json"
    
    data = {
        'date': date_str,
        'type': '涨幅榜' if order == 'asc' else '跌幅榜',
        'count': len(concepts),
        'concepts': concepts
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 已保存 → {filepath}")
    return filepath


def print_rank_table(concepts: list):
    """打印排行表格"""
    if not concepts:
        print("  ⚠️ 无数据")
        return
    
    print(f"\n{'='*80}")
    print(f"{'排名':<6} {'概念名称':<20} {'涨幅%':<10} {'成交额(亿)':<12}")
    print(f"{'='*80}")
    
    for c in concepts:
        print(f"{c['rank']:<6} {c['name']:<20} {c['change_pct']:<10.2f} {c['total_amount']:<12.2f}")
    
    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(description='概念板块涨幅排行采集工具')
    parser.add_argument('--top', type=int, default=50, help='获取前N个板块（默认50）')
    parser.add_argument('--order', type=str, default='asc', choices=['asc', 'desc'], 
                        help='排序方式：asc=涨幅榜, desc=跌幅榜')
    parser.add_argument('--save', action='store_true', help='保存到文件')
    
    args = parser.parse_args()
    
    # 获取排行
    concepts = fetch_concept_rank(args.top, args.order)
    
    if concepts:
        # 打印表格
        print_rank_table(concepts)
        
        # 保存
        if args.save:
            save_concept_rank(concepts, args.order)
    else:
        print("❌ 获取概念板块排行失败")


if __name__ == "__main__":
    main()
