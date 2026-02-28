#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票池导入工具 - 从概念股票池体系文档导入股票到后端数据库

使用方法：
    python import_stock_pool.py

功能：
1. 解析 docs/概念股票池体系.md 文件
2. 提取所有股票代码、名称、市场信息
3. 批量添加到后端股票池
4. 同步股票信息到 stock_info 表
"""

import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from backend_client import backend_client


class StockPoolImporter:
    """股票池导入器"""
    
    def __init__(self):
        self.backend_client = backend_client
        self.doc_path = Path(__file__).parent.parent.parent / "docs/概念股票池体系.md"
        
        if not self.doc_path.exists():
            raise FileNotFoundError(f"概念股票池体系文档不存在：{self.doc_path}")
    
    def parse_markdown_table(self, content: str) -> List[Dict]:
        """
        解析 Markdown 表格中的股票信息
        
        Args:
            content: Markdown 内容
            
        Returns:
            股票列表 [{'code': '688111', 'name': '金山办公', 'market': 'SH'}, ...]
        """
        stocks = []
        
        # 匹配表格行（股票代码 | 股票名称 | ...）
        # 正则表达式匹配：| 688111 | 金山办公 | ...
        pattern = r'^\|\s*(\d{6})\s*\|\s*([^|]+?)\s*\|'
        
        for line in content.split('\n'):
            match = re.match(pattern, line.strip())
            if match:
                code = match.group(1).strip()
                name = match.group(2).strip()
                
                # 去除名称中的特殊符号（如 ✅ ⚪）
                name = re.sub(r'[✅⚪❌]\s*', '', name).strip()
                
                # 判断市场
                if code.startswith(('6', '5')):
                    market = 'SH'
                else:
                    market = 'SZ'
                
                stocks.append({
                    'code': code,
                    'name': name,
                    'market': market
                })
        
        return stocks
    
    def extract_stocks_from_document(self) -> List[Dict]:
        """
        从文档中提取所有股票
        
        Returns:
            股票列表
        """
        print(f"📖 正在读取文档：{self.doc_path}")
        
        with open(self.doc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📊 文档大小：{len(content)} 字节")
        
        # 解析所有表格中的股票
        stocks = self.parse_markdown_table(content)
        
        # 去重（按股票代码）
        seen_codes = set()
        unique_stocks = []
        for stock in stocks:
            if stock['code'] not in seen_codes:
                seen_codes.add(stock['code'])
                unique_stocks.append(stock)
        
        print(f"✅ 提取到 {len(unique_stocks)} 只唯一股票")
        
        return unique_stocks
    
    def import_to_backend(self, stocks: List[Dict], batch_size: int = 50) -> Tuple[int, int]:
        """
        批量导入股票到后端
        
        Args:
            stocks: 股票列表
            batch_size: 批次大小
            
        Returns:
            (成功数量，失败数量)
        """
        print(f"\n💾 开始导入股票到后端...")
        print(f"  总数：{len(stocks)} 只")
        print(f"  批次：{batch_size} 只/批\n")
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        # 获取现有股票池（避免重复添加）
        print("  📋 查询现有股票池...")
        try:
            existing_stocks = self.backend_client.get_all_stocks()
            existing_codes = {s['code'] for s in existing_stocks}
            print(f"  ✅ 股票池已有 {len(existing_stocks)} 只股票\n")
        except Exception as e:
            print(f"  ⚠️  查询股票池失败：{e}，假设股票池为空")
            existing_codes = set()
        
        # 分批导入
        for i in range(0, len(stocks), batch_size):
            batch = stocks[i:i+batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(stocks) + batch_size - 1) // batch_size
            
            print(f"  批次 {batch_num}/{total_batches}: ", end='', flush=True)
            
            for stock in batch:
                code = stock['code']
                name = stock['name']
                market = stock['market']
                
                # 跳过已存在的股票
                if code in existing_codes:
                    print(f"⏭️", end='', flush=True)
                    skipped_count += 1
                    continue
                
                try:
                    # 添加到股票池
                    result = self.backend_client.add_stock_to_pool(
                        code=code,
                        name=name,
                        market=market,
                        note=f"来自概念股票池体系（{datetime.now().strftime('%Y-%m-%d')}）"
                    )
                    
                    if result.get('success'):
                        print(f"✅", end='', flush=True)
                        success_count += 1
                    else:
                        print(f"❌", end='', flush=True)
                        failed_count += 1
                        
                except Exception as e:
                    print(f"❌", end='', flush=True)
                    failed_count += 1
            
            print(f" (本批完成)")
        
        print(f"\n📊 导入统计:")
        print(f"  成功：{success_count} 只")
        print(f"  失败：{failed_count} 只")
        print(f"  跳过：{skipped_count} 只")
        
        return success_count, failed_count
    
    def sync_stock_info(self, stocks: List[Dict]) -> Tuple[int, int]:
        """
        同步股票信息到 stock_info 表
        
        Args:
            stocks: 股票列表
            
        Returns:
            (成功数量，失败数量)
        """
        print(f"\n🔄 同步股票信息到 stock_info...")
        
        # 准备同步数据
        stocks_to_sync = []
        for stock in stocks:
            code = stock['code']
            name = stock['name']
            market = stock['market']
            
            # 判断板块类型
            if code.startswith('688'):
                board_type = '科创板'
            elif code.startswith('300') or code.startswith('301'):
                board_type = '创业板'
            elif code.startswith('8') or code.startswith('4'):
                board_type = '北交所'
            else:
                board_type = '主板'
            
            stocks_to_sync.append({
                'stock_code': code,
                'stock_name': name,
                'market': market,
                'board_type': board_type
            })
        
        # 批量同步
        try:
            result = self.backend_client.sync_stock_info(stocks_to_sync)
            success_count = result.get('success_count', 0)
            failed_count = result.get('failed_count', 0)
            
            print(f"  ✅ 同步完成：{success_count} 成功，{failed_count} 失败")
            
            return success_count, failed_count
            
        except Exception as e:
            print(f"  ❌ 同步失败：{e}")
            return 0, len(stocks)
    
    def run(self):
        """执行完整导入流程"""
        print("=" * 60)
        print("股票池导入工具")
        print("=" * 60)
        print(f"\n📅 执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # Step 1: 从文档提取股票
            stocks = self.extract_stocks_from_document()
            
            # Step 2: 导入到后端
            success_import, failed_import = self.import_to_backend(stocks)
            
            # Step 3: 同步股票信息
            success_sync, failed_sync = self.sync_stock_info(stocks)
            
            print(f"\n{'=' * 60}")
            print("✅ 导入完成")
            print(f"{'=' * 60}")
            print(f"📊 最终统计:")
            print(f"  提取股票：{len(stocks)} 只")
            print(f"  导入成功：{success_import} 只")
            print(f"  导入失败：{failed_import} 只")
            print(f"  同步成功：{success_sync} 只")
            print(f"  同步失败：{failed_sync} 只")
            print(f"{'=' * 60}\n")
            
            return True
            
        except Exception as e:
            print(f"\n❌ 导入失败：{e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """命令行入口"""
    importer = StockPoolImporter()
    success = importer.run()
    
    if success:
        print("🎉 股票池导入成功！")
        sys.exit(0)
    else:
        print("💥 股票池导入失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()
