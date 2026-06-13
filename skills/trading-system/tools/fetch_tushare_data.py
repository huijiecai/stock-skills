#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ⚠️ 已被 astock 取代：`astock query limit --date YYYYMMDD`、`astock query limit ladder`
#    本脚本仅在 astock 不可用时作兜底。优先级详见 SKILL.md 「数据采集工具」章节。
"""
交易系统数据采集工具（Tushare 高积分）

为预期驱动交易系统提供涨跌停数据、历史分钟数据采集。
依赖：tushare（pip install tushare）

使用方法：
    # 采集涨停数据（含首封时间、炸板次数、连板高度）
    python fetch_tushare_data.py --limit-up --date 2026-03-27

    # 采集跌停数据
    python fetch_tushare_data.py --limit-up --date 2026-03-27 --type D

    # 采集历史分钟数据
    python fetch_tushare_data.py --code 002192 --start 2026-03-01 --end 2026-03-27 --intraday

    # 采集指定频率的分时数据
    python fetch_tushare_data.py --code 002192 --days 7 --intraday --freq 5min

    # 采集多只股票+指数的全量数据
    python fetch_tushare_data.py --all --date 2026-03-27 --watchlist 002192 000722 --indices 000001 399001
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import tushare as ts
except ImportError:
    print("❌ 需要安装 tushare: pip install tushare")
    sys.exit(1)


# ─── 配置 ─────────────────────────────────────────────────────────────

TUSHARE_TOKEN = '78c2b09c8175affca2a45a788be6b0ba13369519220f7cd1b9c5b991'
TUSHARE_DOMAIN = 'http://tushare.xyz'

# 数据保存根目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_pro():
    """获取 Tushare pro API 实例"""
    import tushare.pro.client as _client
    _client.DataApi._DataApi__http_url = TUSHARE_DOMAIN
    return ts.pro_api(TUSHARE_TOKEN)


def get_ts_code(code: str) -> str:
    """6位代码 -> Tushare格式（如 002192 -> 002192.SZ）"""
    code = code.strip()
    if '.' in code:
        return code.upper()
    if code.startswith(('6', '9')):
        return f"{code}.SH"
    elif code.startswith(('0', '3', '2')):
        return f"{code}.SZ"
    elif code.startswith('4') or code.startswith('8'):
        return f"{code}.BJ"
    return f"{code}.SZ"


# ─── 日线数据 ──────────────────────────────────────────────────────

def fetch_daily(code: str, start_date: str, end_date: str) -> dict:
    """
    采集日线数据
    Returns: {date: {open, high, low, close, volume, amount, change_pct, change, pre_close}, ...}
    格式与 fetch_adata_data.fetch_stock_daily 统一
    """
    pro = get_pro()
    ts_code = get_ts_code(code)
    start = start_date.replace('-', '')
    end = end_date.replace('-', '')

    df = pro.daily(
        ts_code=ts_code, start_date=start, end_date=end,
        fields='ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount'
    )
    if df is None or df.empty:
        return {}

    result = {}
    for _, row in df.iterrows():
        d = str(row['trade_date'])
        date_fmt = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        close_price = float(row['close'])
        pre_close = float(row['pre_close'])
        change = close_price - pre_close
        result[date_fmt] = {
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': close_price,
            'pre_close': pre_close,
            'change_pct': float(row['pct_chg']),
            'change': round(change, 2),
            'volume': float(row['vol']),
            'amount': float(row['amount']) * 1000,
        }
    return result


# ─── 分钟数据 ──────────────────────────────────────────────────────

def fetch_intraday(code: str, start_date: str, end_date: str, freq: str = '1min', is_index: bool = False) -> dict:
    """
    采集分钟级数据（个股用 stk_mins，指数用 idx_mins）
    is_index: 是否为指数（指数用 idx_mins，个股用 stk_mins）
    Returns: {date: [{time, price, change, change_pct, volume, amount, avg_price}, ...], ...}
    格式与 fetch_adata_data.fetch_stock_intraday 统一
    """
    pro = get_pro()
    ts_code = get_ts_code(code)

    start_dt = datetime.strptime(start_date.replace('-', ''), '%Y%m%d')
    end_dt = datetime.strptime(end_date.replace('-', ''), '%Y%m%d')
    result = {}
    current = start_dt

    while current <= end_dt:
        batch_end = min(current + timedelta(days=5), end_dt)
        start_time = current.strftime('%Y-%m-%d 09:00:00')
        end_time = batch_end.strftime('%Y-%m-%d 15:30:00')

        try:
            if is_index:
                # 指数用 idx_mins（需要单独开权限）
                df = pro.idx_mins(
                    ts_code=ts_code, freq=freq,
                    start_date=start_time, end_date=end_time,
                    fields='ts_code,trade_time,open,high,low,close,vol,amount'
                )
            else:
                # 个股用 stk_mins
                df = pro.stk_mins(
                    ts_code=ts_code, freq=freq,
                    start_date=start_time, end_date=end_time,
                    fields='ts_code,trade_time,open,high,low,close,vol,amount'
                )

            if df is not None and not df.empty:
                # 按日期分组，用于计算涨跌幅
                daily_data = {}
                for _, row in df.iterrows():
                    trade_time = str(row['trade_time'])
                    date_part = trade_time[:10]
                    time_part = trade_time[11:16]  # HH:MM 格式
                    if date_part not in daily_data:
                        daily_data[date_part] = []
                    daily_data[date_part].append({
                        'time': time_part,
                        'price': float(row['close']),  # 用 close 作为 price
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'volume': float(row['vol']),
                        'amount': float(row['amount']) * 1000,
                    })

                # 计算涨跌幅和均价
                for date_part, bars in daily_data.items():
                    if not bars:
                        continue
                    # 第一根K线的 open 作为昨收
                    pre_close = bars[0]['open'] if bars else 0
                    # 计算累计成交额和成交量
                    total_amount = 0.0
                    total_volume = 0.0
                    for bar in bars:
                        total_amount += bar['amount']
                        total_volume += bar['volume']
                        # 涨跌额和涨跌幅
                        bar['change'] = bar['price'] - pre_close
                        bar['change_pct'] = (bar['change'] / pre_close * 100) if pre_close else 0
                        # 均价
                        bar['avg_price'] = total_amount / total_volume / 100 if total_volume > 0 else bar['price']
                        # 移除 OHLC 字段，保持与 adata 格式统一
                        del bar['open']
                        del bar['high']
                        del bar['low']
                    result[date_part] = bars

                print(f"  ✅ {current.strftime('%Y-%m-%d')} ~ {batch_end.strftime('%Y-%m-%d')}: {len(df)} 条")
            else:
                print(f"  ⏭️ {current.strftime('%Y-%m-%d')} ~ {batch_end.strftime('%Y-%m-%d')}: 无数据")

        except Exception as e:
            err = str(e)
            if '权限' in err:
                hint = 'idx_mins' if is_index else 'stk_mins'
                print(f"  ❌ {hint} 接口权限不足")
                return {}
            print(f"  ❌ 请求失败: {e}")

        current = batch_end + timedelta(days=1)
        time.sleep(0.5)

    return result


# ─── 指数分时（腾讯财经备用，免费）──────────────────────────────────

def fetch_index_min_tencent(code: str, date_str: str) -> list:
    """
    从腾讯财经获取指数分时数据（免费，无需token）
    仅支持最近一个交易日的历史分时
    code: 000001 / 399001 / 399006
    Returns: [{time, close, vol, amount}, ...]
    """
    import urllib.request

    prefix = 'sh' if code.startswith('0') else 'sz'
    full_code = f'{prefix}{code}'
    url = f'https://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data&code={full_code}'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        text = urllib.request.urlopen(req, timeout=10).read().decode()
        if 'min_data=' in text:
            text = text.split('min_data=', 1)[1]
        data = json.loads(text)
        raw = data['data'][full_code]['data']['data']

        bars = []
        for line in raw:
            parts = line.split(' ')
            bars.append({
                'time': f'{parts[0][:2]}:{parts[0][2:4]}',
                'close': float(parts[1]),
                'vol': float(parts[2]),
                'amount': float(parts[3]),
            })
        return bars
    except Exception as e:
        print(f"  ❌ 腾讯财经接口失败: {e}")
        return []


# ─── 涨停/跌停数据 ────────────────────────────────────────────────

def fetch_limit_list(date: str, limit_type: str = 'U') -> list:
    """
    采集涨停/跌停数据
    limit_type: 'U'=涨停, 'D'=跌停
    Returns: [{code, name, close, pct_chg, industry, first_time, open_times, ...}, ...]
    """
    pro = get_pro()
    date_compact = date.replace('-', '')

    df = pro.limit_list_d(trade_date=date_compact, limit_type=limit_type)

    if df is None or df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        # 解析 first_time
        ft = str(row.get('first_time', '') or '')
        if len(ft) == 6:
            ft = f'{ft[:2]}:{ft[2:4]}:{ft[4:6]}'

        result.append({
            'code': row.get('ts_code', ''),
            'name': row.get('name', ''),
            'close': float(row.get('close') or 0),
            'pct_chg': float(row.get('pct_chg') or 0),
            'amount': float(row.get('amount') or 0),
            'limit_amount': float(row.get('limit_amount') or 0),
            'first_time': ft,
            'last_time': str(row.get('last_time') or ''),
            'open_times': int(row.get('open_times') or 0),
            'industry': row.get('industry', ''),
            'fd_amount': float(row.get('fd_amount') or 0),
        })
    return result


# ─── 业绩公告/披露日程 ──────────────────────────────────────────

def fetch_disclosure_schedule(end_date: str, pre_date: str = None, actual_date: str = None) -> list:
    """
    获取财报披露日程（谁在哪天披露）
    
    Args:
        end_date: 报告期（如20260331=Q1, 20251231=年报）
        pre_date: 预计披露日期（如20260428=查4/28预约披露的公司）
        actual_date: 实际披露日期
    
    Returns: [{ts_code, ann_date, end_date, pre_date, actual_date}, ...]
    """
    pro = get_pro()
    
    params = {'end_date': end_date.replace('-', '')}
    if pre_date:
        params['pre_date'] = pre_date.replace('-', '')
    if actual_date:
        params['actual_date'] = actual_date.replace('-', '')
    
    try:
        df = pro.disclosure_date(**params)
        if df is None or df.empty:
            return []
        
        result = []
        for _, row in df.iterrows():
            ts_code = row.get('ts_code', '')
            code = ts_code.split('.')[0] if '.' in ts_code else ts_code
            result.append({
                'ts_code': ts_code,
                'code': code,
                'ann_date': str(row.get('ann_date', '') or ''),
                'end_date': str(row.get('end_date', '') or ''),
                'pre_date': str(row.get('pre_date', '') or ''),
                'actual_date': str(row.get('actual_date', '') or ''),
            })
        return result
    except Exception as e:
        print(f"  ❌ 披露日程获取失败: {e}")
        return []


def fetch_express_vip(period: str, ann_date: str = None) -> list:
    """
    批量获取业绩快报（需5000积分）
    
    Args:
        period: 报告期（如20260331=2026Q1）
        ann_date: 公告日期（筛选某日公告的快报）
    
    Returns: [{ts_code, code, name, ann_date, revenue, n_income, yoy_sales, yoy_dedu_np, ...}, ...]
    """
    pro = get_pro()
    period_compact = period.replace('-', '')
    
    try:
        params = {
            'period': period_compact,
            'fields': 'ts_code,ann_date,end_date,revenue,operate_profit,total_profit,'
                      'n_income,yoy_sales,yoy_op,yoy_tp,yoy_dedu_np,perf_summary'
        }
        df = pro.express_vip(**params)
        
        if df is None or df.empty:
            return []
        
        # 如果指定了ann_date，过滤
        if ann_date:
            ann_compact = ann_date.replace('-', '')
            df = df[df['ann_date'] == ann_compact]
        
        result = []
        for _, row in df.iterrows():
            ts_code = row.get('ts_code', '')
            code = ts_code.split('.')[0] if '.' in ts_code else ts_code
            
            revenue = row.get('revenue')
            n_income = row.get('n_income')
            yoy_sales = row.get('yoy_sales')
            yoy_np = row.get('yoy_dedu_np')
            
            result.append({
                'ts_code': ts_code,
                'code': code,
                'ann_date': str(row.get('ann_date', '') or ''),
                'revenue': float(revenue) / 1e8 if revenue else None,  # 转为亿元
                'n_income': float(n_income) / 1e8 if n_income else None,  # 转为亿元
                'yoy_sales': float(yoy_sales) if yoy_sales else None,  # 营收同比%
                'yoy_dedu_np': float(yoy_np) if yoy_np else None,  # 扣非净利同比%
                'perf_summary': str(row.get('perf_summary', '') or ''),
            })
        
        # 按净利同比降序排列
        result.sort(key=lambda x: abs(x.get('yoy_dedu_np') or 0), reverse=True)
        return result
    except Exception as e:
        print(f"  ❌ 业绩快报批量获取失败: {e}")
        return []


def fetch_income_by_period(period: str) -> list:
    """
    批量获取利润表数据（income_vip，需5000积分）
    获取指定报告期所有已披露的利润表
    
    Args:
        period: 报告期（如20260331=2026Q1）
    
    Returns: [{ts_code, code, ann_date, revenue, n_income, ...}, ...]
    """
    pro = get_pro()
    period_compact = period.replace('-', '')
    
    try:
        df = pro.income_vip(
            period=period_compact,
            fields='ts_code,ann_date,end_date,revenue,n_income,n_income_attr_p'
        )
        
        if df is None or df.empty:
            return []
        
        result = []
        for _, row in df.iterrows():
            ts_code = row.get('ts_code', '')
            code = ts_code.split('.')[0] if '.' in ts_code else ts_code
            
            revenue = row.get('revenue')
            n_income = row.get('n_income_attr_p') or row.get('n_income')
            
            result.append({
                'ts_code': ts_code,
                'code': code,
                'ann_date': str(row.get('ann_date', '') or ''),
                'revenue': float(revenue) / 1e8 if revenue else None,
                'n_income': float(n_income) / 1e8 if n_income else None,
            })
        return result
    except Exception as e:
        print(f"  ❌ 利润表批量获取失败: {e}")
        return []


def fetch_earnings_for_premarket(last_trade_date: str, today_date: str, period: str = None) -> dict:
    """
    盘前分析专用：一键获取业绩披露全景
    
    1. 昨晚实际披露的一季报/年报（actual_date=昨日）
    2. 今日预约披露的一季报/年报（pre_date=今日）
    3. 已披露的业绩快报数据（含营收/净利/同比）
    
    Args:
        last_trade_date: 上个交易日（如2026-04-27）
        today_date: 今日（如2026-04-28）
        period: 报告期（默认自动推断当前季度，如20260331）
    
    Returns: {
        'disclosed_yesterday': [...],  # 昨晚已披露
        'scheduled_today': [...],  # 今日将披露
        'express_data': [...],  # 业绩快报数据
        'period': '20260331'
    }
    """
    from datetime import datetime as dt
    
    if not period:
        # 自动推断：4-7月查Q1(0331)，7-10月查半年报(0630)，以此类推
        month = dt.now().month
        year = dt.now().year
        if month <= 4:
            period = f"{year}0331"  # Q1
        elif month <= 8:
            period = f"{year}0630"  # 半年报
        elif month <= 10:
            period = f"{year}0930"  # 三季报
        else:
            period = f"{year}1231"  # 年报
    
    result = {
        'period': period,
        'disclosed_yesterday': [],
        'scheduled_today': [],
        'express_data': [],
    }
    
    # 1. 昨晚实际披露
    print(f"  📋 查询 {last_trade_date} 实际披露...")
    yesterday_list = fetch_disclosure_schedule(period, actual_date=last_trade_date)
    result['disclosed_yesterday'] = yesterday_list
    print(f"  ✅ 昨日披露 {len(yesterday_list)} 家")
    
    time.sleep(0.3)
    
    # 2. 今日预约披露
    print(f"  📋 查询 {today_date} 预约披露...")
    today_list = fetch_disclosure_schedule(period, pre_date=today_date)
    result['scheduled_today'] = today_list
    print(f"  ✅ 今日预约 {len(today_list)} 家")
    
    time.sleep(0.3)
    
    # 3. 尝试获取业绩快报
    print(f"  📋 查询 {period} 业绩快报...")
    express = fetch_express_vip(period)
    result['express_data'] = express
    print(f"  ✅ 业绩快报 {len(express)} 家")
    
    # 4. 年报也查一下（Q1季报期间年报也在密集披露）
    year = period[:4]
    annual_period = f"{int(year)-1}1231"  # 上年年报
    
    print(f"  📋 查询 {today_date} 年报预约披露...")
    annual_today = fetch_disclosure_schedule(annual_period, pre_date=today_date)
    if annual_today:
        print(f"  ✅ 今日年报预约 {len(annual_today)} 家")
        result['annual_scheduled_today'] = annual_today
    
    return result


# ─── 概念enrichment ──────────────────────────────────────────────

# 噪音概念黑名单：标签型/地域型/过于宽泛的概念，不代表市场真实炒作方向
CONCEPT_BLACKLIST = {
    # 政策/结构标签
    '央国企改革', '一带一路', '乡村振兴', '碳中和', '专精特新',
    '国企改革', '混改', '举牌', '股权转让', '资产重组',
    # 地域标签
    '西部大开发', '深圳特区', '长三角一体化', '粤港澳大湾区',
    '京津冀一体化', '海南自贸区', '雄安新区', '成渝经济圈',
    '福建自贸区', '上海自贸区',
    # 过于宽泛
    '新材料', '新能源', '节能环保', '大数据', '物联网',
    '智慧城市', '创投', '知识产权', '高送转', '次新股',
    '独角兽', '壳资源', '摘帽', 'ST板块', '参股新三板',
    # 金融属性
    '融资融券', '沪股通', '深股通', '标普道琼斯A股',
    'MSCI概念', '富时罗素概念', '转债标的', '参股金融',
    '参股券商', '参股银行', '参股保险',
    # 行业过于宽泛（不是具体方向）
    '军工', '医药',
}


def enrich_limit_concepts(limit_list: list, date: str, limit_type: str = 'U') -> dict:
    """
    为涨停/跌停股票补充概念标签，并生成概念聚合统计
    使用 adata（免费）获取每只股票的东方财富概念
    
    Args:
        limit_list: 涨停/跌停股票列表
        date: 日期
        limit_type: 'U'=涨停, 'D'=跌停
    
    Returns: {
        'date': '2026-04-16',
        'type': 'limit_up',
        'total': 79,
        'concept_summary': [
            {'concept': '算力租赁', 'concept_code': 'BK1234', 'count': 11, 'stocks': [...]},
            ...
        ],
        'enriched_stocks': [原始数据 + concepts字段]
    }
    """
    try:
        import adata
    except ImportError:
        print("  ⚠️ adata 未安装，跳过概念enrichment")
        return {}
    
    label = '涨停' if limit_type == 'U' else '跌停'
    total = len(limit_list)
    print(f"\n🏷️  概念enrichment: 为 {total} 只{label}股获取概念标签...")
    
    # 概念计数器: {concept_name: {code, stocks: [{code, name}]}}
    concept_counter = {}
    enriched = []
    success = 0
    
    for i, stock in enumerate(limit_list):
        ts_code = stock.get('code', '')
        # 从 ts_code 提取6位代码: 002192.SZ -> 002192
        stock_code = ts_code.split('.')[0] if '.' in ts_code else ts_code
        stock_name = stock.get('name', '')
        
        try:
            # 使用 adata 获取股票所属概念
            df = adata.stock.info.get_concept_east(stock_code=stock_code)
            concepts = []
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    ccode = str(row.get('concept_code', ''))
                    cname = str(row.get('name', ''))
                    if ccode and cname:
                        concepts.append({'code': ccode, 'name': cname})
                        # 累加到概念计数器
                        if cname not in concept_counter:
                            concept_counter[cname] = {
                                'concept_code': ccode,
                                'stocks': []
                            }
                        concept_counter[cname]['stocks'].append({
                            'code': ts_code,
                            'name': stock_name,
                            'pct_chg': stock.get('pct_chg', 0),
                        })
            
            stock_enriched = dict(stock)
            stock_enriched['concepts'] = concepts
            enriched.append(stock_enriched)
            success += 1
            
            # 进度显示（每10只）
            if (i + 1) % 10 == 0:
                print(f"  📋 进度: {i+1}/{total} ({success} 成功)")
            
            # 控制请求频率，避免被限流
            if i < total - 1:
                time.sleep(0.3)
                
        except Exception as e:
            # 失败时保留原始数据，不中断
            stock_enriched = dict(stock)
            stock_enriched['concepts'] = []
            enriched.append(stock_enriched)
            if 'timed out' not in str(e).lower():
                print(f"  ⚠️ {stock_code}({stock_name}) 概念获取失败: {e}")
    
    print(f"  ✅ 概念获取完成: {success}/{total} 成功")
    
    # 生成概念聚合统计（过滤噪音概念，按涨停数降序）
    concept_summary = []
    filtered_out = []
    for cname, info in concept_counter.items():
        item = {
            'concept': cname,
            'concept_code': info['concept_code'],
            'count': len(info['stocks']),
            'stocks': info['stocks'],
        }
        if cname in CONCEPT_BLACKLIST:
            filtered_out.append(item)
        else:
            concept_summary.append(item)
    concept_summary.sort(key=lambda x: x['count'], reverse=True)
    filtered_out.sort(key=lambda x: x['count'], reverse=True)
    
    if filtered_out:
        print(f"  🚫 过滤噪音概念: {len(filtered_out)} 个（{', '.join(f['concept'] for f in filtered_out[:5])}...)") 
    
    # 打印TOP概念
    print(f"\n📊 概念{label}统计 TOP15（已过滤噪音概念）:")
    for item in concept_summary[:15]:
        stock_names = [s['name'] for s in item['stocks'][:5]]
        suffix = f" +{len(item['stocks'])-5}只" if len(item['stocks']) > 5 else ""
        print(f"  {item['concept']:12s} {item['count']:3d}只  {', '.join(stock_names)}{suffix}")
    
    result = {
        'date': date,
        'type': 'limit_up' if limit_type == 'U' else 'limit_down',
        'total': total,
        'enriched_count': success,
        'concept_summary': concept_summary,
        'filtered_concepts': filtered_out,
        'enriched_stocks': enriched,
    }
    
    return result


# ─── 保存 ──────────────────────────────────────────────────────────

def save_data(code: str, data_type: str, data, category: str = None):
    """保存数据到本地 JSON 文件
    
    Args:
        code: 代码
        data_type: 数据类型
        data: 数据内容
        category: 数据分类（stocks/indices/concepts/limit_list）
    """
    # 自动推断分类
    if category is None:
        if code.startswith('limit-'):
            category = 'limit_list'
            # limit_list 直接保存文件，不建子目录
            save_dir = DATA_DIR / category
            save_dir.mkdir(parents=True, exist_ok=True)
            filepath = save_dir / f"{code}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return filepath
        elif code.startswith(('000', '399', '899')):
            category = 'indices'
        elif code.startswith(('BK', '886')):
            category = 'concepts'
        else:
            category = 'stocks'
    
    save_dir = DATA_DIR / category / code
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / f"{data_type}.json"

    # 日线/分时数据，合并已有文件
    if isinstance(data, dict) and filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        if isinstance(existing, dict):
            existing.update(data)
            data = existing

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


# ─── 全量采集（一天）──────────────────────────────────────────────

def fetch_all(date: str, watchlist: list, indices: list):
    """
    采集一天的全量数据：盯盘股日线+分时 + 涨停 + 跌停 + 指数
    必须传入 watchlist 和 indices
    """
    if not watchlist:
        print("❌ 错误: 必须传入 watchlist")
        return
    if not indices:
        print("❌ 错误: 必须传入 indices")
        return

    print(f"{'='*60}")
    print(f"📊 全量采集: {date}")
    print(f"盯盘股: {watchlist}")
    print(f"指数: {indices}")
    print(f"{'='*60}")

    # 1. 涨停数据
    print(f"\n🔴 涨停数据...")
    up_list = fetch_limit_list(date, 'U')
    if up_list:
        fp = save_data(f"{date.replace('-', '')}_up", 'limit_up', up_list, category='limit_list')
        print(f"✅ 涨停 {len(up_list)} 只 → {fp}")
    else:
        print("⚠️ 无涨停数据")

    # 2. 跌停数据
    print(f"\n🟢 跌停数据...")
    down_list = fetch_limit_list(date, 'D')
    if down_list:
        fp = save_data(f"{date.replace('-', '')}_down", 'limit_down', down_list, category='limit_list')
        print(f"✅ 跌停 {len(down_list)} 只 → {fp}")
    else:
        print("⚠️ 无跌停数据")

    # 3. 盯盘股日线+分时
    print(f"\n📈 盯盘股数据...")
    for code in watchlist:
        ts_code = get_ts_code(code)
        print(f"\n  --- {code} ({ts_code}) ---")

        # 日线
        daily = fetch_daily(code, date, date)
        if daily:
            save_data(code, 'daily', daily)
            d = list(daily.values())[0]
            print(f"  📅 日线: {d['close']:.2f} ({d['change_pct']:+.2f}%)")

        # 分时
        intraday = fetch_intraday(code, date, date)
        if intraday:
            fp = save_data(code, 'intraday_1min', intraday)
            total = sum(len(v) for v in intraday.values())
            print(f"  ⏱️ 分时: {total} 条 → {fp}")

    # 4. 指数（优先 Tushare idx_mins，失败则用腾讯）
    print(f"\n📊 指数数据...")
    for code in indices:
        print(f"\n  --- 指数 {code} ---")

        # 日线
        daily = fetch_daily(code, date, date)
        if daily:
            save_data(code, 'daily', daily)
            d = list(daily.values())[0]
            print(f"  📅 日线: {d['close']:.2f} ({d['change_pct']:+.2f}%)")

        # 分时（Tushare idx_mins）
        intraday = fetch_intraday(code, date, date, is_index=True)
        if intraday:
            fp = save_data(code, 'intraday_1min', intraday)
            total = sum(len(v) for v in intraday.values())
            print(f"  ⏱️ 分时(tushare): {total} 条")
        else:
            # 备用：腾讯财经（仅最近一个交易日）
            print(f"  ⚠️ Tushare idx_mins 权限不足，尝试腾讯财经...")
            bars = fetch_index_min_tencent(code, date)
            if bars:
                # 腾讯返回 close/vol/amount，补齐格式
                full_bars = []
                for b in bars:
                    full_bars.append({
                        'time': b['time'],
                        'open': b['close'],  # 腾讯分时只有 close
                        'high': b['close'],
                        'low': b['close'],
                        'close': b['close'],
                        'vol': b['vol'],
                        'amount': b['amount'],
                    })
                fp = save_data(code, 'intraday_1min_tencent', {date: full_bars})
                print(f"  ⏱️ 分时(腾讯): {len(full_bars)} 条 → {fp}")
            else:
                print(f"  ❌ 指数分时获取失败")

    print(f"\n{'='*60}")
    print("🎉 全量采集完成！")


# ─── 主流程 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='交易系统数据采集工具（Tushare 高积分）')
    parser.add_argument('--code', type=str, help='股票/指数代码（如 002192）')
    parser.add_argument('--days', type=int, default=30, help='最近N天（默认30）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--intraday', action='store_true', help='同时采集分钟数据')
    parser.add_argument('--freq', type=str, default='1min', choices=['1min','5min','15min','30min','60min'])
    parser.add_argument('--limit-up', action='store_true', help='采集涨停/跌停数据')
    parser.add_argument('--type', type=str, default='U', choices=['U','D'], help='U=涨停 D=跌停')
    parser.add_argument('--date', type=str, help='指定日期')
    parser.add_argument('--all', action='store_true', help='全量采集（涨跌停+股票+指数）')
    parser.add_argument('--watchlist', type=str, nargs='+', help='股票列表（用于 --all）')
    parser.add_argument('--indices', type=str, nargs='+', help='指数列表（用于 --all）')
    parser.add_argument('--is-index', action='store_true', help='指定代码为指数')
    parser.add_argument('--no-enrich', action='store_true', help='跳过涨停概念enrichment')

    args = parser.parse_args()

    if args.all:
        if not args.date:
            parser.error("--all 需要指定 --date")
        if not args.watchlist:
            parser.error("--all 需要指定 --watchlist")
        if not args.indices:
            parser.error("--all 需要指定 --indices")
        fetch_all(args.date, args.watchlist, args.indices)
        return

    if args.limit_up:
        if not args.date:
            parser.error("--limit-up 需要指定 --date")
        label = '涨停' if args.type == 'U' else '跌停'
        print(f"📊 采集{label}数据: {args.date}")
        data = fetch_limit_list(args.date, args.type)
        if data:
            tag = 'limit-up' if args.type == 'U' else 'limit-down'
            filepath = save_data(f"{tag}-{args.date.replace('-', '')}", f'limit_{args.type.lower()}', data)
            print(f"✅ {label} {len(data)} 只 → {filepath}")
            
            # 自动进行概念enrichment
            if not args.no_enrich:
                enriched = enrich_limit_concepts(data, args.date, args.type)
                if enriched:
                    # 保存概念聚合统计
                    summary_file = f"{tag}-concepts-{args.date.replace('-', '')}"
                    fp = save_data(summary_file, f'concepts', enriched, category='limit_list')
                    print(f"✅ 概念统计 → {fp}")
            else:
                print("⏭️ 跳过概念enrichment (--no-enrich)")
        else:
            print("⚠️ 无数据")
        return

    if not args.code:
        parser.error("请指定 --code / --limit-up / --all")

    code = args.code.strip()
    ts_code = get_ts_code(code)
    end = args.end or datetime.now().strftime('%Y-%m-%d')
    start = args.start or (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    print(f"📊 采集 {ts_code} | {start} ~ {end}")

    # 日线
    daily = fetch_daily(code, start, end)
    if daily:
        filepath = save_data(code, 'daily', daily)
        print(f"✅ 日线 {len(daily)} 天 → {filepath}")

    # 分钟数据
    if args.intraday:
        print(f"⏱️ 分钟数据（{args.freq}）...")
        intraday = fetch_intraday(code, start, end, args.freq, is_index=args.is_index)
        if intraday:
            filepath = save_data(code, f'intraday_{args.freq}', intraday)
            total = sum(len(v) for v in intraday.values())
            print(f"✅ {len(intraday)} 天 {total} 条 → {filepath}")

    print("🎉 完成！")


if __name__ == "__main__":
    main()
