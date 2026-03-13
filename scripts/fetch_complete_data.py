#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从东方财富网获取股票完整财务数据（PE、市值、股本等）
"""

import requests
import pandas as pd
from datetime import datetime
import json
import time

# 23家核心公司列表
STOCK_LIST = [
    {'name': '特变电工', 'code': '600089', 'market': 'SH'},
    {'name': '明阳智能', 'code': '601615', 'market': 'SH'},
    {'name': '协鑫能科', 'code': '002015', 'market': 'SZ'},
    {'name': '阳光电源', 'code': '300274', 'market': 'SZ'},
    {'name': '金盘科技', 'code': '688676', 'market': 'SH'},
    {'name': '国电南瑞', 'code': '600406', 'market': 'SH'},
    {'name': '大金重工', 'code': '002487', 'market': 'SZ'},
    {'name': '德业股份', 'code': '605117', 'market': 'SH'},
    {'name': '平高电气', 'code': '600312', 'market': 'SH'},
    {'name': '许继电气', 'code': '000400', 'market': 'SZ'},
    {'name': '科华数据', 'code': '002335', 'market': 'SZ'},
    {'name': '绿发电力', 'code': '000537', 'market': 'SZ'},
    {'name': '宁德时代', 'code': '300750', 'market': 'SZ'},
    {'name': '南网能源', 'code': '003035', 'market': 'SZ'},
    {'name': '保变电气', 'code': '600550', 'market': 'SH'},
    {'name': '德力佳', 'code': '603092', 'market': 'SH'},
    {'name': '中国西电', 'code': '601179', 'market': 'SH'},
    {'name': '金开新能', 'code': '600821', 'market': 'SH'},
    {'name': '伊戈尔', 'code': '002922', 'market': 'SZ'},
    {'name': '节能风电', 'code': '601016', 'market': 'SH'},
    {'name': '三一重工', 'code': '600031', 'market': 'SH'},
    {'name': '海力风电', 'code': '301155', 'market': 'SZ'},
    {'name': '东方电缆', 'code': '603606', 'market': 'SH'},
]


def get_stock_info_from_eastmoney(code, market):
    """从东方财富网获取股票完整信息"""
    try:
        # 东方财富网API
        # secid: 市场.代码 (1.上海 0.深圳)
        market_code = '1' if market == 'SH' else '0'
        secid = f"{market_code}.{code}"
        
        url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f57,f58,f162,f163,f116,f60,f46,f44,f45,f47,f48,f50,f107,f137,f152,f161"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'http://quote.eastmoney.com/'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        if data.get('rc') != 0 or not data.get('data'):
            return None
        
        stock_data = data['data']
        
        result = {
            'code': code,
            'name': stock_data.get('f58', ''),
            'price': stock_data.get('f43', 0) / 100,  # 最新价
            'change_pct': stock_data.get('f170', 0) / 100,  # 涨跌幅
            'pe_ttm': stock_data.get('f162', 0) / 100 if stock_data.get('f162') else None,  # 动态PE
            'pb': stock_data.get('f167', 0) / 100 if stock_data.get('f167') else None,  # 市净率
            'total_market_cap': stock_data.get('f116', 0) / 100000000 if stock_data.get('f116') else None,  # 总市值（亿）
            'float_market_cap': stock_data.get('f117', 0) / 100000000 if stock_data.get('f117') else None,  # 流通市值（亿）
            'turnover_rate': stock_data.get('f168', 0) / 100 if stock_data.get('f168') else None,  # 换手率
            'volume': stock_data.get('f47', 0),  # 成交量
            'amount': stock_data.get('f48', 0) / 100000000 if stock_data.get('f48') else None,  # 成交额（亿）
        }
        
        return result
        
    except Exception as e:
        print(f"  ⚠️ 获取失败: {e}")
        return None


def format_value(value, decimals=2):
    """格式化数值"""
    if value is None or pd.isna(value) or value == 0:
        return '-'
    return f"{value:.{decimals}f}"


def main():
    """主函数"""
    print("=" * 80)
    print("从东方财富网获取股票完整财务数据...")
    print("=" * 80)
    print()
    
    results = []
    
    # 遍历所有股票
    for i, stock in enumerate(STOCK_LIST, 1):
        print(f"[{i}/{len(STOCK_LIST)}] 正在获取 {stock['name']} ({stock['code']})...", end=' ')
        
        info = get_stock_info_from_eastmoney(stock['code'], stock['market'])
        
        if info:
            result = {
                '序号': i,
                '公司': stock['name'],
                '代码': stock['code'],
                '最新价(元)': format_value(info['price']),
                '涨跌幅(%)': format_value(info['change_pct']),
                'PE(动态)': format_value(info['pe_ttm']),
                'PB': format_value(info['pb']),
                '总市值(亿)': format_value(info['total_market_cap']),
                '流通市值(亿)': format_value(info['float_market_cap']),
                '换手率(%)': format_value(info['turnover_rate']),
                '成交额(亿)': format_value(info['amount']),
            }
            results.append(result)
            print(f"✅ 价格: {result['最新价(元)']}元, PE: {result['PE(动态)']}, 市值: {result['总市值(亿)']}亿")
        else:
            print("❌ 获取失败")
            results.append({
                '序号': i,
                '公司': stock['name'],
                '代码': stock['code'],
                '最新价(元)': '-',
                '涨跌幅(%)': '-',
                'PE(动态)': '-',
                'PB': '-',
                '总市值(亿)': '-',
                '流通市值(亿)': '-',
                '换手率(%)': '-',
                '成交额(亿)': '-',
            })
        
        # 避免请求过快
        time.sleep(0.2)
    
    print()
    print("=" * 80)
    
    # 转换为DataFrame
    df = pd.DataFrame(results)
    
    # 保存文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = f'/Users/huijiecai/Project/stock/scripts/stock_data_complete_{timestamp}.csv'
    output_json = f'/Users/huijiecai/Project/stock/scripts/stock_data_complete_{timestamp}.json'
    output_md = f'/Users/huijiecai/Project/stock/scripts/stock_data_complete_{timestamp}.md'
    
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    df.to_json(output_json, orient='records', force_ascii=False, indent=2)
    
    print(f"✅ CSV: {output_csv}")
    print(f"✅ JSON: {output_json}")
    
    # 生成Markdown报告
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(f"# 23家核心公司完整财务数据\n\n")
        f.write(f"> **更新时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
        f.write(f"> **数据来源**: 东方财富网实时数据\n\n")
        f.write("---\n\n")
        f.write("## 完整数据表\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n\n---\n\n")
        
        # 估值分级
        f.write("## 估值分级分析\n\n")
        
        df_valid = df[df['PE(动态)'] != '-'].copy()
        df_valid['PE_NUM'] = pd.to_numeric(df_valid['PE(动态)'], errors='coerce')
        df_valid = df_valid[df_valid['PE_NUM'] > 0]
        
        if len(df_valid) > 0:
            f.write("### 🟢 低估值区 (PE < 30)\n\n")
            low_pe = df_valid[df_valid['PE_NUM'] < 30].sort_values('PE_NUM')
            if len(low_pe) > 0:
                f.write(low_pe[['序号', '公司', '代码', '最新价(元)', 'PE(动态)', '总市值(亿)', '涨跌幅(%)']].to_markdown(index=False))
                f.write(f"\n\n**共 {len(low_pe)} 只**\n")
            else:
                f.write("无\n")
            
            f.write("\n\n### 🟡 中等估值区 (PE 30-50)\n\n")
            mid_pe = df_valid[(df_valid['PE_NUM'] >= 30) & (df_valid['PE_NUM'] < 50)].sort_values('PE_NUM')
            if len(mid_pe) > 0:
                f.write(mid_pe[['序号', '公司', '代码', '最新价(元)', 'PE(动态)', '总市值(亿)', '涨跌幅(%)']].to_markdown(index=False))
                f.write(f"\n\n**共 {len(mid_pe)} 只**\n")
            else:
                f.write("无\n")
            
            f.write("\n\n### 🔴 高估值区 (PE >= 50)\n\n")
            high_pe = df_valid[df_valid['PE_NUM'] >= 50].sort_values('PE_NUM')
            if len(high_pe) > 0:
                f.write(high_pe[['序号', '公司', '代码', '最新价(元)', 'PE(动态)', '总市值(亿)', '涨跌幅(%)']].to_markdown(index=False))
                f.write(f"\n\n**共 {len(high_pe)} 只**\n")
            else:
                f.write("无\n")
            
            # 统计
            f.write("\n\n---\n\n## 统计信息\n\n")
            f.write(f"- **数据获取成功**: {len(df_valid)}/{len(df)} 只\n")
            f.write(f"- **PE平均值**: {df_valid['PE_NUM'].mean():.2f}\n")
            f.write(f"- **PE中位数**: {df_valid['PE_NUM'].median():.2f}\n")
            
            if len(df_valid) > 0:
                min_pe_stock = df_valid.loc[df_valid['PE_NUM'].idxmin()]
                max_pe_stock = df_valid.loc[df_valid['PE_NUM'].idxmax()]
                f.write(f"- **PE最小**: {df_valid['PE_NUM'].min():.2f} ({min_pe_stock['公司']})\n")
                f.write(f"- **PE最大**: {df_valid['PE_NUM'].max():.2f} ({max_pe_stock['公司']})\n")
            
            # 市值统计
            df_mv = df[df['总市值(亿)'] != '-'].copy()
            df_mv['MV_NUM'] = pd.to_numeric(df_mv['总市值(亿)'], errors='coerce')
            if len(df_mv) > 0:
                f.write(f"\n- **总市值平均**: {df_mv['MV_NUM'].mean():.2f}亿\n")
                f.write(f"- **总市值中位数**: {df_mv['MV_NUM'].median():.2f}亿\n")
                max_mv_stock = df_mv.loc[df_mv['MV_NUM'].idxmax()]
                min_mv_stock = df_mv.loc[df_mv['MV_NUM'].idxmin()]
                f.write(f"- **市值最大**: {df_mv['MV_NUM'].max():.2f}亿 ({max_mv_stock['公司']})\n")
                f.write(f"- **市值最小**: {df_mv['MV_NUM'].min():.2f}亿 ({min_mv_stock['公司']})\n")
    
    print(f"✅ Markdown: {output_md}")
    
    # 打印预览
    print("\n" + "=" * 80)
    print("数据预览:")
    print("=" * 80)
    print(df.to_string(index=False))
    
    print("\n" + "=" * 80)
    print("✅ 完整财务数据获取完成！")
    print("=" * 80)
    
    return output_md, df


if __name__ == '__main__':
    output_file, df = main()
    print(f"\n💡 数据文件: {output_file}")
