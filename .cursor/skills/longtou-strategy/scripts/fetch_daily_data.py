#!/usr/bin/env python3
"""
每日数据拉取脚本

用途：
- 每天早盘前运行一次（8:00-8:30）
- 批量拉取当日所有需要的数据
- 缓存到本地文件，供后续快速读取
- 避免频率限制和重复查询

使用方式：
    python scripts/fetch_daily_data.py

说明：
- Tushare有IP限制（每个token最多2个IP），如果遇到IP限制：
  方法1：在同一台机器上运行（推荐）
  方法2：只拉取akshare数据，概念数据通过实时API获取（降级模式）
"""

import sys
import os
import json
import time
from datetime import datetime

# 添加模块路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

import akshare as ak

# 尝试导入Tushare（可能失败）
TUSHARE_AVAILABLE = False
try:
    import tushare as ts
    from modules.config import TUSHARE_TOKEN
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    TUSHARE_AVAILABLE = True
except Exception as e:
    print(f"⚠️  Tushare不可用：{e}")
    print("将使用降级模式（只拉取akshare数据）")


def fetch_today_data():
    """拉取今日所有数据"""
    today = datetime.now().strftime("%Y%m%d")
    data_dir = os.path.join(parent_dir, "data", today)
    os.makedirs(data_dir, exist_ok=True)
    
    print("="*60)
    print(f"📅 开始拉取 {today} 数据")
    print("="*60)
    
    # 1. 涨停股票
    print("\n【1/5】获取涨停股票...")
    try:
        df = ak.stock_zt_pool_em(date=today)
        if df is not None and not df.empty:
            # 格式化JSON写入
            data = json.loads(df.to_json(orient='records', force_ascii=False))
            with open(os.path.join(data_dir, "limit_up_stocks.json"), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ 涨停股票：{len(df)} 只")
            limit_up_count = len(df)
        else:
            print("⚠️  今日暂无涨停")
            limit_up_count = 0
    except Exception as e:
        print(f"❌ 失败：{e}")
        limit_up_count = 0
    
    # 2. 连板数据
    print("\n【2/5】获取连板数据...")
    try:
        df = ak.stock_zt_pool_strong_em(date=today)
        if df is not None and not df.empty:
            # 格式化JSON写入
            data = json.loads(df.to_json(orient='records', force_ascii=False))
            with open(os.path.join(data_dir, "continuous_limit_up.json"), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ 连板股票：{len(df)} 只")
        else:
            print("⚠️  今日暂无连板")
    except Exception as e:
        print(f"❌ 失败：{e}")
    
    # 3. 东方财富人气榜
    print("\n【3/5】获取东方财富人气榜...")
    try:
        df = ak.stock_hot_rank_em()
        if df is not None and not df.empty:
            # 格式化JSON写入
            data = json.loads(df.to_json(orient='records', force_ascii=False))
            with open(os.path.join(data_dir, "em_hot_rank.json"), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ 人气榜：{len(df)} 只")
        else:
            print("⚠️  人气榜为空")
    except Exception as e:
        print(f"❌ 失败：{e}")
    
    # 4. 龙虎榜（可选，经常失败）
    print("\n【4/5】获取龙虎榜...")
    yesterday = datetime.now().strftime("%Y%m%d")
    try:
        df = ak.stock_lhb_detail_em(start_date=yesterday, end_date=yesterday)
        if df is not None and not df.empty:
            # 格式化JSON写入
            data = json.loads(df.to_json(orient='records', force_ascii=False))
            with open(os.path.join(data_dir, "dragon_tiger_list.json"), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ 龙虎榜：{len(df)} 只")
        else:
            print("⚠️  龙虎榜为空")
    except Exception as e:
        print(f"⚠️  龙虎榜获取失败（这个接口不稳定）：{e}")
    
    # 5. 批量获取涨停股票的概念
    print("\n【5/5】批量获取股票概念...")
    
    # 读取涨停股票列表
    limit_up_path = os.path.join(data_dir, "limit_up_stocks.json")
    if not os.path.exists(limit_up_path) or limit_up_count == 0:
        print("⚠️  未找到涨停股票数据，跳过概念查询")
        return
    
    with open(limit_up_path, 'r', encoding='utf-8') as f:
        limit_up_stocks = json.load(f)
    
    stock_concepts = {}
    total = len(limit_up_stocks)
    
    print(f"需要查询 {total} 只股票的概念...")
    
    # 方案A：优先使用 akshare 的行业数据（免费、稳定）
    print("使用 akshare 的行业数据（免费、无限制）")
    for i, stock in enumerate(limit_up_stocks, 1):
        code = str(stock['代码']).zfill(6)
        name = stock['名称']
        industry = stock.get('所属行业', '')
        
        # 使用行业作为概念（简化版）
        concepts = [industry] if industry else []
        
        stock_concepts[code] = {
            '名称': name,
            '概念': concepts,
            '行业': industry
        }
        print(f"  [{i}/{total}] {name} ({code}): {industry}")
    
    # 方案B：如果 Tushare 可用且无 IP 限制，尝试补充详细概念（可选）
    if TUSHARE_AVAILABLE:
        print("\n尝试使用 Tushare 补充详细概念（可能遇到 IP 限制）...")
        success_count = 0
        failed_count = 0
        
        for i, stock in enumerate(limit_up_stocks, 1):
            code = str(stock['代码']).zfill(6)
            name = stock['名称']
            
            # 转换为Tushare代码
            if code.startswith('6'):
                ts_code = f"{code}.SH"
            elif code.startswith('0') or code.startswith('3'):
                ts_code = f"{code}.SZ"
            elif code.startswith('8') or code.startswith('4'):
                ts_code = f"{code}.BJ"
            else:
                continue
            
            try:
                # 查询概念
                time.sleep(0.5)
                df = pro.concept_detail(ts_code=ts_code, fields='id,concept_name')
                
                if df is not None and not df.empty:
                    concepts = df['concept_name'].tolist()
                    # 合并行业和概念
                    industry = stock_concepts[code].get('行业', '')
                    all_concepts = [industry] + concepts if industry else concepts
                    stock_concepts[code]['概念'] = list(set(all_concepts))  # 去重
                    print(f"  [{i}/{total}] {name}: 补充 {len(concepts)} 个概念")
                    success_count += 1
                    
            except Exception as e:
                error_msg = str(e)
                failed_count += 1
                
                # 如果是IP限制，提前退出
                if 'IP' in error_msg or 'ip' in error_msg.lower():
                    print(f"\n⚠️  Tushare IP限制：{e}")
                    print(f"已补充 {success_count}/{total} 只股票的详细概念")
                    print("其余股票使用行业数据（已足够匹配逻辑库）")
                    break
        
        if success_count > 0:
            print(f"\n✅ Tushare 补充完成：{success_count}/{total} 只股票")
    else:
        print("\n💡 Tushare 不可用，使用行业数据（已足够匹配逻辑库）")
    
    # 保存概念数据到文件
    with open(os.path.join(data_dir, "stock_concepts.json"), 'w', encoding='utf-8') as f:
        json.dump(stock_concepts, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 概念数据已保存：{len(stock_concepts)} 只股票")
    
    # 创建软链接到latest
    latest_link = os.path.join(parent_dir, "data", "latest")
    if os.path.exists(latest_link) or os.path.islink(latest_link):
        os.remove(latest_link)
    os.symlink(today, latest_link)
    
    print("\n" + "="*60)
    print(f"🎉 数据拉取完成！保存在: data/{today}/")
    print("="*60)
    print("\n提示：现在可以使用 /longtou-strategy 筛选，速度会更快！")


if __name__ == "__main__":
    fetch_today_data()
