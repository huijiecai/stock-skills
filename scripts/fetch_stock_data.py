#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从Tushare获取股票实时财务数据
"""

import tushare as ts
import pandas as pd
from datetime import datetime
import json

# 20家核心公司列表
STOCK_LIST = [
    {'name': '特变电工', 'code': '600089', 'exchange': 'SH'},
    {'name': '明阳智能', 'code': '601615', 'exchange': 'SH'},
    {'name': '协鑫能科', 'code': '002015', 'exchange': 'SZ'},
    {'name': '阳光电源', 'code': '300274', 'exchange': 'SZ'},
    {'name': '金盘科技', 'code': '688676', 'exchange': 'SH'},
    {'name': '国电南瑞', 'code': '600406', 'exchange': 'SH'},
    {'name': '大金重工', 'code': '002487', 'exchange': 'SZ'},
    {'name': '德业股份', 'code': '605117', 'exchange': 'SH'},
    {'name': '平高电气', 'code': '600312', 'exchange': 'SH'},
    {'name': '许继电气', 'code': '000400', 'exchange': 'SZ'},
    {'name': '科华数据', 'code': '002335', 'exchange': 'SZ'},
    {'name': '绿发电力', 'code': '000537', 'exchange': 'SZ'},
    {'name': '宁德时代', 'code': '300750', 'exchange': 'SZ'},
    {'name': '南网能源', 'code': '003035', 'exchange': 'SZ'},
    {'name': '保变电气', 'code': '600550', 'exchange': 'SH'},
    {'name': '德力佳', 'code': '603092', 'exchange': 'SH'},
    {'name': '中国西电', 'code': '601179', 'exchange': 'SH'},
    {'name': '金开新能', 'code': '600821', 'exchange': 'SH'},
    {'name': '伊戈尔', 'code': '002922', 'exchange': 'SZ'},
    {'name': '节能风电', 'code': '601016', 'exchange': 'SH'},
]


def init_tushare():
    """初始化Tushare"""
    # 从环境变量或配置文件读取token
    try:
        with open('/Users/huijiecai/.tushare_token', 'r') as f:
            token = f.read().strip()
    except FileNotFoundError:
        print("❌ 未找到Tushare token，请先配置")
        print("方法1: 创建文件 ~/.tushare_token 并写入你的token")
        print("方法2: 或在代码中直接设置 token = 'your_token'")
        return None
    
    ts.set_token(token)
    return ts.pro_api()


def get_stock_basic_info(pro, ts_code):
    """获取股票基本信息"""
    try:
        df = pro.daily_basic(ts_code=ts_code, fields='ts_code,trade_date,close,turnover_rate,volume_ratio,pe_ttm,pb,ps_ttm,total_mv,circ_mv')
        if df is not None and len(df) > 0:
            return df.iloc[0].to_dict()
    except Exception as e:
        print(f"获取 {ts_code} 基本信息失败: {e}")
    return None


def get_latest_financial(pro, ts_code):
    """获取最新财报数据"""
    try:
        # 获取最近的季报
        df = pro.income(ts_code=ts_code, fields='ts_code,end_date,revenue,n_income,n_income_attr_p')
        if df is not None and len(df) > 0:
            return df.iloc[0].to_dict()
    except Exception as e:
        print(f"获取 {ts_code} 财报数据失败: {e}")
    return None


def format_number(num, unit='亿'):
    """格式化数字"""
    if num is None or pd.isna(num):
        return '-'
    
    if unit == '亿':
        return f"{num / 10000:.2f}"
    elif unit == '万':
        return f"{num:.2f}"
    else:
        return f"{num:.2f}"


def main():
    """主函数"""
    print("=" * 80)
    print("开始从Tushare获取股票实时数据...")
    print("=" * 80)
    print()
    
    # 初始化
    pro = init_tushare()
    if pro is None:
        return
    
    # 存储结果
    results = []
    
    # 遍历所有股票
    for stock in STOCK_LIST:
        ts_code = f"{stock['code']}.{stock['exchange']}"
        print(f"正在获取 {stock['name']} ({ts_code})...")
        
        # 获取基本信息
        basic_info = get_stock_basic_info(pro, ts_code)
        
        # 获取财报数据
        financial = get_latest_financial(pro, ts_code)
        
        if basic_info:
            result = {
                '公司': stock['name'],
                '代码': stock['code'],
                'TS代码': ts_code,
                '日期': basic_info.get('trade_date', '-'),
                '收盘价': f"{basic_info.get('close', 0):.2f}" if basic_info.get('close') else '-',
                'PE(TTM)': f"{basic_info.get('pe_ttm', 0):.2f}" if basic_info.get('pe_ttm') and basic_info.get('pe_ttm') > 0 else '-',
                'PB': f"{basic_info.get('pb', 0):.2f}" if basic_info.get('pb') else '-',
                'PS': f"{basic_info.get('ps_ttm', 0):.2f}" if basic_info.get('ps_ttm') else '-',
                '总市值(亿)': format_number(basic_info.get('total_mv')),
                '流通市值(亿)': format_number(basic_info.get('circ_mv')),
                '换手率%': f"{basic_info.get('turnover_rate', 0):.2f}" if basic_info.get('turnover_rate') else '-',
            }
            
            if financial:
                result['最新财报期'] = financial.get('end_date', '-')
                result['营收(亿)'] = format_number(financial.get('revenue'))
                result['净利润(亿)'] = format_number(financial.get('n_income_attr_p'))
            
            results.append(result)
            
            # 打印简要信息
            print(f"  ✅ 股价: {result['收盘价']}元, PE: {result['PE(TTM)']}, 市值: {result['总市值(亿)']}亿")
        else:
            print(f"  ❌ 获取失败")
        
        print()
    
    # 转换为DataFrame
    df = pd.DataFrame(results)
    
    # 保存为CSV
    output_csv = f'/Users/huijiecai/Project/stock/scripts/stock_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"✅ 数据已保存到: {output_csv}")
    
    # 保存为JSON
    output_json = f'/Users/huijiecai/Project/stock/scripts/stock_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    df.to_json(output_json, orient='records', force_ascii=False, indent=2)
    print(f"✅ 数据已保存到: {output_json}")
    
    # 打印表格
    print("\n" + "=" * 80)
    print("数据汇总表:")
    print("=" * 80)
    print(df.to_string(index=False))
    
    # 生成Markdown表格
    output_md = f'/Users/huijiecai/Project/stock/scripts/stock_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md'
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(f"# 20家核心公司最新财务数据\n\n")
        f.write(f"> 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"> 数据来源: Tushare\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n\n---\n\n")
        f.write("## 估值分级\n\n")
        
        # 按PE分级
        df_valid = df[df['PE(TTM)'] != '-'].copy()
        df_valid['PE_NUM'] = df_valid['PE(TTM)'].astype(float)
        
        f.write("### 🟢 低估值区 (PE < 30)\n\n")
        low_pe = df_valid[df_valid['PE_NUM'] < 30].sort_values('PE_NUM')
        if len(low_pe) > 0:
            f.write(low_pe[['公司', '代码', 'PE(TTM)', '总市值(亿)', '收盘价']].to_markdown(index=False))
        else:
            f.write("无\n")
        
        f.write("\n\n### 🟡 中等估值区 (PE 30-50)\n\n")
        mid_pe = df_valid[(df_valid['PE_NUM'] >= 30) & (df_valid['PE_NUM'] < 50)].sort_values('PE_NUM')
        if len(mid_pe) > 0:
            f.write(mid_pe[['公司', '代码', 'PE(TTM)', '总市值(亿)', '收盘价']].to_markdown(index=False))
        else:
            f.write("无\n")
        
        f.write("\n\n### 🔴 高估值区 (PE >= 50)\n\n")
        high_pe = df_valid[df_valid['PE_NUM'] >= 50].sort_values('PE_NUM')
        if len(high_pe) > 0:
            f.write(high_pe[['公司', '代码', 'PE(TTM)', '总市值(亿)', '收盘价']].to_markdown(index=False))
        else:
            f.write("无\n")
    
    print(f"✅ Markdown报告已保存到: {output_md}")
    
    print("\n" + "=" * 80)
    print("✅ 数据获取完成！")
    print("=" * 80)


if __name__ == '__main__':
    main()
