#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用Tushare获取股票实时财务数据（简化版，使用免费接口）
"""

import tushare as ts
import pandas as pd
from datetime import datetime
import time

# 20家核心公司列表
STOCK_LIST = [
    {'name': '特变电工', 'code': '600089'},
    {'name': '明阳智能', 'code': '601615'},
    {'name': '协鑫能科', 'code': '002015'},
    {'name': '阳光电源', 'code': '300274'},
    {'name': '金盘科技', 'code': '688676'},
    {'name': '国电南瑞', 'code': '600406'},
    {'name': '大金重工', 'code': '002487'},
    {'name': '德业股份', 'code': '605117'},
    {'name': '平高电气', 'code': '600312'},
    {'name': '许继电气', 'code': '000400'},
    {'name': '科华数据', 'code': '002335'},
    {'name': '绿发电力', 'code': '000537'},
    {'name': '宁德时代', 'code': '300750'},
    {'name': '南网能源', 'code': '003035'},
    {'name': '保变电气', 'code': '600550'},
    {'name': '德力佳', 'code': '603092'},
    {'name': '中国西电', 'code': '601179'},
    {'name': '金开新能', 'code': '600821'},
    {'name': '伊戈尔', 'code': '002922'},
    {'name': '节能风电', 'code': '601016'},
]


def get_stock_info(code):
    """获取单只股票的实时信息（使用免费接口）"""
    try:
        # 使用免费的实时行情接口
        df = ts.get_realtime_quotes(code)
        
        if df is None or df.empty:
            return None
        
        info = df.iloc[0]
        
        # 计算市值（股价 × 流通股本）
        price = float(info.get('price', 0))
        
        result = {
            '代码': code,
            '名称': info.get('name', ''),
            '最新价': price,
            '涨跌幅': float(info.get('changepercent', 0)),
            '开盘价': float(info.get('open', 0)),
            '最高价': float(info.get('high', 0)),
            '最低价': float(info.get('low', 0)),
            '成交量': float(info.get('volume', 0)),
            '成交额': float(info.get('amount', 0)),
        }
        
        # 尝试获取PE等估值指标（需要额外接口）
        try:
            basic = ts.get_stock_basics()
            if code in basic.index:
                stock_basic = basic.loc[code]
                result['PE'] = float(stock_basic.get('pe', 0))
                result['PB'] = float(stock_basic.get('pb', 0))
                result['流通股本(亿)'] = float(stock_basic.get('outstanding', 0))
                result['总股本(亿)'] = float(stock_basic.get('totals', 0))
                # 计算市值
                result['流通市值(亿)'] = round(price * result['流通股本(亿)'], 2)
                result['总市值(亿)'] = round(price * result['总股本(亿)'], 2)
        except:
            result['PE'] = None
            result['PB'] = None
            result['流通市值(亿)'] = None
            result['总市值(亿)'] = None
        
        return result
        
    except Exception as e:
        print(f"  ⚠️  获取失败: {e}")
        return None


def format_value(value, decimals=2):
    """格式化数值"""
    if value is None or pd.isna(value) or value == 0:
        return '-'
    return f"{value:.{decimals}f}"


def main():
    """主函数"""
    print("=" * 80)
    print("开始从Tushare获取股票实时数据（免费接口）...")
    print("=" * 80)
    print()
    
    # 先获取股票基础信息
    print("正在获取所有股票基础信息...")
    try:
        stock_basics = ts.get_stock_basics()
        print(f"✅ 获取到 {len(stock_basics)} 只股票的基础信息")
    except Exception as e:
        print(f"⚠️  获取基础信息失败: {e}")
        stock_basics = pd.DataFrame()
    
    print()
    
    # 存储结果
    results = []
    
    # 遍历所有股票
    for i, stock in enumerate(STOCK_LIST, 1):
        print(f"[{i}/{len(STOCK_LIST)}] 正在获取 {stock['name']} ({stock['code']})...", end=' ')
        
        info = get_stock_info(stock['code'])
        
        if info:
            result = {
                '序号': i,
                '公司': stock['name'],
                '代码': stock['code'],
                '最新价(元)': format_value(info['最新价']),
                '涨跌幅(%)': format_value(info['涨跌幅']),
                'PE(动态)': format_value(info.get('PE')),
                'PB': format_value(info.get('PB')),
                '总市值(亿)': format_value(info.get('总市值(亿)')),
                '流通市值(亿)': format_value(info.get('流通市值(亿)')),
                '成交额(亿)': format_value(info['成交额'] / 100000000),
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
                '成交额(亿)': '-',
            })
        
        # 避免请求过快
        if i < len(STOCK_LIST):
            time.sleep(0.3)
    
    print()
    print("=" * 80)
    
    # 转换为DataFrame
    df = pd.DataFrame(results)
    
    # 保存为CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_csv = f'/Users/huijiecai/Project/stock/scripts/stock_data_{timestamp}.csv'
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"✅ CSV数据已保存: {output_csv}")
    
    # 保存为JSON
    output_json = f'/Users/huijiecai/Project/stock/scripts/stock_data_{timestamp}.json'
    df.to_json(output_json, orient='records', force_ascii=False, indent=2)
    print(f"✅ JSON数据已保存: {output_json}")
    
    # 生成Markdown报告
    output_md = f'/Users/huijiecai/Project/stock/scripts/stock_data_{timestamp}.md'
    
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(f"# 20家核心公司最新财务数据\n\n")
        f.write(f"> **更新时间**: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n")
        f.write(f"> **数据来源**: Tushare免费接口\n\n")
        f.write("---\n\n")
        f.write("## 完整数据表\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n\n---\n\n")
        
        # 按PE分级
        f.write("## 估值分级分析\n\n")
        
        # 过滤有效PE数据
        df_valid = df[df['PE(动态)'] != '-'].copy()
        df_valid['PE_NUM'] = pd.to_numeric(df_valid['PE(动态)'], errors='coerce')
        df_valid = df_valid[df_valid['PE_NUM'] > 0]  # 过滤负PE和无效值
        
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
            
            # 统计信息
            f.write("\n\n---\n\n## 统计信息\n\n")
            f.write(f"- **数据获取成功**: {len(df_valid)}/{len(df)} 只\n")
            f.write(f"- **PE平均值**: {df_valid['PE_NUM'].mean():.2f}\n")
            f.write(f"- **PE中位数**: {df_valid['PE_NUM'].median():.2f}\n")
            
            if len(df_valid) > 0:
                min_pe_stock = df_valid[df_valid['PE_NUM'] == df_valid['PE_NUM'].min()]
                max_pe_stock = df_valid[df_valid['PE_NUM'] == df_valid['PE_NUM'].max()]
                f.write(f"- **PE最小值**: {df_valid['PE_NUM'].min():.2f} ({min_pe_stock['公司'].values[0]})\n")
                f.write(f"- **PE最大值**: {df_valid['PE_NUM'].max():.2f} ({max_pe_stock['公司'].values[0]})\n")
            
            # 市值统计
            df_mv = df[df['总市值(亿)'] != '-'].copy()
            df_mv['MV_NUM'] = pd.to_numeric(df_mv['总市值(亿)'], errors='coerce')
            if len(df_mv) > 0:
                f.write(f"\n- **总市值平均**: {df_mv['MV_NUM'].mean():.2f}亿\n")
                f.write(f"- **总市值中位数**: {df_mv['MV_NUM'].median():.2f}亿\n")
                max_mv_stock = df_mv[df_mv['MV_NUM'] == df_mv['MV_NUM'].max()]
                min_mv_stock = df_mv[df_mv['MV_NUM'] == df_mv['MV_NUM'].min()]
                f.write(f"- **市值最大**: {df_mv['MV_NUM'].max():.2f}亿 ({max_mv_stock['公司'].values[0]})\n")
                f.write(f"- **市值最小**: {df_mv['MV_NUM'].min():.2f}亿 ({min_mv_stock['公司'].values[0]})\n")
        else:
            f.write("⚠️ 未获取到有效的PE数据\n")
    
    print(f"✅ Markdown报告已保存: {output_md}")
    
    # 打印表格预览
    print("\n" + "=" * 80)
    print("数据预览（前10条）:")
    print("=" * 80)
    print(df.head(10).to_string(index=False))
    
    print("\n" + "=" * 80)
    print("✅ 数据获取完成！")
    print("=" * 80)
    print(f"\n输出文件:")
    print(f"  1. CSV: {output_csv}")
    print(f"  2. JSON: {output_json}")
    print(f"  3. Markdown: {output_md}")
    
    return output_md


if __name__ == '__main__':
    output_file = main()
    print(f"\n💡 下一步: 查看 {output_file}")
